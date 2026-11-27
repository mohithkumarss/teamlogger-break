"""
Activity timeline for the TeamLogger Break Scheduler.

ActivityLog   - stores the day as segments in ~/.local/share/teamlogger-break/
sample_state  - works out what you're doing right now
Timeline      - Tk canvas that draws a day like TeamLogger's "Activity" bar

States (read from TeamLogger's own buttons)
  active   TeamLogger timer running
  break    TeamLogger timer stopped (on a break)
"""

import datetime as dt
import json
import os
import threading
import time
import tkinter as tk

import teamlogger_break as tl

DATA_DIR = os.path.expanduser("~/.local/share/teamlogger-break")
SAMPLE_EVERY = 5             # seconds between samples
MAX_GAP = 3 * SAMPLE_EVERY   # longer gaps (app closed, laptop asleep) stay empty

STATES = {
    # key: (label, colour) — colours match TeamLogger's legend
    "active": ("Working", "#0a6b0a"),
    "break": ("On break", "#8a8a8a"),
}


def sample_state(port):
    """Return 'active', 'break', or None when TeamLogger can't be read."""
    try:
        _page, st = tl.find_main_page(port)
    except Exception:
        return None
    if not st:
        return None
    if st.get("canResume") and not st.get("canBreak"):
        return "break"
    return "active"


class ActivityLog:
    """Segments per day: [[start_ts, end_ts, state], ...] in activity-YYYY-MM-DD.json."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}
        os.makedirs(DATA_DIR, exist_ok=True)

    def path(self, day):
        return os.path.join(DATA_DIR, f"activity-{day:%Y-%m-%d}.json")

    # TeamLogger's own "current working day" total, one number per day
    TOTALS = os.path.join(DATA_DIR, "teamlogger-totals.json")

    def tl_totals(self):
        if not hasattr(self, "_tl"):
            try:
                with open(self.TOTALS) as f:
                    self._tl = json.load(f)
            except (OSError, ValueError):
                self._tl = {}
        return self._tl

    def tl_total(self, day):
        return self.tl_totals().get(f"{day:%Y-%m-%d}")

    def set_tl_total(self, day, seconds):
        totals = self.tl_totals()
        key = f"{day:%Y-%m-%d}"
        if totals.get(key) == seconds:
            return
        totals[key] = seconds
        tmp = self.TOTALS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(totals, f, indent=0)
        os.replace(tmp, self.TOTALS)

    def load(self, day):
        with self.lock:
            if day not in self.cache:
                try:
                    with open(self.path(day)) as f:
                        self.cache[day] = json.load(f)
                except (OSError, ValueError):
                    self.cache[day] = []
            return [list(s) for s in self.cache[day]]

    def _save(self, day):
        tmp = self.path(day) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.cache[day], f)
        os.replace(tmp, self.path(day))

    def record(self, state, now_ts):
        day = dt.date.fromtimestamp(now_ts)
        self.load(day)
        with self.lock:
            segs = self.cache[day]
            last = segs[-1] if segs else None
            joined = last is not None and now_ts - last[1] <= MAX_GAP
            if joined and last[2] == state:
                last[1] = now_ts
            elif joined:
                segs.append([last[1], now_ts, state])
            else:
                segs.append([now_ts, now_ts, state])
            self._save(day)


class Recorder(threading.Thread):
    def __init__(self, log, get_port):
        super().__init__(daemon=True)
        self.log, self.get_port = log, get_port

    def run(self):
        while True:
            state = sample_state(self.get_port())
            if state:
                self.log.record(state, time.time())
            time.sleep(SAMPLE_EVERY)


def fmt_dur(seconds):
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


class Timeline(tk.Frame):
    """Day view: hour ruler + coloured bars, planned breaks outlined, hover for details."""

    W, H = 620, 92
    PAD = 14
    RULER_Y = 30
    BAR_Y0, BAR_Y1 = 42, 74

    def __init__(self, master, log, get_planned):
        super().__init__(master)
        self.log, self.get_planned = log, get_planned
        self.day = dt.date.today()
        self.full_day = tk.BooleanVar(value=False)

        top = tk.Frame(self)
        top.pack(fill="x")
        tk.Button(top, text="◀", width=2, relief="flat", command=lambda: self.shift(-1)).pack(side="left")
        self.day_lbl = tk.Label(top, text="", font=("Sans", 10, "bold"), width=16)
        self.day_lbl.pack(side="left")
        tk.Button(top, text="▶", width=2, relief="flat", command=lambda: self.shift(1)).pack(side="left")
        tk.Button(top, text="Today", relief="flat", command=self.today).pack(side="left", padx=4)
        tk.Checkbutton(top, text="Full 24h", variable=self.full_day, command=self.redraw).pack(side="left")
        legend = tk.Frame(top)
        legend.pack(side="right")
        for key, (label, colour) in STATES.items():
            tk.Label(legend, text="■", fg=colour, font=("Sans", 10)).pack(side="left")
            tk.Label(legend, text=label + " ", font=("Sans", 9)).pack(side="left")

        self.canvas = tk.Canvas(self, width=self.W, height=self.H, bg="#fafafa",
                                highlightthickness=1, highlightbackground="#dddddd")
        self.canvas.pack(pady=(4, 2))
        self.canvas.bind("<Motion>", self.hover)
        self.canvas.bind("<Leave>", lambda e: self.canvas.delete("tip"))
        self.totals = tk.Label(self, text="", font=("Sans", 9), anchor="w")
        self.totals.pack(fill="x")
        self.segs = []
        self.range = (0, 1)

    def shift(self, days):
        new = self.day + dt.timedelta(days=days)
        if new <= dt.date.today():
            self.day = new
            self.redraw()

    def today(self):
        self.day = dt.date.today()
        self.redraw()

    # -- geometry
    def x_of(self, ts):
        t0, t1 = self.range
        return self.PAD + (ts - t0) / (t1 - t0) * (self.W - 2 * self.PAD)

    def ts_of(self, x):
        t0, t1 = self.range
        return t0 + (x - self.PAD) / (self.W - 2 * self.PAD) * (t1 - t0)

    def compute_range(self, segs, planned):
        midnight = dt.datetime.combine(self.day, dt.time()).timestamp()
        if self.full_day.get():
            return midnight, midnight + 86400
        points = [s[0] for s in segs] + [s[1] for s in segs]
        points += [p for pair in planned for p in pair]
        if self.day == dt.date.today():
            points.append(dt.datetime.now().timestamp())
        if not points:
            return midnight + 8 * 3600, midnight + 18 * 3600
        lo = midnight + max(0, int((min(points) - midnight) // 3600) - 1) * 3600
        hi = midnight + min(24, int((max(points) - midnight) // 3600) + 2) * 3600
        if hi - lo < 8 * 3600:  # at least 8 hours wide so it stays readable
            hi = min(midnight + 86400, lo + 8 * 3600)
            lo = hi - 8 * 3600
        return lo, hi

    # -- drawing
    def redraw(self):
        c = self.canvas
        c.delete("all")
        self.segs = self.log.load(self.day)
        planned = self.get_planned(self.day)
        self.range = t0, t1 = self.compute_range(self.segs, planned)
        self.day_lbl.config(text="Today" if self.day == dt.date.today() else f"{self.day:%a %d %b}")

        # ruler: tick every hour, label every hour (or every 2h when zoomed out)
        hours = (t1 - t0) / 3600
        step = 1 if hours <= 12 else 2
        h_ts = t0
        i = 0
        while h_ts <= t1 + 1:
            x = self.x_of(h_ts)
            major = i % step == 0
            c.create_line(x, self.RULER_Y - (8 if major else 4), x, self.RULER_Y, fill="#999999")
            c.create_line(x, self.BAR_Y0, x, self.BAR_Y1, fill="#eeeeee")
            if major:
                c.create_text(x, 12, text=dt.datetime.fromtimestamp(h_ts).strftime("%H:%M"),
                              font=("Sans", 8, "bold" if (i // step) % 2 == 0 else ""), fill="#333333")
            h_ts += 3600
            i += 1
        c.create_line(self.PAD, self.RULER_Y, self.W - self.PAD, self.RULER_Y, fill="#cccccc")

        # planned breaks (dashed outline)
        for s, e in planned:
            c.create_rectangle(self.x_of(s), self.BAR_Y0 - 3, self.x_of(e), self.BAR_Y1 + 3,
                               outline="#8a8a8a", dash=(3, 2))

        # recorded activity
        totals = {k: 0 for k in STATES}
        for s, e, state in self.segs:
            x0, x1 = self.x_of(s), self.x_of(e)
            if x1 - x0 < 1:
                x1 = x0 + 1
            c.create_rectangle(x0, self.BAR_Y0, x1, self.BAR_Y1, fill=STATES[state][1], width=0)
            totals[state] += e - s

        # now marker
        if self.day == dt.date.today():
            x = self.x_of(dt.datetime.now().timestamp())
            c.create_line(x, self.RULER_Y, x, self.H - 6, fill="#1a73e8", width=2)

        if not self.segs:
            c.create_text(self.W / 2, (self.BAR_Y0 + self.BAR_Y1) / 2, fill="#999999",
                          text="No activity recorded" + (" yet" if self.day == dt.date.today() else ""))
        breaks = [s for s in self.segs if s[2] == "break"]
        self.totals.config(text=f"Worked {fmt_dur(totals['active'])}    "
                                f"On break {fmt_dur(totals['break'])} "
                                f"({len(breaks)} break{'s' if len(breaks) != 1 else ''})")

    def hover(self, event):
        c = self.canvas
        c.delete("tip")
        ts = self.ts_of(event.x)
        text = None
        if self.BAR_Y0 - 4 <= event.y <= self.BAR_Y1 + 4:
            for s, e, state in self.segs:
                if s <= ts <= e or abs(self.x_of(s) - event.x) < 1:
                    text = (f"{STATES[state][0]}  {dt.datetime.fromtimestamp(s):%H:%M} – "
                            f"{dt.datetime.fromtimestamp(e):%H:%M}  ({fmt_dur(e - s)})")
                    break
            if text is None:
                for s, e in self.get_planned(self.day):
                    if s <= ts <= e:
                        text = (f"Planned break  {dt.datetime.fromtimestamp(s):%H:%M} – "
                                f"{dt.datetime.fromtimestamp(e):%H:%M}")
        if text is None:
            text = dt.datetime.fromtimestamp(ts).strftime("%H:%M")
        tid = c.create_text(min(max(event.x, 110), self.W - 110), self.H - 8, text=text,
                            font=("Sans", 8), fill="white", tags="tip")
        bx = c.bbox(tid)
        c.create_rectangle(bx[0] - 4, bx[1] - 1, bx[2] + 4, bx[3] + 1, fill="#333333",
                           width=0, tags="tip")
        c.tag_raise(tid)


# ------------------------------------------------------------------ statistics
def day_summary(log, day):
    """Worked/break totals for one day, from the recorded timeline."""
    segs = log.load(day)
    worked = sum(e - s for s, e, st in segs if st == "active")
    breaks = [(s, e) for s, e, st in segs if st == "break"]
    # ignore break slivers under a minute (e.g. the moment TeamLogger restarts)
    breaks = [(s, e) for s, e in breaks if e - s >= 60]
    work_segs = [(s, e) for s, e, st in segs if st == "active"]
    tl = log.tl_total(day) if hasattr(log, "tl_total") else None
    return {
        "day": day,
        "worked": tl if tl is not None else worked,   # TeamLogger's own total wins
        "recorded": worked,
        "source": "teamlogger" if tl is not None else "recorded",
        "break": sum(e - s for s, e in breaks),
        "breaks": len(breaks),
        "first": min((s for s, _ in work_segs), default=None),
        "last": max((e for _, e in work_segs), default=None),
    }


def period_days(kind, anchor):
    """Days in the week (Mon–Sun) or month containing `anchor`."""
    if kind == "week":
        start = anchor - dt.timedelta(days=anchor.weekday())
        return [start + dt.timedelta(days=i) for i in range(7)]
    start = anchor.replace(day=1)
    nxt = (start + dt.timedelta(days=32)).replace(day=1)
    return [start + dt.timedelta(days=i) for i in range((nxt - start).days)]


def period_summary(log, kind, anchor):
    days = [day_summary(log, d) for d in period_days(kind, anchor)]
    worked_days = [d for d in days if d["worked"] >= 60]
    total = sum(d["worked"] for d in days)
    brk = sum(d["break"] for d in days)
    n_breaks = sum(d["breaks"] for d in days)
    return {
        "days": days,
        "worked": total,
        "break": brk,
        "breaks": n_breaks,
        "days_worked": len(worked_days),
        "avg_day": total / len(worked_days) if worked_days else 0,
        "avg_break": brk / n_breaks if n_breaks else 0,
    }

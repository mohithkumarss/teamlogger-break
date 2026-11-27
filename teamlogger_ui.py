"""
Interface for TeamLogger Break (GTK 4 + libadwaita).

Layout — a desktop "bento" dashboard that fits without scrolling (~920×700):

  Today   ┌──────────────── hero ───────────────┐ ┌ tiles 2×2 ┐
          │ state · countdown · progress         │ ├ 30 days   ┤
          │ day strip (work + breaks, editable)  │ ├ this week ┤
          │ actions                              │ │           │
          ├──────────── 8-week trend ────────────┤ └───────────┘
  Stats   period card (week bars / month calendar) + selected-day detail │ tiles + history

  Below ~820 px wide the two columns stack.

Visual system
  Calm, typographic. True black (light: soft grey), soft cards, heavy rounded
  numerals, grey labels. Colour carries meaning only: blue = working / today,
  amber = breaks, green/red = change. One white primary button.

Typeface: Google Sans Flex (SIL OFL 1.1), bundled in ./fonts and loaded at
runtime — see fonts/OFL.txt and fonts/TRADEMARKS.md.
"""

import datetime as dt
import glob
import math
import os
import string
import time

import teamlogger_activity as ta

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts"), "/usr/share/teamlogger-break/fonts"]
SANS = '"Google Sans Flex", "Ubuntu Sans", "Cantarell", sans-serif'
PANGO_SANS = "Google Sans Flex, Ubuntu Sans, Sans"

PALETTES = {
    "dark": dict(
        bg="#0A0A0B", card="#151517", card2="#1F1F22", card3="#2A2A2E",
        stroke="rgba(255,255,255,0.06)", ink="#F5F5F7", sec="#8E8E95", ter="#55555C",
        pos="#34C759", neg="#FF5F57", blue="#4C8DFF", amber="#FFA53A",
        shadow="rgba(0,0,0,0.0)",
    ),
    "light": dict(
        bg="#EFEFF2", card="#FFFFFF", card2="#F3F3F6", card3="#E6E6EB",
        stroke="rgba(0,0,0,0.06)", ink="#0E0E10", sec="#6B6B73", ter="#A3A3AB",
        pos="#1F9D43", neg="#D93025", blue="#2563EB", amber="#D97706",
        shadow="rgba(20,20,30,0.06)",
    ),
}

CSS = string.Template("""
window.tlb { background-color: $bg; color: $ink; font-family: $SANS; }
window.tlb toolbarview, window.tlb scrolledwindow, window.tlb viewport,
window.tlb stack { background: transparent; }
window.tlb headerbar { background: transparent; box-shadow: none; color: $ink; min-height: 54px; }

:root {
  --window-bg-color: $bg; --window-fg-color: $ink;
  --view-bg-color: $card; --view-fg-color: $ink;
  --card-bg-color: $card; --card-fg-color: $ink; --card-shade-color: $stroke;
  --dialog-bg-color: $bg; --dialog-fg-color: $ink;
  --popover-bg-color: $card2; --popover-fg-color: $ink;
  --headerbar-bg-color: $bg; --headerbar-fg-color: $ink;
  --headerbar-shade-color: transparent; --headerbar-border-color: transparent;
  --accent-bg-color: $blue; --accent-fg-color: #ffffff; --accent-color: $blue;
}
dialog, .tlb-dialog { font-family: $SANS; }

/* surfaces */
.card { background-color: $card; border-radius: 22px;
        box-shadow: 0 1px 2px $shadow, 0 8px 24px $shadow, inset 0 0 0 1px $stroke; }
.hero.work  { background-image: radial-gradient(ellipse farthest-corner at 100% 0%, alpha($blue, 0.13), transparent 55%); }
.hero.break { background-image: radial-gradient(ellipse farthest-corner at 100% 0%, alpha($amber, 0.16), transparent 55%); }

/* type scale */
.display { font-size: 76px; font-weight: 720; letter-spacing: -2.6px;
           font-feature-settings: "tnum"; font-variation-settings: "ROND" 50, "wdth" 94; }
.hero.break .display { color: $amber; }
.num-lg { font-size: 40px; font-weight: 720; letter-spacing: -1.2px;
          font-feature-settings: "tnum"; font-variation-settings: "ROND" 50, "wdth" 96; }
.num-md { font-size: 26px; font-weight: 700; letter-spacing: -0.7px;
          font-feature-settings: "tnum"; font-variation-settings: "ROND" 50, "wdth" 96; }
.num-sm { font-size: 17px; font-weight: 680; letter-spacing: -0.2px;
          font-feature-settings: "tnum"; font-variation-settings: "ROND" 50; }
.card-title { font-size: 13px; font-weight: 640; color: $sec; }
.body { font-size: 14px; font-weight: 500; color: $ink; }
.body-strong { font-size: 14px; font-weight: 650; color: $ink; }
.sub { font-size: 13px; font-weight: 500; color: $sec; }
.tiny { font-size: 12px; font-weight: 500; color: $ter; }
.unit { font-size: 14px; font-weight: 600; color: $sec; }
.pos { color: $pos; font-size: 12px; font-weight: 700; }
.neg { color: $neg; font-size: 12px; font-weight: 700; }
.icon-sec { color: $sec; }

/* state pill */
.state { border-radius: 999px; padding: 4px 12px 4px 10px; font-size: 12px; font-weight: 700; }
.state.work { color: $blue; background-color: alpha($blue, 0.13); }
.state.break { color: $amber; background-color: alpha($amber, 0.15); }
.state.off { color: $sec; background-color: $card2; }

/* buttons */
button.primary { background-color: $ink; color: $bg; border-radius: 999px; min-height: 48px; padding: 0 26px;
                 font-size: 15px; font-weight: 700; box-shadow: none; }
button.primary:hover { background-color: alpha($ink, 0.86); }
button.primary.breaking { background-color: $amber; color: #1d1100; }
button.soft { background-color: $card2; color: $ink; border-radius: 999px; min-height: 48px; padding: 0 20px;
              font-size: 14px; font-weight: 650; }
button.soft:hover { background-color: $card3; }
button.quiet { background: transparent; color: $sec; border-radius: 999px; min-height: 32px; padding: 0 12px;
               font-size: 13px; font-weight: 600; }
button.quiet:hover { background-color: $card2; color: $ink; }
button.icon-round { min-width: 36px; min-height: 36px; padding: 0; border-radius: 999px;
                    background-color: $card2; color: $ink; }
button.icon-round:hover { background-color: $card3; }
button.conn { border-radius: 999px; min-height: 30px; padding: 0 12px; font-size: 12px; font-weight: 650;
              background-color: alpha($neg, 0.12); color: $neg; }
button.conn:hover { background-color: alpha($neg, 0.2); }
button.danger { background: transparent; color: $neg; border-radius: 999px; min-height: 48px; padding: 0 22px;
                box-shadow: inset 0 0 0 1px alpha($neg, 0.5); font-weight: 650; }

/* header segmented */
.seg { background-color: $card2; border-radius: 999px; padding: 3px; }
button.segbtn { border-radius: 999px; min-height: 30px; min-width: 76px; padding: 0 14px; background: transparent;
                color: $sec; font-weight: 650; font-size: 13px; }
button.segbtn:checked { background-color: $card; color: $ink; box-shadow: 0 1px 3px rgba(0,0,0,0.25); }
.seg.compact button.segbtn { min-width: 48px; padding: 0 10px; }

/* rows */
button.row { background: transparent; border-radius: 14px; padding: 0; min-height: 0; }
button.row:hover { background-color: $card2; }
button.row.selected { background-color: $card2; }
.sep { background-color: $stroke; min-height: 1px; }

/* editor */
button.preset { border-radius: 999px; min-width: 56px; min-height: 38px; background-color: $card2;
                color: $ink; font-weight: 650; }
button.preset:checked { background-color: $ink; color: $bg; }
.big-spin { font-size: 30px; font-weight: 720; font-feature-settings: "tnum"; font-variation-settings: "ROND" 50; }
button.ampm { border-radius: 999px; min-height: 34px; padding: 0 16px; background-color: $card2; color: $sec;
              font-weight: 650; }
button.ampm:checked { background-color: $ink; color: $bg; }
.dialog-title { font-size: 26px; font-weight: 740; letter-spacing: -0.6px; }

/* motion */
@keyframes breathe { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
.state .dot { animation: breathe 2.2s ease-in-out infinite; }
.display { transition: color 450ms ease, transform 220ms cubic-bezier(0.34, 1.56, 0.64, 1); }
.display.pop { transform: scale(1.06); }
.tile { transition: transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 200ms ease; }
.tile:hover { transform: translateY(-3px);
              box-shadow: 0 10px 28px alpha(black, 0.18), inset 0 0 0 1px $stroke; }
button.primary, button.soft, button.quiet, button.segbtn, button.preset, button.conn, button.icon-round, button.row {
  transition: transform 130ms ease, background-color 180ms ease, color 180ms ease, box-shadow 180ms ease; }
button.primary:active, button.soft:active, button.preset:active, button.conn:active, button.icon-round:active {
  transform: scale(0.95); }
button.primary:hover { transform: translateY(-1px); }
""")


def render_css(pal):
    return CSS.substitute(pal, SANS=SANS)


def font_files():
    return [f for d in FONT_DIRS for f in sorted(glob.glob(os.path.join(d, "*.ttf")))]


_FC_REGISTERED = False


def register_fonts_early():
    """Make the bundled Google Sans Flex the app's font on any Linux, without installing it.

    Adds the font to fontconfig for this process only (FcConfigAppFontAddFile).
    Works with every Pango version, but must run before GTK/Pango create their
    font map, i.e. before GTK is imported. Returns True when the font was added.
    """
    global _FC_REGISTERED
    try:
        import ctypes
        import ctypes.util
        name = ctypes.util.find_library("fontconfig") or "libfontconfig.so.1"
        fc = ctypes.CDLL(name)
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        for f in font_files():
            if fc.FcConfigAppFontAddFile(None, f.encode()):
                _FC_REGISTERED = True
    except (OSError, AttributeError):
        pass
    return _FC_REGISTERED


def load_fonts():
    """Make sure the bundled Google Sans Flex is available to this process only.

    Uses the fontconfig registration from register_fonts_early() when that
    worked; otherwise Pango >= 1.56 can add the file to its font map directly.
    """
    if _FC_REGISTERED:
        return True
    import gi
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import PangoCairo
    fm = PangoCairo.FontMap.get_default()
    if not hasattr(fm, "add_font_file"):   # old Pango and no fontconfig: system fonts
        return False
    ok = False
    for f in font_files():
        try:
            ok = fm.add_font_file(f) or ok
        except Exception:
            pass
    return ok


def fmt_hm(seconds):
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def fmt_hours(seconds):
    hrs = seconds / 3600
    return f"{hrs:.1f}" if hrs < 10 else f"{hrs:.0f}"


def pct_change(now, before):
    if before <= 0:
        return None
    return round((now - before) / before * 100)


def build_ui_classes(Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango, h):
    fmt12, fmt_range = h["fmt12"], h["fmt_range"]

    # ------------------------------------------------------------ helpers
    def is_dark():
        return Adw.StyleManager.get_default().get_dark()

    def P(key, alpha=None):
        c = Gdk.RGBA()
        c.parse(PALETTES["dark" if is_dark() else "light"][key])
        if alpha is not None:
            c.alpha = alpha
        return c

    def grect(x, y, w, hh):
        return Graphene.Rect().init(x, y, w, hh)

    def gpt(x, y):
        return Graphene.Point().init(x, y)

    def rounded(x, y, w, hh, r):
        rr = Gsk.RoundedRect()
        rr.init_from_rect(grect(x, y, w, hh), max(0, min(r, w / 2, hh / 2)))
        return rr

    def fill_round(snap, col, x, y, w, hh, r):
        snap.push_rounded_clip(rounded(x, y, w, hh, r))
        snap.append_color(col, grect(x, y, w, hh))
        snap.pop()

    def stroke_round(snap, col, x, y, w, hh, r, width=1.0, dash=None):
        pb = Gsk.PathBuilder.new()
        pb.add_rounded_rect(rounded(x + width / 2, y + width / 2, w - width, hh - width, r))
        st = Gsk.Stroke.new(width)
        if dash:
            st.set_dash(dash)
        snap.append_stroke(pb.to_path(), st, col)

    def measure_text(widget, txt, size, weight):
        layout = widget.create_pango_layout(txt)
        fd = Pango.FontDescription.from_string(f"{PANGO_SANS} {size}")
        fd.set_variations(f"wght={int(weight)}")
        layout.set_font_description(fd)
        return layout

    def text(widget, snap, txt, x, y, col, size=9, weight=600, anchor="left"):
        layout = measure_text(widget, txt, size, weight)
        tw, th = layout.get_pixel_size()
        if anchor == "center":
            x -= tw / 2
        elif anchor == "right":
            x -= tw
        snap.save()
        snap.translate(gpt(x, y))
        snap.append_layout(layout, col)
        snap.restore()
        return x, tw, th

    def clear(box):
        c = box.get_first_child()
        while c:
            n = c.get_next_sibling()
            box.remove(c)
            c = n

    def card(spacing=10, pad=20, css=()):
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["card", *css])
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing,
                        margin_top=pad - 2, margin_bottom=pad, margin_start=pad, margin_end=pad)
        c.append(inner)
        return c, inner

    def title_row(title, right=None):
        r = Gtk.Box(spacing=8)
        r.append(Gtk.Label(label=title, css_classes=["card-title"], xalign=0, hexpand=True,
                           ellipsize=Pango.EllipsizeMode.END))
        if right is not None:
            r.append(right)
        return r

    def L(label="", css=(), xalign=0, ellipsize=True, **kw):
        lbl = Gtk.Label(label=label, css_classes=list(css), xalign=xalign, **kw)
        if ellipsize:
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
        return lbl

    def delta_label(pct, tip=None):
        lbl = Gtk.Label(label="" if pct is None else f"{'+' if pct >= 0 else ''}{pct}%",
                        css_classes=["pos" if (pct or 0) >= 0 else "neg"])
        if tip and pct is not None:
            lbl.set_tooltip_text(tip)
        return lbl

    # ------------------------------------------------------------ motion helpers
    def ease_out(t):
        return 1 - (1 - t) ** 3

    def animate(widget, ms, cb, frm=0.0, to=1.0, easing=None, done=None):
        target = Adw.CallbackAnimationTarget.new(cb)
        a = Adw.TimedAnimation.new(widget, frm, to, ms, target)
        a.set_easing(easing or Adw.Easing.EASE_OUT_CUBIC)
        if done:
            a.connect("done", lambda *_: done())
        a.play()
        return a

    def count_to(lbl, value, fmt, ms=700):
        """Animate a label's number from its previous value to `value`."""
        prev = getattr(lbl, "_v", None)
        lbl._v = value
        if getattr(lbl, "_anim", None):
            lbl._anim.skip()
        if prev is None or prev == value or not lbl.get_mapped():
            lbl.set_label(fmt(value))
            return
        lbl._anim = animate(lbl, ms, lambda v: lbl.set_label(fmt(prev + (value - prev) * v)))

    class Grow:
        """Mixin: a 0→1 'draw-in' progress that replays when the data changes."""
        def grow_init(self):
            self.t, self._sig, self._ga = 1.0, None, None

        def grow_if_changed(self, sig):
            if sig != self._sig:
                self._sig = sig
                self.replay()

        def replay(self, ms=900):
            if self._ga:
                self._ga.skip()
            self.t = 0.0

            def step(v):
                self.t = v
                self.queue_draw()
            self._ga = animate(self, ms, step, easing=Adw.Easing.LINEAR)

    # ------------------------------------------------------------ progress line
    class LineProgress(Gtk.Widget):
        __gtype_name__ = "TLBLineProgress2"

        def __init__(self):
            super().__init__(hexpand=True)
            self.frac, self.mode = 0.0, "work"

        def set_state(self, frac, mode):
            frac = max(0.0, min(1.0, frac or 0.0))
            if mode != self.mode or abs(frac - self.frac) > 0.02:   # jumps glide
                start, self.mode = self.frac if mode == self.mode else 0.0, mode
                if getattr(self, "_a", None):
                    self._a.skip()

                def step(v):
                    self.frac = start + (frac - start) * v
                    self.queue_draw()
                self._a = animate(self, 650, step)
            elif abs(frac - self.frac) > 1e-4:
                self.frac = frac
                self.queue_draw()

        def do_measure(self, orientation, for_size):
            return (40, 200, -1, -1) if orientation == Gtk.Orientation.HORIZONTAL else (5, 5, -1, -1)

        def do_snapshot(self, snap):
            w, hh = self.get_width(), self.get_height()
            fill_round(snap, P("card3"), 0, 0, w, hh, hh / 2)
            if self.frac > 0 and self.mode != "off":
                fill_round(snap, P("amber") if self.mode == "break" else P("blue"), 0, 0,
                           max(hh, w * self.frac), hh, hh / 2)

    # ------------------------------------------------------------ day strip
    class DayStrip(Gtk.Widget, Grow):
        """One day on a line: work (solid), recorded breaks (amber), planned breaks
        (amber outline with their time above — click to edit), now (blue)."""
        __gtype_name__ = "TLBDayStrip"
        TOP, BAR, PAD = 20, 30, 1

        def __init__(self, log, get_planned, on_planned=None, day=None):
            super().__init__(hexpand=True, has_tooltip=True)
            self.log, self.get_planned, self.on_planned = log, get_planned, on_planned
            self.day = day or dt.date.today()
            self.segs, self.range, self.blocks = [], (0, 1), []
            self.grow_init()
            self.pulse = 0.0
            self.connect("query-tooltip", self.on_tip)
            self.connect("map", lambda *_: self.start_pulse())
            if on_planned:
                g = Gtk.GestureClick()
                g.connect("released", lambda _g, _n, x, y: self.click(x, y))
                self.add_controller(g)
                self.set_cursor_from_name("pointer")
            self.refresh()

        # API kept compatible with the old TimelineView
        @property
        def area(self):
            return self

        def go_today(self):
            self.day = dt.date.today()
            self.refresh()

        def set_day(self, day):
            self.day = day
            self.refresh()

        def refresh(self):
            self.segs = self.log.load(self.day)
            self.grow_if_changed((self.day, len(self.segs)))
            self.queue_draw()

        def start_pulse(self):
            if getattr(self, "_pa", None):
                return

            def step(v):
                self.pulse = v
                if self.day == dt.date.today():
                    self.queue_draw()
            target = Adw.CallbackAnimationTarget.new(step)
            self._pa = Adw.TimedAnimation.new(self, 0.0, 1.0, 2000, target)
            self._pa.set_repeat_count(0)          # forever
            self._pa.set_easing(Adw.Easing.EASE_OUT_QUAD)
            self._pa.play()

        def do_measure(self, orientation, for_size):
            return (200, 480, -1, -1) if orientation == Gtk.Orientation.HORIZONTAL else (72, 72, -1, -1)

        def compute_range(self, planned):
            midnight = dt.datetime.combine(self.day, dt.time()).timestamp()
            pts = [q for s in self.segs for q in s[:2]] + [q for pr in planned for q in pr]
            if self.day == dt.date.today():
                pts.append(time.time())
            if not pts:
                return midnight + 9 * 3600, midnight + 19 * 3600
            lo = midnight + max(0, int((min(pts) - midnight) // 3600)) * 3600
            hi = midnight + min(24, int((max(pts) - midnight) // 3600) + 1) * 3600
            if hi - lo < 9 * 3600:
                hi = min(midnight + 86400, lo + 9 * 3600)
                lo = hi - 9 * 3600
            return lo, hi

        def x_of(self, ts, w):
            t0, t1 = self.range
            return self.PAD + (ts - t0) / (t1 - t0) * (w - 2 * self.PAD)

        def do_snapshot(self, snap):
            w = self.get_width()
            if w <= 0:
                return
            planned = self.get_planned(self.day)
            self.range = t0, t1 = self.compute_range(planned)
            y0, bh = self.TOP, self.BAR
            fill_round(snap, P("card2"), 0, y0, w, bh, 10)
            # hour grid
            hours = (t1 - t0) / 3600
            step = next((s for s in (1, 2, 3, 4, 6) if w / max(hours, 1) * s >= 52), 6)
            hts, i = t0, 0
            while hts <= t1 + 1:
                x = self.x_of(hts, w)
                if 0 < i and hts < t1:
                    snap.append_color(P("stroke"), grect(int(x), y0 + 6, 1, bh - 12))
                if i % step == 0:
                    lbl = dt.datetime.fromtimestamp(hts).strftime("%-I %p").lower()
                    text(self, snap, lbl, min(max(x, 14), w - 14), y0 + bh + 6, P("ter"), size=8, weight=560,
                         anchor="center")
                hts += 3600
                i += 1
            # work + recorded breaks (drawn in from the left)
            snap.push_clip(grect(0, 0, max(1, w * ease_out(self.t)), self.get_height()))
            for s, e, st in self.segs:
                xs, xe = self.x_of(s, w), self.x_of(e, w)
                if st == "active":
                    fill_round(snap, P("ink", 0.82), xs, y0 + 9, max(2, xe - xs), bh - 18, 6)
                else:
                    fill_round(snap, P("amber"), xs, y0 + 5, max(3, xe - xs), bh - 10, 6)
            snap.pop()
            # planned breaks + labels
            self.blocks = []
            last_label_end = -1e9
            for s, e in planned:
                xs, xe = self.x_of(s, w), self.x_of(e, w)
                bw = max(6, xe - xs)
                fill_round(snap, P("amber", 0.12), xs, y0 + 1, bw, bh - 2, 8)
                stroke_round(snap, P("amber", 0.85), xs, y0 + 1, bw, bh - 2, 8, 1.3)
                lbl = dt.datetime.fromtimestamp(s).strftime("%-I:%M")
                layout = measure_text(self, lbl, 8, 680)
                tw = layout.get_pixel_size()[0]
                lx = min(max(xs + bw / 2 - tw / 2, 0), w - tw)
                if lx > last_label_end + 6:
                    text(self, snap, lbl, lx, 2, P("amber"), size=8, weight=680)
                    last_label_end = lx + tw
                self.blocks.append((xs - 4, xs + bw + 4, s, e))
            # now
            if self.day == dt.date.today():
                x = self.x_of(time.time(), w)
                # soft radar ping around the "now" dot
                pb = Gsk.PathBuilder.new()
                pb.add_circle(gpt(x, y0 - 5), 3.5 + 9 * self.pulse)
                snap.append_fill(pb.to_path(), Gsk.FillRule.WINDING, P("blue", 0.35 * (1 - self.pulse)))
                fill_round(snap, P("blue"), x - 1.5, y0 - 4, 3, bh + 8, 1.5)
                pb = Gsk.PathBuilder.new()
                pb.add_circle(gpt(x, y0 - 5), 3.5)
                snap.append_fill(pb.to_path(), Gsk.FillRule.WINDING, P("blue"))

        def ts_at(self, x):
            t0, t1 = self.range
            w = max(1, self.get_width())
            return t0 + (x - self.PAD) / (w - 2 * self.PAD) * (t1 - t0)

        def click(self, x, y):
            for x0, x1, s, e in self.blocks:
                if x0 <= x <= x1:
                    self.on_planned(dt.datetime.fromtimestamp(s).time(), dt.datetime.fromtimestamp(e).time())
                    return

        def on_tip(self, _w, x, _y, _kb, tip):
            ts = self.ts_at(x)
            f = lambda t: fmt12(dt.datetime.fromtimestamp(t))  # noqa: E731
            for x0, x1, s, e in self.blocks:
                if x0 <= x <= x1:
                    tip.set_text(f"Planned break · {f(s)} – {f(e)}" + (" · click to edit" if self.on_planned else ""))
                    return True
            for s, e, st in self.segs:
                if s - 30 <= ts <= e + 30:
                    tip.set_text(f"{'Working' if st == 'active' else 'On break'} · {f(s)} – {f(e)} ({fmt_hm(e - s)})")
                    return True
            tip.set_text(f(ts))
            return True

    # ------------------------------------------------------------ pill grid
    class PillGrid(Gtk.Widget, Grow):
        """Days as pills. filled = full day · soft = short day · outline = workday,
        nothing recorded · dashed = day off · blue ring = today (or selected)."""
        __gtype_name__ = "TLBPillGrid2"
        GAP = 6

        def __init__(self, on_day, cols=10, header=False, max_h=22):
            super().__init__(hexpand=True, has_tooltip=True)
            self.days, self.workdays, self.on_day, self.cells = [], set(), on_day, []
            self.cols, self.header, self.max_h, self.selected = cols, header, max_h, None
            self.grow_init()
            self.connect("query-tooltip", self.on_tip)
            g = Gtk.GestureClick()
            g.connect("released", lambda _g, _n, x, y: self.click(x, y))
            self.add_controller(g)

        def set_data(self, days, workdays, selected=None):
            self.days, self.workdays, self.selected = days, workdays, selected
            self.grow_if_changed(tuple((d["day"], d["worked"] >= 60, d["worked"] >= 4 * 3600) for d in days))
            self.queue_resize()
            self.queue_draw()

        def geo(self, w):
            rows = max(1, math.ceil(len(self.days) / self.cols))
            pw = (w - self.GAP * (self.cols - 1)) / self.cols
            ph = min(self.max_h, pw * 0.6)
            return rows, pw, ph, (18 if self.header else 0)

        def do_measure(self, orientation, for_size):
            if orientation == Gtk.Orientation.HORIZONTAL:
                return 180, 360, -1, -1
            rows, _pw, ph, top = self.geo(for_size if for_size > 0 else 300)
            hh = int(top + rows * ph + (rows - 1) * self.GAP + 6)
            return hh, hh, -1, -1

        def do_snapshot(self, snap):
            w = self.get_width()
            rows, pw, ph, top = self.geo(w)
            today = dt.date.today()
            if self.header:
                for i, ch in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
                    text(self, snap, ch, i * (pw + self.GAP) + pw / 2, 0, P("ter"), size=8, weight=600,
                         anchor="center")
            self.cells = []
            for i, d in enumerate(self.days):
                r, c = divmod(i, self.cols)
                x, y = c * (pw + self.GAP), top + 3 + r * (ph + self.GAP)
                if d.get("pad"):
                    continue
                k = max(0.0, min(1.0, self.t * 1.8 - i / max(1, len(self.days)) * 0.8))
                if k <= 0:
                    continue
                snap.push_opacity(ease_out(k))
                worked = d["worked"]
                if worked >= 4 * 3600:
                    fill_round(snap, P("ink", 0.85), x, y, pw, ph, ph / 2)
                elif worked >= 60:
                    fill_round(snap, P("ink", 0.32), x, y, pw, ph, ph / 2)
                elif d["day"] > today:
                    fill_round(snap, P("card2"), x, y, pw, ph, ph / 2)
                elif d["day"].weekday() in self.workdays:
                    stroke_round(snap, P("card3"), x, y, pw, ph, ph / 2, 1.5)
                else:
                    stroke_round(snap, P("card3"), x, y, pw, ph, ph / 2, 1.5, dash=[3, 3])
                if d["day"] == (self.selected or today):
                    stroke_round(snap, P("blue"), x - 2.5, y - 2.5, pw + 5, ph + 5, (ph + 5) / 2, 2)
                snap.pop()
                self.cells.append((x, y, pw, ph, d))

        def hit(self, x, y):
            for cx, cy, w, hh, d in self.cells:
                if cx - 2 <= x <= cx + w + 2 and cy - 2 <= y <= cy + hh + 2:
                    return d
            return None

        def on_tip(self, _w, x, y, _kb, tip):
            d = self.hit(x, y)
            if not d:
                return False
            tip.set_text(f"{d['day']:%a %d %b} · " + (f"{fmt_hm(d['worked'])} worked, {d['breaks']} breaks"
                                                      if d["worked"] else "nothing recorded"))
            return True

        def click(self, x, y):
            d = self.hit(x, y)
            if d and d["day"] <= dt.date.today():
                self.on_day(d["day"])

    # ------------------------------------------------------------ area trend
    class AreaTrend(Gtk.Widget, Grow):
        __gtype_name__ = "TLBAreaTrend2"

        def __init__(self, height=110):
            super().__init__(hexpand=True, has_tooltip=True)
            self.values, self.labels, self.h = [], [], height
            self.grow_init()
            self.connect("query-tooltip", self.on_tip)

        def set_values(self, values, labels):
            self.values, self.labels = values, labels
            self.grow_if_changed((tuple(int(v // 300) for v in values), tuple(labels)))
            self.queue_draw()

        def do_measure(self, orientation, for_size):
            return (160, 400, -1, -1) if orientation == Gtk.Orientation.HORIZONTAL else (self.h, self.h, -1, -1)

        def points(self):
            w, hh = self.get_width(), self.get_height() - 18
            vals = self.values if len(self.values) >= 2 else [0, 0]
            top = max(max(vals), 1)
            n = len(vals)
            return [(8 + i * (w - 16) / (n - 1), 10 + (1 - v / top) * (hh - 16)) for i, v in enumerate(vals)]

        def do_snapshot(self, snap):
            w, hh = self.get_width(), self.get_height()
            if w <= 0:
                return
            pts = self.points()
            n = len(pts)
            base = hh - 18

            def curve(pb):
                pb.move_to(*pts[0])
                for i in range(n - 1):
                    p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
                    pb.cubic_to(p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6,
                                p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6, p2[0], p2[1])

            snap.push_clip(grect(0, 0, max(1, w * ease_out(self.t)), hh))
            pb = Gsk.PathBuilder.new()
            curve(pb)
            pb.line_to(pts[-1][0], base)
            pb.line_to(pts[0][0], base)
            pb.close()
            snap.push_fill(pb.to_path(), Gsk.FillRule.WINDING)
            try:
                s0, s1 = Gsk.ColorStop(), Gsk.ColorStop()
                s0.offset, s0.color = 0.0, P("blue", 0.30)
                s1.offset, s1.color = 1.0, P("blue", 0.0)
                snap.append_linear_gradient(grect(0, 0, w, base), gpt(0, 0), gpt(0, base), [s0, s1])
            except Exception:
                snap.append_color(P("blue", 0.12), grect(0, 0, w, base))
            snap.pop()
            pb = Gsk.PathBuilder.new()
            curve(pb)
            st = Gsk.Stroke.new(2.4)
            st.set_line_cap(Gsk.LineCap.ROUND)
            snap.append_stroke(pb.to_path(), st, P("blue"))
            for i, (x, y) in enumerate(pts):
                last = i == n - 1
                pb = Gsk.PathBuilder.new()
                pb.add_circle(gpt(x, y), 4.5 if last else 2.6)
                snap.append_fill(pb.to_path(), Gsk.FillRule.WINDING, P("blue") if last else P("card"))
                if not last:
                    pb = Gsk.PathBuilder.new()
                    pb.add_circle(gpt(x, y), 2.6)
                    snap.append_stroke(pb.to_path(), Gsk.Stroke.new(1.6), P("blue"))
                if i < len(self.labels):
                    lw = measure_text(self, self.labels[i], 8, 650).get_pixel_size()[0]
                    lx = min(max(x - lw / 2, 0), w - lw)
                    text(self, snap, self.labels[i], lx, hh - 14, P("ink" if last else "ter"), size=8,
                         weight=650 if last else 540)
            snap.pop()

        def on_tip(self, _w, x, _y, _kb, tip):
            if not self.values:
                return False
            pts = self.points()
            i = min(range(len(pts)), key=lambda k: abs(pts[k][0] - x))
            tip.set_text(f"Week of {self.labels[i] if i < len(self.labels) else ''} · {fmt_hm(self.values[i])}")
            return True

    # ------------------------------------------------------------ bars
    class ValueBars(Gtk.Widget, Grow):
        __gtype_name__ = "TLBValueBars2"

        def __init__(self, height=120, label_size=8, on_day=None, values=True):
            super().__init__(hexpand=True, has_tooltip=True)
            self.items, self.h, self.ls, self.on_day, self.show_values = [], height, label_size, on_day, values
            self.grow_init()
            self.connect("query-tooltip", self.on_tip)
            if on_day:
                g = Gtk.GestureClick()
                g.connect("released", lambda _g, _n, x, y: self.click(x))
                self.add_controller(g)

        def set_items(self, items):
            """items: [(axis_label, seconds, state, tooltip, day)]; state: 'hi' | 'sel' | ''"""
            self.items = items
            self.grow_if_changed(tuple((it[0], int(it[1] // 300)) for it in items))
            self.queue_draw()

        def do_measure(self, orientation, for_size):
            return (140, 400, -1, -1) if orientation == Gtk.Orientation.HORIZONTAL else (self.h, self.h, -1, -1)

        def slot(self):
            return self.get_width() / max(1, len(self.items))

        def do_snapshot(self, snap):
            if not self.items:
                return
            hh = self.get_height()
            slot = self.slot()
            top = max([v for _l, v, *_ in self.items] + [3600])
            label_h = 15 if self.show_values else 0
            axis_h = 18
            plot = hh - axis_h - label_h - 4
            bw = min(34, slot * 0.62)
            for i, (lbl, v, state, _t, _d) in enumerate(self.items):
                cx = slot * (i + 0.5)
                k = ease_out(max(0.0, min(1.0, self.t * 1.5 - i * 0.07)))
                bh = max(4, v / top * plot * k) if v > 0 else 4
                y = label_h + 4 + plot - bh
                if state == "sel":
                    col = P("blue")
                elif state == "hi":
                    col = P("ink", 0.9)
                else:
                    col = P("ink", 0.2) if v > 0 else P("card2")
                fill_round(snap, col, cx - bw / 2, y, bw, bh, min(7, bw / 3))
                if self.show_values and v > 0 and k > 0.6:
                    text(self, snap, fmt_hours(v), cx, y - label_h, P("ink", (0.9 if state else 0.6) * (k - 0.6) / 0.4),
                         size=self.ls, weight=700, anchor="center")
                text(self, snap, lbl, cx, hh - axis_h + 3, P("ink" if state else "ter"),
                     size=self.ls, weight=680 if state else 540, anchor="center")

        def on_tip(self, _w, x, _y, _kb, tip):
            i = int(x // self.slot()) if self.items else -1
            if 0 <= i < len(self.items) and self.items[i][3]:
                tip.set_text(self.items[i][3])
                return True
            return False

        def click(self, x):
            i = int(x // self.slot()) if self.items else -1
            if 0 <= i < len(self.items) and self.items[i][4] and self.items[i][4] <= dt.date.today():
                self.on_day(self.items[i][4])

    # ------------------------------------------------------------ data helpers
    def last_days(log, n):
        today = dt.date.today()
        return [ta.day_summary(log, today - dt.timedelta(days=i)) for i in range(n - 1, -1, -1)]

    def week_series(log, weeks):
        today = dt.date.today()
        monday = today - dt.timedelta(days=today.weekday())
        out = []
        for k in range(weeks - 1, -1, -1):
            start = monday - dt.timedelta(days=7 * k)
            out.append((start, ta.period_summary(log, "week", start)["worked"]))
        return out

    def stat_tile(icon, caption):
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["card", "tile"])
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                        margin_top=14, margin_bottom=14, margin_start=16, margin_end=14)
        top = Gtk.Box(spacing=6)
        top.append(Gtk.Image(icon_name=icon, pixel_size=14, css_classes=["icon-sec"]))
        top.append(L(caption, ["card-title"], hexpand=True))
        delta = Gtk.Label(css_classes=["pos"])
        top.append(delta)
        inner.append(top)
        val = L("", ["num-md"], margin_top=6)
        inner.append(val)
        sub = L("", ["tiny"])
        inner.append(sub)
        c.append(inner)
        c.val, c.sub, c.delta = val, sub, delta
        return c

    def responsive_columns(left_w=None, right_w=320, spacing=14):
        row = Gtk.Box(spacing=spacing, homogeneous=False)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, hexpand=True)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, width_request=right_w)
        row.append(left)
        row.append(right)
        return row, left, right

    # ------------------------------------------------------------ Stats page
    class StatsView(Gtk.Box):
        def __init__(self, win):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, margin_top=4, margin_bottom=20,
                             margin_start=20, margin_end=20)
            self.win, self.log = win, win.app.activity
            self.kind, self.anchor, self.selected = "week", dt.date.today(), dt.date.today()
            self.cols, left, right = responsive_columns(right_w=300)
            self.append(self.cols)

            # period card
            pc, pi = card(spacing=4)
            pc.set_vexpand(True)
            pi.set_vexpand(True)
            top = Gtk.Box(spacing=8)
            seg = Gtk.Box(css_classes=["seg", "compact"], valign=Gtk.Align.CENTER)
            self.week_btn = Gtk.ToggleButton(label="Week", active=True, css_classes=["segbtn"])
            self.month_btn = Gtk.ToggleButton(label="Month", group=self.week_btn, css_classes=["segbtn"])
            for b, k in ((self.week_btn, "week"), (self.month_btn, "month")):
                b.connect("toggled", lambda btn, k=k: btn.get_active() and self.set_kind(k))
                seg.append(b)
            top.append(seg)
            top.append(Gtk.Box(hexpand=True))
            prev = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["icon-round"])
            prev.connect("clicked", lambda *_: self.shift(-1))
            self.period_lbl = L("", ["body-strong"], xalign=0.5, width_chars=9, max_width_chars=14)
            self.next_btn = Gtk.Button(icon_name="go-next-symbolic", css_classes=["icon-round"])
            self.next_btn.connect("clicked", lambda *_: self.shift(1))
            top.append(prev)
            top.append(self.period_lbl)
            top.append(self.next_btn)
            pi.append(top)
            nrow = Gtk.Box(spacing=10, margin_top=14)
            self.total_lbl = L("", ["num-lg"], ellipsize=False)
            nrow.append(self.total_lbl)
            self.delta_box = Gtk.Box(valign=Gtk.Align.CENTER, margin_top=8)
            nrow.append(self.delta_box)
            pi.append(nrow)
            self.desc_lbl = L("", ["sub"])
            pi.append(self.desc_lbl)
            self.chart_stack = Gtk.Stack(margin_top=16, vhomogeneous=False, interpolate_size=True, vexpand=True)
            self.bars = ValueBars(height=168, label_size=8, on_day=self.select)
            self.bars.set_vexpand(True)
            self.month_grid = PillGrid(self.select, cols=7, header=True, max_h=26)
            self.chart_stack.add_named(self.bars, "week")
            self.chart_stack.add_named(self.month_grid, "month")
            pi.append(self.chart_stack)
            left.append(pc)

            # selected day detail
            dc, di = card(spacing=10)
            dh = Gtk.Box(spacing=8)
            self.day_title = L("", ["card-title"], hexpand=True)
            self.day_val = L("", ["body-strong"], ellipsize=False)
            dh.append(self.day_title)
            dh.append(self.day_val)
            di.append(dh)
            self.day_strip = DayStrip(self.log, win.app.planned_breaks)
            di.append(self.day_strip)
            self.day_breaks = L("", ["sub"])
            di.append(self.day_breaks)
            left.append(dc)

            # tiles
            grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
            self.t_avg = stat_tile("preferences-system-time-symbolic", "Avg / day")
            self.t_days = stat_tile("x-office-calendar-symbolic", "Days")
            self.t_brk = stat_tile("hourglass-symbolic", "Breaks")
            self.t_abrk = stat_tile("alarm-symbolic", "Avg break")
            for i, t in enumerate((self.t_avg, self.t_days, self.t_brk, self.t_abrk)):
                grid.attach(t, i % 2, i // 2, 1, 1)
            right.append(grid)

            # history (scrolls inside its card)
            hc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["card"], vexpand=True)
            hc.append(L("History", ["card-title"], margin_top=16, margin_start=18, margin_bottom=6))
            sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                    min_content_height=180, propagate_natural_height=False)
            self.hist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=6, margin_end=6, margin_bottom=8)
            sc.set_child(self.hist)
            hc.append(sc)
            right.append(hc)

        # compatibility: the app refreshes win.timeline
        @property
        def timeline(self):
            return self.day_strip

        def set_kind(self, kind):
            self.kind, self.anchor = kind, dt.date.today()
            self.refresh()

        def shift(self, n):
            if self.kind == "week":
                new = self.anchor + dt.timedelta(days=7 * n)
            else:
                m = self.anchor.month - 1 + n
                new = dt.date(self.anchor.year + m // 12, m % 12 + 1, 1)
            self.anchor = min(new, dt.date.today())
            self.refresh()

        def select(self, day):
            self.selected = day
            self.refresh()

        def refresh(self):
            today = dt.date.today()
            s = ta.period_summary(self.log, self.kind, self.anchor)
            days = [d["day"] for d in s["days"]]
            if self.kind == "week":
                prev = ta.period_summary(self.log, "week", days[0] - dt.timedelta(days=7))
                title = ("This week" if days[0] <= today <= days[-1] else
                         "Last week" if days[0] <= today - dt.timedelta(days=7) <= days[-1] else
                         f"{days[0]:%d %b} – {days[-1]:%d %b}")
            else:
                prev = ta.period_summary(self.log, "month", days[0] - dt.timedelta(days=1))
                title = "This month" if (days[0].year, days[0].month) == (today.year, today.month) \
                    else f"{days[0]:%B %Y}"
            self.period_lbl.set_label(title)
            self.next_btn.set_sensitive(days[-1] < today)
            count_to(self.total_lbl, s["worked"], fmt_hm)
            clear(self.delta_box)
            if days[-1] < today:
                self.delta_box.append(delta_label(pct_change(s["worked"], prev["worked"]), "vs. previous period"))
            self.desc_lbl.set_label(
                f"worked across {s['days_worked']} day{'s' if s['days_worked'] != 1 else ''}"
                if s["worked"] else "Nothing recorded in this period yet")
            self.chart_stack.set_visible_child_name(self.kind)
            if self.selected not in days:
                self.selected = today if today in days else max((d["day"] for d in s["days"] if d["worked"]),
                                                                default=days[-1])
            if self.kind == "week":
                self.bars.set_items([(f"{d['day']:%a}", d["worked"],
                                      "sel" if d["day"] == self.selected else "",
                                      f"{d['day']:%a %d %b} · {fmt_hm(d['worked'])} worked, {d['breaks']} breaks",
                                      d["day"]) for d in s["days"]])
            else:
                pad = [{"pad": True, "day": days[0], "worked": 0, "break": 0, "breaks": 0}] * days[0].weekday()
                self.month_grid.set_data(pad + s["days"], set(self.win.app.cfg["days"]), self.selected)

            for t, val, sub in ((self.t_avg, fmt_hm(s["avg_day"]) if s["days_worked"] else "–", "per worked day"),
                                (self.t_days, str(s["days_worked"]), f"of {len(days)}"),
                                (self.t_brk, str(s["breaks"]), fmt_hm(s["break"]) + " total"),
                                (self.t_abrk, fmt_hm(s["avg_break"]) if s["breaks"] else "–", "per break")):
                t.val.set_label(val)
                t.sub.set_label(sub)

            sd = ta.day_summary(self.log, self.selected)
            self.day_title.set_label("Today" if self.selected == today else f"{self.selected:%A, %d %B}")
            self.day_val.set_label(f"{fmt_hm(sd['worked'])} worked")
            self.day_strip.set_day(self.selected)
            brk = [(a, b) for a, b, st in self.log.load(self.selected) if st == "break" and b - a >= 60]
            f = lambda t: fmt12(dt.datetime.fromtimestamp(t))  # noqa: E731
            self.day_breaks.set_label("Breaks: " + ",  ".join(f"{f(a)} ({fmt_hm(b - a)})" for a, b in brk)
                                      if brk else "No breaks recorded")
            self.day_breaks.set_tooltip_text(self.day_breaks.get_label())

            clear(self.hist)
            rows = [d for d in reversed(s["days"]) if d["worked"] or d["break"]]
            for i, d in enumerate(rows):
                name = ("Today" if d["day"] == today else
                        "Yesterday" if d["day"] == today - dt.timedelta(days=1) else f"{d['day']:%a, %d %b}")
                b = Gtk.Button(css_classes=["row"] + (["selected"] if d["day"] == self.selected else []))
                r = Gtk.Box(spacing=10, margin_top=9, margin_bottom=9, margin_start=12, margin_end=12)
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, spacing=1)
                col.append(L(name, ["body-strong"]))
                col.append(L(f"{d['breaks']} break{'s' if d['breaks'] != 1 else ''} · {fmt_hm(d['break'])}",
                             ["tiny"]))
                r.append(col)
                r.append(L(fmt_hm(d["worked"]), ["num-sm"], ellipsize=False))
                b.set_child(r)
                b.connect("clicked", lambda _b, day=d["day"]: self.select(day))
                self.hist.append(b)
            if not rows:
                self.hist.append(L("Time is recorded while this app runs and TeamLogger is connected.",
                                   ["sub"], ellipsize=False, wrap=True, margin_start=12, margin_end=12))

        def redraw(self):
            for wdg in (self.bars, self.month_grid, self.day_strip):
                wdg.queue_draw()
            self.refresh()

    # ------------------------------------------------------------ main window
    class MainWindow(Adw.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="TeamLogger Break", css_classes=["tlb"])
            self.app = app
            self.settings_dlg = None
            self.set_default_size(960, 740)
            self.set_size_request(400, 560)
            self.connect("close-request", self.on_close)

            self.toasts = Adw.ToastOverlay()
            view = Adw.ToolbarView()
            header = Adw.HeaderBar()
            seg = Gtk.Box(css_classes=["seg"])
            self.header_seg = seg
            self.nav_today = Gtk.ToggleButton(label="Today", active=True, css_classes=["segbtn"])
            self.nav_stats = Gtk.ToggleButton(label="Stats", group=self.nav_today, css_classes=["segbtn"])
            seg.append(self.nav_today)
            seg.append(self.nav_stats)
            header.set_title_widget(seg)
            self.theme_btn = Gtk.Button(label="◐", css_classes=["icon-round"], tooltip_text="Light / dark")
            self.theme_btn.connect("clicked", lambda *_: self.app.toggle_theme())
            header.pack_start(self.theme_btn)
            header.pack_end(self.build_menu())
            gear = Gtk.Button(icon_name="emblem-system-symbolic", css_classes=["icon-round"], tooltip_text="Settings")
            gear.connect("clicked", lambda *_: self.open_settings())
            header.pack_end(gear)
            view.add_top_bar(header)

            self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=150,
                                   hhomogeneous=False, vhomogeneous=False)
            self.stack.add_named(self.scrolled(self.build_today()), "today")
            self.stats = StatsView(self)
            self.timeline = self.stats.timeline
            self.stack.add_named(self.scrolled(self.stats), "stats")
            self.nav_today.connect("toggled", lambda b: b.get_active() and self.stack.set_visible_child_name("today"))
            self.nav_stats.connect("toggled", lambda b: b.get_active() and (self.stack.set_visible_child_name("stats"),
                                                                            self.stats.refresh(),
                                                                            self.stats.bars.replay(),
                                                                            self.stats.month_grid.replay(),
                                                                            self.stats.day_strip.replay()))
            self.nav_today.connect("toggled", lambda b: b.get_active() and (self.pills.replay(), self.trend.replay(),
                                                                            self.week_bars.replay()))
            view.set_content(self.stack)
            self.toasts.set_child(view)
            self.set_content(self.toasts)

            # narrow window: stack the columns
            bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 820sp"))
            for row, right in ((self.today_cols, self.today_right), (self.stats.cols, self.stats.cols.get_last_child())):
                bp.add_setter(row, "orientation", Gtk.Orientation.VERTICAL)
                bp.add_setter(right, "width-request", -1)
            bp.add_setter(self.numrow, "orientation", Gtk.Orientation.VERTICAL)
            bp.add_setter(self.numrow, "spacing", 0)
            bp.add_setter(self.auto_lbl, "visible", False)
            bp.add_setter(self.conn_btn, "label", "Connect")
            bp.add_setter(self.theme_btn, "visible", False)
            bp.connect("apply", lambda *_: self.header_seg.add_css_class("compact"))
            bp.connect("unapply", lambda *_: self.header_seg.remove_css_class("compact"))
            for pg in (self.today_page, self.stats):
                bp.add_setter(pg, "margin-start", 12)
                bp.add_setter(pg, "margin-end", 12)
            self.add_breakpoint(bp)

        @staticmethod
        def scrolled(child):
            sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            clamp = Adw.Clamp(maximum_size=1000, tightening_threshold=900)
            clamp.set_child(child)
            sc.set_child(clamp)
            return sc

        def build_menu(self):
            menu = Gio.Menu()
            s1 = Gio.Menu()
            s1.append("Take a Break Now…", "app.break-now")
            s1.append("Skip Today's Breaks", "app.skip-today")
            menu.append_section(None, s1)
            s2 = Gio.Menu()
            s2.append("Activity Log", "app.show-log")
            s2.append("Hide Window", "app.hide")
            s2.append("Quit", "app.quit")
            menu.append_section(None, s2)
            return Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=menu, primary=True,
                                  css_classes=["icon-round"], tooltip_text="More")

        # ---- Today
        def build_today(self):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=4, margin_bottom=20,
                           margin_start=20, margin_end=20)
            self.today_page = page
            self.today_cols, left, right = responsive_columns(right_w=320)
            self.today_right = right
            page.append(self.today_cols)

            # hero
            self.hero, hi = card(spacing=0, pad=24, css=("hero", "work"))
            top = Gtk.Box(spacing=10)
            self.state = Gtk.Box(spacing=6, css_classes=["state", "work"], valign=Gtk.Align.CENTER)
            self.state_lbl = Gtk.Label()
            self.state.append(Gtk.Label(label="●", css_classes=["dot"]))
            self.state.append(self.state_lbl)
            top.append(self.state)
            top.append(Gtk.Box(hexpand=True))
            self.conn_btn = Gtk.Button(label="Connect TeamLogger", css_classes=["conn"], valign=Gtk.Align.CENTER)
            self.conn_btn.connect("clicked", lambda *_: self.app.activate_action("connect"))
            top.append(self.conn_btn)
            self.auto_lbl = L("Auto", ["sub"], ellipsize=False, margin_start=6)
            top.append(self.auto_lbl)
            self.auto_switch = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Automatic breaks")
            self.auto_switch.connect("notify::active", self.on_auto)
            top.append(self.auto_switch)
            hi.append(top)

            numrow = Gtk.Box(spacing=16, margin_top=14)
            self.numrow = numrow
            self.hero_num = L("", ["display"], ellipsize=False)
            numrow.append(self.hero_num)
            cap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2, margin_top=8)
            self.hero_cap1 = L("", ["body-strong"])
            self.hero_cap2 = L("", ["sub"])
            cap.append(self.hero_cap1)
            cap.append(self.hero_cap2)
            numrow.append(cap)
            hi.append(numrow)
            self.progress = LineProgress()
            self.progress.set_margin_top(14)
            hi.append(self.progress)

            st = Gtk.Box(margin_top=24)
            st.append(L("Your day", ["card-title"], hexpand=True))
            add = Gtk.Button(css_classes=["quiet"])
            ab = Gtk.Box(spacing=6)
            ab.append(Gtk.Image(icon_name="list-add-symbolic", pixel_size=14))
            ab.append(Gtk.Label(label="Add break"))
            add.set_child(ab)
            add.connect("clicked", lambda *_: self.break_editor())
            st.append(add)
            hi.append(st)
            self.strip = DayStrip(self.app.activity, self.app.planned_breaks,
                                  on_planned=lambda s, e: self.break_editor(s, e))
            self.strip.set_margin_top(6)
            hi.append(self.strip)

            acts = Adw.WrapBox(child_spacing=10, line_spacing=10, margin_top=22)
            self.primary = Gtk.Button(css_classes=["primary"])
            self.primary.connect("clicked", self.on_primary)
            self.ext5 = Gtk.Button(label="+5 min", css_classes=["soft"])
            self.ext5.connect("clicked", lambda *_: self.app.extend_break(5))
            self.ext10 = Gtk.Button(label="+10 min", css_classes=["soft"])
            self.ext10.connect("clicked", lambda *_: self.app.extend_break(10))
            self.skip = Gtk.Button(label="Skip today", css_classes=["soft"], tooltip_text="Skip today's remaining breaks")
            self.skip.connect("clicked", lambda *_: self.app.skip_today())
            for b in (self.primary, self.ext5, self.ext10, self.skip):
                acts.append(b)
            hi.append(acts)
            left.append(self.hero)

            # trend
            tc, ti = card(spacing=2)
            tc.set_vexpand(True)
            ti.set_vexpand(True)
            th = Gtk.Box(spacing=8)
            self.trend_title = L("Work hours · by week", ["card-title"], hexpand=True)
            th.append(self.trend_title)
            self.trend_delta = Gtk.Box()
            th.append(self.trend_delta)
            ti.append(th)
            tr = Gtk.Box(spacing=6, margin_top=4)
            self.trend_val = L("", ["num-md"], ellipsize=False)
            tr.append(self.trend_val)
            tr.append(L("this week", ["unit"], ellipsize=False, valign=Gtk.Align.END, margin_bottom=3))
            ti.append(tr)
            self.trend = AreaTrend(height=112)
            self.trend.set_vexpand(True)
            self.trend.set_margin_top(6)
            ti.append(self.trend)
            left.append(tc)

            # right column: tiles
            grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
            self.t_worked = stat_tile("preferences-system-time-symbolic", "Worked")
            self.t_breaks = stat_tile("hourglass-symbolic", "Breaks")
            self.t_week = stat_tile("x-office-calendar-symbolic", "This week")
            self.t_avg = stat_tile("power-statistics-symbolic", "30-day avg")
            for i, t in enumerate((self.t_worked, self.t_breaks, self.t_week, self.t_avg)):
                grid.attach(t, i % 2, i // 2, 1, 1)
            right.append(grid)

            mc, mi = card(spacing=12)
            self.month_lbl = L("", ["tiny"], ellipsize=False)
            mi.append(title_row("Last 30 days", self.month_lbl))
            self.pills = PillGrid(lambda d: self.show_day(d), cols=10, max_h=20)
            mi.append(self.pills)
            right.append(mc)

            wc, wi = card(spacing=6)
            wc.set_vexpand(True)
            wi.set_vexpand(True)
            self.week_delta = Gtk.Box()
            wi.append(title_row("This week · hours per day", self.week_delta))
            self.week_bars = ValueBars(height=118, label_size=7, on_day=lambda d: self.show_day(d))
            self.week_bars.set_vexpand(True)
            wi.append(self.week_bars)
            right.append(wc)
            return page

        def show_day(self, day):
            self.nav_stats.set_active(True)
            self.stats.select(day)

        # ---- live updates (every second)
        def update(self, st):
            mode = st.get("mode", "off")
            on_break = bool(self.app.active)
            if getattr(self, "_mode", None) not in (None, mode):
                self.hero_num.add_css_class("pop")
                GLib.timeout_add(220, lambda: self.hero_num.remove_css_class("pop") or False)
            self._mode = mode
            for m in ("work", "break", "off"):
                (self.hero.add_css_class if m == mode else self.hero.remove_css_class)(m)
                (self.state.add_css_class if m == mode else self.state.remove_css_class)(m)
            if mode == "break":
                s, e = self.app.active
                self.state_lbl.set_label("On break")
                self.hero_cap1.set_label("left of your break")
                self.hero_cap2.set_label(f"Back to work at {fmt12(e)}")
            elif mode == "work":
                self.state_lbl.set_label("Working")
                self.hero_cap1.set_label("until your next break")
                self.hero_cap2.set_label(st["caption"])
            else:
                self.state_lbl.set_label("Paused" if not self.app.running else "Done for today")
                self.hero_cap1.set_label("Automatic breaks are off" if not self.app.running
                                         else "No more breaks today")
                self.hero_cap2.set_label("Turn on Auto to follow your schedule" if not self.app.running else "")
            self.hero_num.set_label(st["clock"] if any(c.isdigit() for c in st["clock"]) else "—")
            self.progress.set_state(st.get("frac", 0), mode)
            self.primary.set_label("Resume work" if on_break else "Take a break now")
            self.primary.set_css_classes(["primary"] + (["breaking"] if on_break else []))
            self.ext5.set_visible(on_break)
            self.ext10.set_visible(on_break)
            self.skip.set_visible(not on_break and self.app.running and bool(self.app.next_break(dt.datetime.now())))
            if self.auto_switch.get_active() != self.app.running:
                self.auto_switch.set_active(self.app.running)
            if time.time() % 30 < 1:
                self.strip.queue_draw()

        def rebuild_breaks(self):
            self.strip.refresh()
            self.update_totals()
            if self.settings_dlg:
                self.settings_dlg.rebuild_breaks()

        def update_totals(self):
            log = self.app.activity
            today = dt.date.today()
            d = ta.day_summary(log, today)
            last = last_days(log, 30)
            worked_days = [x for x in last if x["worked"] >= 3600]
            avg = sum(x["worked"] for x in worked_days) / len(worked_days) if worked_days else 0

            count_to(self.t_worked.val, d["worked"], fmt_hm)
            self.t_worked.sub.set_label("from TeamLogger" if d.get("source") == "teamlogger" else
                                        (f"since {fmt12(dt.datetime.fromtimestamp(d['first']))}" if d["first"]
                                         else "nothing yet"))
            count_to(self.t_breaks.val, d["breaks"], lambda v: str(int(round(v))))
            self.t_breaks.sub.set_label(f"{fmt_hm(d['break'])} total · {len(self.app.breaks())} planned")
            wk = ta.period_summary(log, "week", today)
            prev = ta.period_summary(log, "week", today - dt.timedelta(days=7))
            done = today.weekday()
            this_done = sum(x["worked"] for x in wk["days"][:done])
            prev_same = sum(x["worked"] for x in prev["days"][:done])
            pct = pct_change(this_done, prev_same) if done else None
            count_to(self.t_week.val, wk["worked"], fmt_hm)
            self.t_week.sub.set_label(f"{wk['days_worked']} day{'s' if wk['days_worked'] != 1 else ''} worked")
            self.t_week.delta.set_label("" if pct is None else f"{'+' if pct >= 0 else ''}{pct}%")
            self.t_week.delta.set_css_classes(["pos" if (pct or 0) >= 0 else "neg"])
            self.t_week.delta.set_tooltip_text("Mon–yesterday vs. the same days last week" if pct is not None else None)
            if worked_days:
                count_to(self.t_avg.val, avg, fmt_hm)
            else:
                self.t_avg.val.set_label("–")
            self.t_avg.sub.set_label(f"over {len(worked_days)} days")

            self.month_lbl.set_label(f"{len(worked_days)} days worked")
            self.pills.set_data(last, set(self.app.cfg["days"]))

            series = week_series(log, 8)
            while len(series) > 4 and series[0][1] == 0:
                series = series[1:]
            self.trend.set_values([v for _s, v in series], [f"{s:%-d %b}" for s, _v in series])
            count_to(self.trend_val, series[-1][1], fmt_hm)
            clear(self.trend_delta)
            self.trend_delta.append(delta_label(pct, "Mon–yesterday vs. the same days last week"))

            self.week_bars.set_items([(f"{x['day']:%a}"[:2], x["worked"], "hi" if x["day"] == today else "",
                                       f"{x['day']:%a %d %b} · {fmt_hm(x['worked'])}", x["day"])
                                      for x in wk["days"]])
            clear(self.week_delta)
            self.strip.refresh()

        def set_connected(self, ok):
            self.conn_btn.set_visible(not ok)
            if self.settings_dlg:
                self.settings_dlg.set_connected(ok)

        def update_theme_button(self):
            pass

        def redraw(self):
            for wdg in (self.progress, self.pills, self.trend, self.week_bars, self.strip):
                wdg.queue_draw()
            self.stats.redraw()

        def toast(self, msg):
            self.toasts.add_toast(Adw.Toast(title=msg, timeout=3))

        # ---- handlers
        def on_close(self, *_):
            self.app.hide_window()
            return True

        def on_primary(self, *_):
            if self.app.active:
                self.app.end_break("Resumed early")
            else:
                self.break_now_dialog()

        def on_auto(self, sw, _p):
            if sw.get_active() != self.app.running:
                self.app.set_running(sw.get_active())

        # ---- dialogs
        def sheet(self, width=400):
            d = Adw.Dialog(content_width=width)
            d.add_css_class("tlb-dialog")
            tv = Adw.ToolbarView()
            tv.add_top_bar(Adw.HeaderBar(show_title=False))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                          margin_top=0, margin_bottom=26, margin_start=26, margin_end=26)
            tv.set_content(box)
            d.set_child(tv)
            return d, box

        def open_settings(self, page=None):
            self.settings_dlg = SettingsDialog(self)
            if page:
                self.settings_dlg.set_visible_page_name(page)
            self.settings_dlg.connect("closed", lambda *_: setattr(self, "settings_dlg", None))
            self.settings_dlg.present(self)

        def break_editor(self, s=None, e=None, parent=None):
            BreakEditor(self, s, e).present(parent or self.settings_dlg or self)

        def break_now_dialog(self):
            d, box = self.sheet()
            box.append(L("Take a break", ["dialog-title"], ellipsize=False))
            box.append(L("How long would you like?", ["sub"], ellipsize=False))
            wrap = Adw.WrapBox(child_spacing=8, line_spacing=8)
            for m in (5, 10, 15, 20, 30, 45, 60):
                b = Gtk.Button(label=f"{m} min", css_classes=["preset"])
                b.connect("clicked", lambda _b, m=m: (d.close(), self.app.break_now(m)))
                wrap.append(b)
            box.append(wrap)
            box.append(L("You can extend it any time — here or from your phone.", ["tiny"],
                         ellipsize=False, wrap=True))
            d.present(self)

        def confirm_connect(self):
            d = Adw.AlertDialog(heading="Connect TeamLogger?",
                                body="TeamLogger restarts once so this app can press its buttons. "
                                     "Its timer pauses for a few seconds.")
            d.add_response("cancel", "Cancel")
            d.add_response("ok", "Connect")
            d.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            d.connect("response", lambda _d, r: r == "ok" and self.app.connect_teamlogger())
            d.present(self.settings_dlg or self)

        def show_log(self):
            d = Adw.Dialog(title="Activity log", content_width=480, content_height=440)
            tv = Adw.ToolbarView()
            tv.add_top_bar(Adw.HeaderBar())
            txt = Gtk.TextView(editable=False, monospace=True, cursor_visible=False,
                               left_margin=16, right_margin=16, top_margin=10, bottom_margin=10)
            txt.get_buffer().set_text("\n".join(self.app.log_lines) or "Nothing yet.")
            sc = Gtk.ScrolledWindow(vexpand=True)
            sc.set_child(txt)
            tv.set_content(sc)
            d.set_child(tv)
            d.present(self.settings_dlg or self)

        def day_dialog(self, day):
            self.show_day(day)

        def phone_setup_dialog(self, parent=None):
            pc = self.app.cfg["phone"]
            d, box = self.sheet(440)
            box.append(L("Your phone", ["dialog-title"], ellipsize=False))
            box.append(Gtk.Label(wrap=True, xalign=0, use_markup=True, css_classes=["sub"], label=(
                "1.  Install <b>ntfy</b> — free on Play Store and App Store.\n"
                "2.  Tap <b>+</b> and subscribe to this topic:")))
            tc, ti = card(spacing=0, pad=8)
            tr = Gtk.Box(margin_start=10)
            tl_ = L(pc["topic"], ["num-sm"], hexpand=True, selectable=True)
            cp = Gtk.Button(icon_name="edit-copy-symbolic", css_classes=["icon-round"], valign=Gtk.Align.CENTER,
                            tooltip_text="Copy")
            cp.connect("clicked", lambda *_: (self.get_clipboard().set(pc["topic"]), self.toast("Topic copied")))
            tr.append(tl_)
            tr.append(cp)
            ti.append(tr)
            box.append(tc)
            box.append(L("3.  Press Send test — it should appear on your phone.\n\n"
                         "For a loud alarm on Android: in ntfy open the topic → Notification settings → "
                         "Urgent priority, and allow it to override Do Not Disturb.\n\n"
                         "Messages go through ntfy.sh and contain only break times. Keep the topic private — "
                         "anyone who knows it could see your breaks or press the buttons.",
                         ["tiny"], ellipsize=False, wrap=True))
            row = Gtk.Box(spacing=10)
            test = Gtk.Button(label="Send test", css_classes=["primary"], hexpand=True)

            def do_test(*_):
                if not pc.get("enabled"):
                    self.app.set_phone("enabled", True)
                    self.app.phone.start_listener()
                    if self.settings_dlg:
                        self.settings_dlg.phone_row.set_active(True)
                self.app.phone.send_test()
                self.toast("Test sent to your phone")
            test.connect("clicked", do_test)
            newt = Gtk.Button(label="New topic", css_classes=["soft"])
            newt.connect("clicked", lambda *_: (tl_.set_label(self.app.new_phone_topic()),
                                                self.toast("New topic — subscribe to it on your phone")))
            row.append(test)
            row.append(newt)
            box.append(row)
            d.present(parent or self.settings_dlg or self)

    # ------------------------------------------------------------ break editor
    class BreakEditor(Adw.Dialog):
        PRESETS = (5, 10, 15, 20, 30, 40, 45, 60, 90)

        def __init__(self, win, s=None, e=None):
            super().__init__(content_width=400)
            self.add_css_class("tlb-dialog")
            self.win, self.app, self.old = win, win.app, (s, e) if s else None
            today = dt.date.today()
            if s:
                start = s
                mins = int((dt.datetime.combine(today, e) - dt.datetime.combine(today, s)).total_seconds() // 60)
            else:
                last = self.app.breaks()[-1] if self.app.breaks() else None
                start = dt.time(min(last[1].hour + 2, 22), 0) if last else dt.time(13, 0)
                mins = 15
            tv = Adw.ToolbarView()
            tv.add_top_bar(Adw.HeaderBar(show_title=False))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                          margin_top=0, margin_bottom=26, margin_start=26, margin_end=26)
            box.append(L("Edit break" if s else "New break", ["dialog-title"], ellipsize=False))
            box.append(L("Starts at", ["card-title"]))
            trow = Gtk.Box(spacing=8)
            self.hour = Gtk.SpinButton.new_with_range(1, 12, 1)
            self.hour.set_wrap(True)
            self.hour.set_value(start.hour % 12 or 12)
            self.minute = Gtk.SpinButton.new_with_range(0, 55, 5)
            self.minute.set_wrap(True)
            self.minute.set_value(start.minute - start.minute % 5)
            self.minute.connect("output", lambda sp: (sp.set_text(f"{int(sp.get_value()):02d}"), True)[1])
            for sp in (self.hour, self.minute):
                sp.add_css_class("big-spin")
                sp.set_orientation(Gtk.Orientation.VERTICAL)
                sp.connect("value-changed", lambda *_: self.update_summary())
            trow.append(self.hour)
            trow.append(Gtk.Label(label=":", css_classes=["big-spin"]))
            trow.append(self.minute)
            ap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, margin_start=10)
            self.am = Gtk.ToggleButton(label="AM", css_classes=["ampm"])
            self.pm = Gtk.ToggleButton(label="PM", css_classes=["ampm"], group=self.am)
            (self.pm if start.hour >= 12 else self.am).set_active(True)
            for b in (self.am, self.pm):
                b.connect("toggled", lambda *_: self.update_summary())
                ap.append(b)
            trow.append(ap)
            box.append(trow)
            box.append(L("Length", ["card-title"], margin_top=4))
            wrap = Adw.WrapBox(child_spacing=8, line_spacing=8)
            self.presets, first = {}, None
            for m in self.PRESETS:
                b = Gtk.ToggleButton(label=f"{m}m", css_classes=["preset"])
                if first:
                    b.set_group(first)
                else:
                    first = b
                b.connect("toggled", lambda btn, m=m: btn.get_active() and self.set_length(m))
                wrap.append(b)
                self.presets[m] = b
            box.append(wrap)
            crow = Gtk.Box(spacing=8)
            crow.append(L("or", ["sub"], ellipsize=False))
            self.length = Gtk.SpinButton.new_with_range(1, 240, 1)
            self.length.connect("value-changed", self.on_length_spin)
            crow.append(self.length)
            crow.append(L("minutes", ["sub"], ellipsize=False))
            box.append(crow)
            self.summary = L("", ["body-strong"], margin_top=6)
            box.append(self.summary)
            btns = Gtk.Box(spacing=10, margin_top=4)
            save = Gtk.Button(label="Save", css_classes=["primary"], hexpand=True)
            save.connect("clicked", self.on_save)
            btns.append(save)
            if self.old:
                dele = Gtk.Button(label="Delete", css_classes=["danger"])
                dele.connect("clicked", self.on_delete)
                btns.append(dele)
            box.append(btns)
            tv.set_content(box)
            self.set_child(tv)
            self.set_length(mins)

        def set_length(self, mins):
            if int(self.length.get_value()) != mins:
                self.length.set_value(mins)
            self.update_summary()

        def on_length_spin(self, sp):
            mins = int(sp.get_value())
            for m, b in self.presets.items():
                if b.get_active() != (m == mins):
                    b.set_active(m == mins)
            self.update_summary()

        def values(self):
            hh = int(self.hour.get_value()) % 12 + (12 if self.pm.get_active() else 0)
            s = dt.time(hh, int(self.minute.get_value()))
            end = dt.datetime.combine(dt.date.today(), s) + dt.timedelta(minutes=int(self.length.get_value()))
            return s, end.time(), end.date() != dt.date.today()

        def update_summary(self):
            s, e, over = self.values()
            self.summary.set_label("Must end before midnight" if over else
                                   f"{fmt_range(s, e)}  ·  {int(self.length.get_value())} min")

        def on_save(self, *_):
            s, e, over = self.values()
            if over:
                self.win.toast("A break must end before midnight")
                return
            if self.old:
                self.app.remove_break(*self.old, quiet=True)
            err = self.app.add_break(s, e)
            if err:
                if self.old:
                    self.app.add_break(*self.old, quiet=True)
                self.win.toast(err)
                return
            self.close()

        def on_delete(self, *_):
            self.app.remove_break(*self.old)
            self.close()

    # ------------------------------------------------------------ settings
    class SettingsDialog(Adw.PreferencesDialog):
        def __init__(self, win):
            super().__init__(title="Settings", search_enabled=False)
            self.add_css_class("tlb-dialog")
            self.win, self.app = win, win.app
            self.add(self.page_schedule())
            self.add(self.page_phone())
            self.add(self.page_general())
            self.set_connected(bool(self.app.connected))

        def page_schedule(self):
            page = Adw.PreferencesPage(title="Schedule", icon_name="alarm-symbolic", name="schedule")
            g = Adw.PreferencesGroup()
            self.auto_row = Adw.SwitchRow(title="Automatic breaks",
                                          subtitle="Take and resume breaks in TeamLogger on schedule")
            self.auto_row.set_active(self.app.running)
            self.auto_row.connect("notify::active",
                                  lambda r, _p: r.get_active() != self.app.running and self.app.set_running(r.get_active()))
            g.add(self.auto_row)
            page.add(g)
            self.breaks_grp = Adw.PreferencesGroup(title="Breaks", description="Tap a break to change it")
            add = Gtk.Button(icon_name="list-add-symbolic", css_classes=["icon-round"], valign=Gtk.Align.CENTER,
                             tooltip_text="Add break")
            add.connect("clicked", lambda *_: self.win.break_editor(parent=self))
            self.breaks_grp.set_header_suffix(add)
            self.break_rows = []
            page.add(self.breaks_grp)
            self.rebuild_breaks()
            dg = Adw.PreferencesGroup(title="Repeat on")
            days = Gtk.Box(spacing=6, halign=Gtk.Align.START)
            self.day_btns = []
            for i, (letter, name) in enumerate(zip("MTWTFSS", ("Monday", "Tuesday", "Wednesday", "Thursday",
                                                               "Friday", "Saturday", "Sunday"))):
                b = Gtk.ToggleButton(label=letter, css_classes=["preset"], tooltip_text=name)
                b.set_size_request(42, 42)
                b.set_active(i in self.app.cfg["days"])
                b.connect("toggled", self.on_day)
                days.append(b)
                self.day_btns.append(b)
            dg.add(days)
            page.add(dg)
            return page

        def rebuild_breaks(self):
            for r in self.break_rows:
                self.breaks_grp.remove(r)
            self.break_rows = []
            today = dt.date.today()
            for s, e in self.app.breaks():
                mins = int((dt.datetime.combine(today, e) - dt.datetime.combine(today, s)).total_seconds() // 60)
                row = Adw.ActionRow(title=fmt_range(s, e), subtitle=f"{mins} minutes", activatable=True)
                row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                row.connect("activated", lambda _r, s=s, e=e: self.win.break_editor(s, e, parent=self))
                self.breaks_grp.add(row)
                self.break_rows.append(row)
            if not self.break_rows:
                row = Adw.ActionRow(title="No breaks yet", subtitle="Add one with +")
                self.breaks_grp.add(row)
                self.break_rows.append(row)

        def on_day(self, *_):
            self.app.set_cfg("days", [i for i, b in enumerate(self.day_btns) if b.get_active()])
            self.win.rebuild_breaks()
            self.win.timeline.refresh()

        def page_phone(self):
            pc = self.app.cfg["phone"]
            page = Adw.PreferencesPage(title="Phone & alarm", icon_name="phone-symbolic", name="phone")
            g = Adw.PreferencesGroup(description="Live countdown and an alarm on your phone, via the free ntfy app.")
            self.phone_row = Adw.SwitchRow(title="Phone notifications")
            self.phone_row.set_active(pc.get("enabled", False))
            self.phone_row.connect("notify::active", self.on_phone)
            g.add(self.phone_row)
            self.setup_row = Adw.ActionRow(title="Set up your phone", subtitle=f"Topic: {pc['topic']}",
                                           activatable=True)
            self.setup_row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            self.setup_row.connect("activated", lambda *_: self.win.phone_setup_dialog(parent=self))
            g.add(self.setup_row)
            page.add(g)
            a = Adw.PreferencesGroup(title="Alarm")
            opts = [0, 2, 5, 10]
            warn = Adw.ComboRow(title="Warn before the break ends",
                                model=Gtk.StringList.new(["Off", "2 minutes", "5 minutes", "10 minutes"]))
            warn.set_selected(opts.index(pc.get("warn_min", 5)) if pc.get("warn_min", 5) in opts else 2)
            warn.connect("notify::selected", lambda r, _p: self.app.set_phone("warn_min", opts[r.get_selected()]))
            a.add(warn)
            alarm = Adw.SwitchRow(title="Alarm when the break ends",
                                  subtitle="Urgent sound that repeats until you press Stop")
            alarm.set_active(pc.get("alarm", True))
            a.add(alarm)
            rep = Adw.SpinRow.new_with_range(1, 10, 1)
            rep.set_title("Rings")
            rep.set_subtitle("One minute apart")
            rep.set_value(pc.get("alarm_repeats", 3))
            rep.set_sensitive(pc.get("alarm", True))
            rep.connect("notify::value", lambda r, _p: self.app.set_phone("alarm_repeats", int(r.get_value())))
            alarm.connect("notify::active", lambda r, _p: (self.app.set_phone("alarm", r.get_active()),
                                                          rep.set_sensitive(r.get_active())))
            a.add(rep)
            lap = Adw.SwitchRow(title="Ring on this computer too")
            lap.set_active(pc.get("laptop_sound", True))
            lap.connect("notify::active", lambda r, _p: self.app.set_phone("laptop_sound", r.get_active()))
            a.add(lap)
            page.add(a)
            return page

        def on_phone(self, row, _p):
            if row.get_active() == self.app.cfg["phone"].get("enabled"):
                return
            self.app.set_phone("enabled", row.get_active())
            if row.get_active():
                self.app.phone.start_listener()
                self.app.phone.send_test()
                self.win.toast("Test notification sent to your phone")

        def page_general(self):
            page = Adw.PreferencesPage(title="General", icon_name="emblem-system-symbolic", name="general")
            ap = Adw.PreferencesGroup(title="Appearance")
            themes = ["system", "light", "dark"]
            th = Adw.ComboRow(title="Theme", model=Gtk.StringList.new(["Follow system", "Light", "Dark"]))
            th.set_selected(themes.index(self.app.cfg.get("theme", "system")))
            th.connect("notify::selected", lambda r, _p: self.app.set_theme(themes[r.get_selected()]))
            self.theme_row = th
            ap.add(th)
            page.add(ap)
            tg = Adw.PreferencesGroup(title="TeamLogger")
            self.tl_row = Adw.ActionRow(title="Connection")
            self.tl_btn = Gtk.Button(label="Connect", valign=Gtk.Align.CENTER, css_classes=["suggested-action", "pill"])
            self.tl_btn.connect("clicked", lambda *_: self.win.confirm_connect())
            self.tl_row.add_suffix(self.tl_btn)
            tg.add(self.tl_row)
            login = Adw.SwitchRow(title="Start at login", subtitle="Runs quietly in the background")
            login.set_active(self.app.cfg.get("login", False))
            login.connect("notify::active", lambda r, _p: self.app.set_login(r.get_active()))
            tg.add(login)
            test = Adw.SwitchRow(title="Test mode", subtitle="Log what would happen without clicking TeamLogger")
            test.set_active(self.app.cfg.get("dry_run", False))
            test.connect("notify::active", lambda r, _p: self.app.set_cfg("dry_run", r.get_active()))
            tg.add(test)
            log = Adw.ActionRow(title="Activity log", activatable=True)
            log.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            log.connect("activated", lambda *_: self.win.show_log())
            tg.add(log)
            page.add(tg)
            about = Adw.PreferencesGroup(title="About")
            about.add(Adw.ActionRow(title="Typeface", subtitle="Google Sans Flex · SIL Open Font License 1.1"))
            page.add(about)
            return page

        def set_connected(self, ok):
            self.tl_row.set_subtitle("Connected" if ok else "Not connected — breaks can't be clicked")
            self.tl_btn.set_visible(not ok)

    return MainWindow

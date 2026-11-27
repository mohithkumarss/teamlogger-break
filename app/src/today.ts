// Today: hero (state, countdown, progress, your day, actions), weekly trend,
// stat tiles, last 30 days, this week's bars.
import { api, type Dashboard, type DayDetail, type Status } from "./api.ts";
import { app } from "./app.ts";
import { Chart, areaTrend, dayStrip, pillGrid, valueBars } from "./charts.ts";
import { countTo, h, icon, setSwitch, switchEl } from "./dom.ts";
import { dayKey, dayShort, fmtClock, fmtDayShort, fmtHm, fmtTs, parseDay, plural, todayKey } from "./fmt.ts";

function tile(iconName: string, caption: string) {
  const delta = h("span", { class: "pos" });
  const val = h("div", { class: "num-md ellipsis" }, "–");
  const sub = h("div", { class: "tiny ellipsis" });
  const el = h("div", { class: "card tile" },
    h("div", { class: "row", style: "gap:6px" }, icon(iconName), h("span", { class: "card-title spacer ellipsis" }, caption), delta),
    val, sub);
  return { el, val, sub, delta };
}

function deltaLabel(el: HTMLElement, pct: number | null, tip?: string) {
  el.textContent = pct == null ? "" : `${pct >= 0 ? "+" : ""}${pct}%`;
  el.className = (pct ?? 0) >= 0 ? "pos" : "neg";
  if (tip && pct != null) el.dataset.tip = tip;
  else delete el.dataset.tip;
}

export class TodayView {
  readonly el: HTMLElement;
  private hero: HTMLElement;
  private state: HTMLElement;
  private stateLbl = h("span");
  private clock = h("div", { class: "display" }, "—");
  private cap1 = h("div", { class: "body-strong ellipsis" });
  private cap2 = h("div", { class: "sub ellipsis" });
  private bar = h("div", { style: "width:0%" });
  private progress = h("div", { class: "progress off" }, this.bar);
  private autoSwitch: HTMLButtonElement;
  private primary: HTMLButtonElement;
  private ext5: HTMLButtonElement;
  private ext10: HTMLButtonElement;
  private skip: HTMLButtonElement;
  private strip = new Chart();
  private trend = new Chart();
  private pills = new Chart();
  private weekBars = new Chart();
  private trendVal = h("span", { class: "num-md" }, "–");
  private trendDelta = h("span", { class: "pos" });
  private monthLbl = h("span", { class: "tiny" });
  private tWorked = tile("clock", "Worked");
  private tBreaks = tile("hourglass", "Breaks");
  private tWeek = tile("calendar", "This week");
  private tAvg = tile("chart", "30-day avg");
  private mode: string | null = null;
  private connBtn = h("button", { class: "btn conn", on: { click: () => app.connect() } },
    h("span", { class: "hide-narrow" }, "Connect TeamLogger"), h("span", { class: "show-narrow" }, "Connect"));

  constructor() {
    this.state = h("span", { class: "state off" }, h("span", { class: "dot" }), this.stateLbl);
    this.autoSwitch = switchEl(false, "Automatic breaks", (on) => app.setRunning(on));
    this.primary = h("button", { class: "btn primary", on: { click: () => this.onPrimary() } }, "Take a break now");
    this.ext5 = h("button", { class: "btn soft", hidden: true, on: { click: () => app.notYet("Extend break") } }, "+5 min");
    this.ext10 = h("button", { class: "btn soft", hidden: true, on: { click: () => app.notYet("Extend break") } }, "+10 min");
    this.skip = h("button", { class: "btn soft", title: "Skip today's remaining breaks", on: { click: () => app.skipToday() } }, "Skip today");

    this.strip.el.addEventListener("click", (e) => {
      const p = (e.target as Element).closest("[data-planned]")?.getAttribute("data-planned");
      if (!p) return;
      const [s, en] = p.split(",").map(Number);
      const hm = (ts: number) => { const d = new Date(ts * 1000); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
      app.openBreakEditor({ start: hm(s), end: hm(en) });
    });
    for (const c of [this.pills, this.weekBars])
      c.el.addEventListener("click", (e) => {
        const day = (e.target as Element).closest("[data-day]")?.getAttribute("data-day");
        if (day) app.showDay(day);
      });

    this.hero = h("section", { class: "card hero off" },
      h("div", { class: "row", style: "gap:10px" },
        this.state, h("span", { class: "spacer" }),
        this.connBtn,
        h("span", { class: "sub hide-narrow", style: "margin-left:6px" }, "Auto"),
        this.autoSwitch),
      h("div", { class: "row numrow", style: "gap:16px;margin-top:14px;align-items:center" },
        this.clock, h("div", { style: "display:flex;flex-direction:column;gap:2px;min-width:0;margin-top:8px" }, this.cap1, this.cap2)),
      this.progress,
      h("div", { class: "row", style: "margin-top:24px" },
        h("span", { class: "card-title spacer" }, "Your day"),
        h("button", { class: "btn quiet", on: { click: () => app.openBreakEditor() } }, icon("plus"), "Add break")),
      h("div", { style: "margin-top:6px" }, this.strip.el),
      h("div", { class: "actions" }, this.primary, this.ext5, this.ext10, this.skip),
    );

    const trendCard = h("section", { class: "card grow", style: "gap:2px" },
      h("div", { class: "row" }, h("span", { class: "card-title spacer" }, "Work hours · by week"), this.trendDelta),
      h("div", { class: "row", style: "gap:6px;margin-top:4px;align-items:baseline" }, this.trendVal, h("span", { class: "unit" }, "this week")),
      h("div", { style: "margin-top:6px" }, this.trend.el));

    const tiles = h("div", { class: "tiles" }, this.tWorked.el, this.tBreaks.el, this.tWeek.el, this.tAvg.el);
    const month = h("section", { class: "card", style: "gap:12px" },
      h("div", { class: "row" }, h("span", { class: "card-title spacer" }, "Last 30 days"), this.monthLbl), this.pills.el);
    const week = h("section", { class: "card grow", style: "gap:6px" },
      h("div", { class: "row" }, h("span", { class: "card-title" }, "This week · hours per day")), this.weekBars.el);

    this.el = h("div", { class: "cols" },
      h("div", { class: "col" }, this.hero, trendCard),
      h("div", { class: "col" }, tiles, month, week));
  }

  /** The Connect button shows only while TeamLogger's control port doesn't answer. */
  setConnected(ok: boolean) {
    this.connBtn.hidden = ok;
  }

  private onPrimary() {
    if (app.status?.active) app.notYet("Resume work");
    else app.openBreakNow();
  }

  /** Every second. */
  tick(st: Status) {
    const mode = st.mode;
    if (this.mode && this.mode !== mode) {
      this.clock.classList.add("pop");
      setTimeout(() => this.clock.classList.remove("pop"), 220);
    }
    this.mode = mode;
    for (const m of ["work", "break", "off"]) {
      this.hero.classList.toggle(m, m === mode);
      this.state.classList.toggle(m, m === mode);
    }
    this.progress.className = `progress ${mode}`;
    if (mode === "break") {
      this.stateLbl.textContent = "On break";
      this.cap1.textContent = "left of your break";
      this.cap2.textContent = st.caption;
    } else if (mode === "work") {
      this.stateLbl.textContent = "Working";
      this.cap1.textContent = "until your next break";
      this.cap2.textContent = st.caption;
    } else {
      this.stateLbl.textContent = st.running ? "Done for today" : "Paused";
      this.cap1.textContent = st.running ? "No more breaks ahead" : "Automatic breaks are off";
      this.cap2.textContent = st.running ? "Add one in Settings" : "Turn on Auto to follow your schedule";
    }
    this.clock.textContent = st.target ? fmtClock(st.target - Date.now() / 1000) : "—";
    this.bar.style.width = `${Math.round(st.frac * 1000) / 10}%`;
    const onBreak = !!st.active;
    this.primary.textContent = onBreak ? "Resume work" : "Take a break now";
    this.primary.classList.toggle("breaking", onBreak);
    this.ext5.hidden = this.ext10.hidden = !onBreak;
    this.skip.hidden = onBreak || !st.running || !st.can_skip;
    setSwitch(this.autoSwitch, st.running);
  }

  /** Every few seconds, and when data changes. */
  async refresh(replay = false) {
    const [d, today] = await Promise.all([api.dashboard(), api.day_detail(todayKey())]);
    this.renderTotals(d, today, replay);
  }

  private renderTotals(d: Dashboard, today: DayDetail, replay: boolean) {
    const workdays = app.cfg.days;
    this.strip.set(`${today.summary.day}|${today.segments.length}|${today.planned.join()}`,
      (w, a) => dayStrip(w, a, { day: today.summary.day, segments: today.segments, planned: today.planned, editable: true }), replay);

    const t = d.today;
    countTo(this.tWorked.val, t.worked, fmtHm);
    this.tWorked.sub.textContent = t.source === "teamlogger" ? "from TeamLogger" : t.first ? `since ${fmtTs(t.first)}` : "nothing yet";
    countTo(this.tBreaks.val, t.breaks, (v) => String(Math.round(v)));
    this.tBreaks.sub.textContent = `${fmtHm(t.break)} total · ${app.cfg.breaks.length} planned`;
    countTo(this.tWeek.val, d.week.worked, fmtHm);
    this.tWeek.sub.textContent = `${plural(d.week.days_worked, "day")} worked`;
    deltaLabel(this.tWeek.delta, d.week_change, "Mon–yesterday vs. the same days last week");
    const worked = d.last30.filter((x) => x.worked >= 3600);
    const avg = worked.length ? worked.reduce((a, x) => a + x.worked, 0) / worked.length : 0;
    if (worked.length) countTo(this.tAvg.val, avg, fmtHm);
    else this.tAvg.val.textContent = "–";
    this.tAvg.sub.textContent = `over ${plural(worked.length, "day")}`;

    this.monthLbl.textContent = `${worked.length} days worked`;
    const sig30 = d.last30.map((x) => `${x.worked >= 60 ? 1 : 0}${x.worked >= 4 * 3600 ? 1 : 0}`).join("");
    this.pills.set(sig30, (w, a) => pillGrid(w, a, { days: d.last30, workdays, cols: 10, maxH: 20 }), replay);

    const labels = d.weeks.map((x) => { const s = parseDay(x.start); return `${s.getDate()} ${s.toLocaleString("en", { month: "short" })}`; });
    const values = d.weeks.map((x) => x.worked);
    this.trend.set(values.map((v) => Math.floor(v / 300)).join(), (w, a) => areaTrend(w, a, { values, labels, height: 112 }), replay);
    countTo(this.trendVal, d.weeks.at(-1)?.worked ?? 0, fmtHm);
    deltaLabel(this.trendDelta, d.week_change, "Mon–yesterday vs. the same days last week");

    const todayK = dayKey(new Date());
    const items = d.week.days.map((x) => {
      const day = parseDay(x.day);
      return { label: dayShort(day).slice(0, 2), value: x.worked, state: x.day === todayK ? ("hi" as const) : ("" as const),
               tip: `${fmtDayShort(day)} · ${fmtHm(x.worked)}`, day: x.day };
    });
    this.weekBars.set(items.map((i) => Math.floor(i.value / 300)).join(), (w, a) => valueBars(w, a, { items, height: 118, labelSize: 10 }), replay);
  }

  replay() {
    [this.strip, this.pills, this.trend, this.weekBars].forEach((c) => c.replay());
  }
}

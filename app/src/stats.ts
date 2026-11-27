// Stats: week bars / month calendar, selected-day detail, tiles, history.
import { api, type DaySummary } from "./api.ts";
import { app } from "./app.ts";
import { Chart, dayStrip, pillGrid, valueBars } from "./charts.ts";
import { clear, countTo, h, icon, iconButton } from "./dom.ts";
import {
  addDays, dayKey, dayShort, fmtDayLong, fmtDayShort, fmtHm, fmtTs, monthName, parseDay, pctChange, plural, todayKey, weekday,
} from "./fmt.ts";

function tile(iconName: string, caption: string) {
  const val = h("div", { class: "num-md ellipsis" }, "–");
  const sub = h("div", { class: "tiny ellipsis" });
  const el = h("div", { class: "card tile" },
    h("div", { class: "row", style: "gap:6px" }, icon(iconName), h("span", { class: "card-title ellipsis" }, caption)), val, sub);
  return { el, val, sub };
}

export class StatsView {
  readonly el: HTMLElement;
  private kind: "week" | "month" = "week";
  private anchor = todayKey();
  private selected = todayKey();
  private seg: HTMLElement;
  private periodLbl = h("span", { class: "body-strong", style: "min-width:96px;text-align:center" });
  private nextBtn: HTMLButtonElement;
  private total = h("div", { class: "num-lg" }, "–");
  private delta = h("span", { class: "pos" });
  private desc = h("div", { class: "sub" });
  private bars = new Chart();
  private month = new Chart();
  private dayTitle = h("span", { class: "card-title spacer ellipsis" });
  private dayVal = h("span", { class: "body-strong" });
  private strip = new Chart();
  private dayBreaks = h("div", { class: "sub ellipsis" });
  private tAvg = tile("clock", "Avg / day");
  private tDays = tile("calendar", "Days");
  private tBrk = tile("hourglass", "Breaks");
  private tAbrk = tile("alarm", "Avg break");
  private hist = h("div", { class: "list" });

  constructor() {
    const mk = (k: "week" | "month", label: string) =>
      h("button", { class: k === "week" ? "on" : "", on: { click: () => this.setKind(k) } }, label);
    this.seg = h("div", { class: "seg compact" }, mk("week", "Week"), mk("month", "Month"));
    this.nextBtn = iconButton("next", "Next", () => this.shift(1));
    for (const c of [this.bars, this.month])
      c.el.addEventListener("click", (e) => {
        const day = (e.target as Element).closest("[data-day]")?.getAttribute("data-day");
        if (day) this.select(day);
      });

    const period = h("section", { class: "card grow", style: "gap:4px" },
      h("div", { class: "row" }, this.seg, h("span", { class: "spacer" }), iconButton("prev", "Previous", () => this.shift(-1)), this.periodLbl, this.nextBtn),
      h("div", { class: "row", style: "gap:10px;margin-top:14px;align-items:center" }, this.total, h("span", { style: "margin-top:8px" }, this.delta)),
      this.desc,
      h("div", { style: "margin-top:16px" }, this.bars.el, this.month.el));
    const day = h("section", { class: "card", style: "gap:10px" },
      h("div", { class: "row" }, this.dayTitle, this.dayVal), this.strip.el, this.dayBreaks);
    const tiles = h("div", { class: "tiles" }, this.tAvg.el, this.tDays.el, this.tBrk.el, this.tAbrk.el);
    const history = h("section", { class: "card grow history", style: "padding:16px 14px 14px" },
      h("div", { class: "card-title", style: "margin:0 4px 6px" }, "History"), this.hist);
    this.el = h("div", { class: "cols stats" }, h("div", { class: "col" }, period, day), h("div", { class: "col" }, tiles, history));
  }

  private setKind(k: "week" | "month") {
    this.kind = k;
    this.anchor = todayKey();
    this.seg.querySelectorAll("button").forEach((b, i) => b.classList.toggle("on", (i === 0) === (k === "week")));
    this.refresh(true);
  }

  private shift(n: number) {
    const a = parseDay(this.anchor);
    const next = this.kind === "week" ? addDays(a, 7 * n) : new Date(a.getFullYear(), a.getMonth() + n, 1);
    this.anchor = dayKey(next > new Date() ? new Date() : next);
    this.refresh(true);
  }

  select(day: string) {
    this.selected = day;
    const d = parseDay(day), a = parseDay(this.anchor);
    const sameWeek = dayKey(addDays(d, -weekday(d))) === dayKey(addDays(a, -weekday(a)));
    const sameMonth = d.getFullYear() === a.getFullYear() && d.getMonth() === a.getMonth();
    if (!(this.kind === "week" ? sameWeek : sameMonth)) this.anchor = day;
    this.refresh();
  }

  async refresh(replay = false) {
    const today = todayKey();
    const { summary: s, previous_worked } = await api.period(this.kind, this.anchor);
    const keys = s.days.map((d) => d.day);
    const first = parseDay(keys[0]), last = parseDay(keys.at(-1)!);
    if (this.kind === "week") {
      const lastWeek = dayKey(addDays(new Date(), -7));
      this.periodLbl.textContent = keys[0] <= today && today <= keys.at(-1)! ? "This week"
        : keys[0] <= lastWeek && lastWeek <= keys.at(-1)! ? "Last week"
        : `${first.getDate()} ${monthName(first).slice(0, 3)} – ${last.getDate()} ${monthName(last).slice(0, 3)}`;
    } else {
      const now = new Date();
      this.periodLbl.textContent = first.getFullYear() === now.getFullYear() && first.getMonth() === now.getMonth()
        ? "This month" : `${monthName(first)} ${first.getFullYear()}`;
    }
    this.nextBtn.disabled = keys.at(-1)! >= today;
    countTo(this.total, s.worked, fmtHm);
    const pct = keys.at(-1)! < today ? pctChange(s.worked, previous_worked) : null;
    this.delta.textContent = pct == null ? "" : `${pct >= 0 ? "+" : ""}${pct}%`;
    this.delta.className = (pct ?? 0) >= 0 ? "pos" : "neg";
    this.delta.dataset.tip = "vs. previous period";
    this.desc.textContent = s.worked ? `worked across ${plural(s.days_worked, "day")}` : "Nothing recorded in this period yet";

    if (!keys.includes(this.selected))
      this.selected = keys.includes(today) ? today : [...s.days].reverse().find((d) => d.worked)?.day ?? keys.at(-1)!;

    this.bars.el.hidden = this.kind !== "week";
    this.month.el.hidden = this.kind !== "month";
    const sig = `${this.kind}${this.anchor.slice(0, 7)}${keys[0]}|${s.days.map((d) => Math.floor(d.worked / 300)).join()}`;
    if (this.kind === "week") {
      const items = s.days.map((d) => {
        const day = parseDay(d.day);
        return { label: dayShort(day), value: d.worked, state: d.day === this.selected ? ("sel" as const) : ("" as const),
                 tip: `${fmtDayShort(day)} · ${fmtHm(d.worked)} worked, ${d.breaks} breaks`, day: d.day };
      });
      this.bars.set(sig, (w, a) => valueBars(w, a, { items, height: 168, labelSize: 11 }), replay);
    } else {
      const pad: (DaySummary | null)[] = Array(weekday(first)).fill(null);
      this.month.set(sig, (w, a) => pillGrid(w, a, { days: [...pad, ...s.days], workdays: app.cfg.days, selected: this.selected, cols: 7, header: true, maxH: 26 }), replay);
    }

    const tiles: [ReturnType<typeof tile>, string, string][] = [
      [this.tAvg, s.days_worked ? fmtHm(s.avg_day) : "–", "per worked day"],
      [this.tDays, String(s.days_worked), `of ${keys.length}`],
      [this.tBrk, String(s.breaks), `${fmtHm(s.break)} total`],
      [this.tAbrk, s.breaks ? fmtHm(s.avg_break) : "–", "per break"],
    ];
    for (const [t, v, sub] of tiles) { t.val.textContent = v; t.sub.textContent = sub; }

    const detail = await api.day_detail(this.selected);
    const sel = parseDay(this.selected);
    this.dayTitle.textContent = this.selected === today ? "Today" : fmtDayLong(sel);
    this.dayVal.textContent = `${fmtHm(detail.summary.worked)} worked`;
    this.strip.set(`${this.selected}|${detail.segments.length}`,
      (w, a) => dayStrip(w, a, { day: this.selected, segments: detail.segments, planned: detail.planned, editable: false }), replay);
    const brk = detail.segments.filter(([a, b, st]) => st === "break" && b - a >= 60);
    this.dayBreaks.textContent = brk.length ? "Breaks: " + brk.map(([a, b]) => `${fmtTs(a)} (${fmtHm(b - a)})`).join(",  ") : "No breaks recorded";
    this.dayBreaks.dataset.tip = this.dayBreaks.textContent;

    const yesterday = dayKey(addDays(new Date(), -1));
    const rows = [...s.days].reverse().filter((d) => d.worked || d.break);
    clear(this.hist, ...rows.map((d) =>
      h("button", { class: d.day === this.selected ? "selected" : "", on: { click: () => this.select(d.day) } },
        h("div", { style: "flex:1;display:flex;flex-direction:column;gap:1px;min-width:0" },
          h("span", { class: "body-strong ellipsis" }, d.day === today ? "Today" : d.day === yesterday ? "Yesterday" : fmtDayShort(parseDay(d.day)).replace(" ", ", ")),
          h("span", { class: "tiny" }, `${plural(d.breaks, "break")} · ${fmtHm(d.break)}`)),
        h("span", { class: "num-sm" }, fmtHm(d.worked)))));
    if (!rows.length)
      this.hist.append(h("div", { class: "sub", style: "padding:0 12px" }, "Time is recorded while this app runs and TeamLogger is connected."));
  }

  replay() {
    [this.bars, this.month, this.strip].forEach((c) => c.replay());
  }
}

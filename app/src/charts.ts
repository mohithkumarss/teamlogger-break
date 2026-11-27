// SVG charts (ports of the GTK widgets in teamlogger_ui.py). Each renderer
// returns an SVG string for a given width; `Chart` re-renders on resize and
// plays the draw-in animation only when the data changes.
import type { DaySummary, Segment } from "./api.ts";
import { fmtHm, fmtHours, fmtTs, fmtDayShort, parseDay, dayKey, weekday } from "./fmt.ts";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const mix = (v: string, pct: number) => `color-mix(in srgb, var(--${v}) ${pct}%, transparent)`;
const n = (x: number) => x.toFixed(1);

export class Chart {
  private sig = "";
  private width = 0;
  private render: (w: number, animate: boolean) => string = () => "";
  readonly el: HTMLDivElement;

  constructor(cls = "") {
    this.el = document.createElement("div");
    this.el.className = `chart ${cls}`;
    new ResizeObserver(() => {
      const w = Math.round(this.el.clientWidth);
      if (w && w !== this.width) {
        this.width = w;
        this.el.innerHTML = this.render(w, false);
      }
    }).observe(this.el);
  }

  /** Draw; animate when `sig` (a summary of the data) changed or `replay` is set. */
  set(sig: string, render: (w: number, animate: boolean) => string, replay = false) {
    const animate = replay || sig !== this.sig;
    this.sig = sig;
    this.render = render;
    this.width = Math.round(this.el.clientWidth);
    if (this.width) this.el.innerHTML = render(this.width, animate);
  }

  replay() {
    if (this.width) this.el.innerHTML = this.render(this.width, true);
  }
}

// ---------------------------------------------------------------- day strip
/** One day on a line: work (solid), recorded breaks (amber), planned breaks
 *  (amber outline + time above, clickable), now (blue with a radar ping). */
export function dayStrip(
  w: number, animate: boolean,
  d: { day: string; segments: Segment[]; planned: [number, number][]; editable: boolean },
): string {
  const TOP = 20, BAR = 30, PAD = 1, H = 72;
  const isToday = d.day === dayKey(new Date());
  const now = Date.now() / 1000;
  const midnight = parseDay(d.day).getTime() / 1000;
  const pts = [...d.segments.flatMap((s) => [s[0], s[1]]), ...d.planned.flat(), ...(isToday ? [now] : [])];
  let t0: number, t1: number;
  if (!pts.length) [t0, t1] = [midnight + 9 * 3600, midnight + 19 * 3600];
  else {
    t0 = midnight + Math.max(0, Math.floor((Math.min(...pts) - midnight) / 3600)) * 3600;
    t1 = midnight + Math.min(24, Math.floor((Math.max(...pts) - midnight) / 3600) + 1) * 3600;
    if (t1 - t0 < 9 * 3600) {
      t1 = Math.min(midnight + 86400, t0 + 9 * 3600);
      t0 = t1 - 9 * 3600;
    }
  }
  const x = (ts: number) => PAD + ((ts - t0) / (t1 - t0)) * (w - 2 * PAD);
  const out: string[] = [];
  out.push(`<rect x="0" y="${TOP}" width="${w}" height="${BAR}" rx="10" style="fill:var(--card2)"/>`);
  // hour grid + labels
  const hours = (t1 - t0) / 3600;
  const step = [1, 2, 3, 4, 6].find((s) => (w / Math.max(hours, 1)) * s >= 52) ?? 6;
  for (let i = 0, ts = t0; ts <= t1 + 1; i++, ts += 3600) {
    const xx = x(ts);
    if (i > 0 && ts < t1) out.push(`<rect x="${Math.floor(xx)}" y="${TOP + 6}" width="1" height="${BAR - 12}" style="fill:var(--stroke)"/>`);
    if (i % step === 0) {
      const dt = new Date(ts * 1000);
      const lbl = `${dt.getHours() % 12 || 12} ${dt.getHours() < 12 ? "am" : "pm"}`;
      out.push(`<text x="${n(Math.min(Math.max(xx, 14), w - 14))}" y="${TOP + BAR + 17}" text-anchor="middle" style="fill:var(--ter);font-size:11px;font-weight:560">${lbl}</text>`);
    }
  }
  // recorded work + breaks
  out.push(`<g class="${animate ? "grow-x" : ""}">`);
  for (const [s, e, st] of d.segments) {
    const xs = x(s), xe = x(e);
    const tipText = `${st === "active" ? "Working" : "On break"} · ${fmtTs(s)} – ${fmtTs(e)} (${fmtHm(e - s)})`;
    if (st === "active")
      out.push(`<rect data-tip="${esc(tipText)}" x="${n(xs)}" y="${TOP + 9}" width="${n(Math.max(2, xe - xs))}" height="${BAR - 18}" rx="6" style="fill:${mix("ink", 82)}"/>`);
    else
      out.push(`<rect data-tip="${esc(tipText)}" x="${n(xs)}" y="${TOP + 5}" width="${n(Math.max(3, xe - xs))}" height="${BAR - 10}" rx="6" style="fill:var(--amber)"/>`);
  }
  out.push("</g>");
  // planned breaks
  let lastLabelEnd = -1e9;
  for (const [s, e] of d.planned) {
    const xs = x(s), bw = Math.max(6, x(e) - xs);
    const tipText = `Planned break · ${fmtTs(s)} – ${fmtTs(e)}${d.editable ? " · click to edit" : ""}`;
    out.push(`<rect class="${d.editable ? "clickable" : ""}" data-planned="${s},${e}" data-tip="${esc(tipText)}" x="${n(xs)}" y="${TOP + 1}" width="${n(bw)}" height="${BAR - 2}" rx="8" style="fill:${mix("amber", 12)};stroke:${mix("amber", 85)};stroke-width:1.3"/>`);
    const dt = new Date(s * 1000);
    const lbl = `${dt.getHours() % 12 || 12}:${String(dt.getMinutes()).padStart(2, "0")}`;
    const tw = lbl.length * 6.4;
    const lx = Math.min(Math.max(xs + bw / 2 - tw / 2, 0), w - tw);
    if (lx > lastLabelEnd + 6) {
      out.push(`<text x="${n(lx)}" y="12" style="fill:var(--amber);font-size:11px;font-weight:680">${lbl}</text>`);
      lastLabelEnd = lx + tw;
    }
  }
  // now
  if (isToday && now >= t0 && now <= t1) {
    const xx = x(now);
    out.push(
      `<circle cx="${n(xx)}" cy="${TOP - 5}" r="3.5" style="fill:var(--blue)"><animate attributeName="r" from="3.5" to="12.5" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" from="0.35" to="0" dur="2s" repeatCount="indefinite"/></circle>`,
      `<rect x="${n(xx - 1.5)}" y="${TOP - 4}" width="3" height="${BAR + 8}" rx="1.5" style="fill:var(--blue)"/>`,
      `<circle cx="${n(xx)}" cy="${TOP - 5}" r="3.5" style="fill:var(--blue)" data-tip="Now · ${fmtTs(now)}"/>`,
    );
  }
  return `<svg width="${w}" height="${H}" viewBox="0 0 ${w} ${H}" role="img" aria-label="Timeline for ${d.day}">${out.join("")}</svg>`;
}

// ---------------------------------------------------------------- pill grid
/** Days as pills. filled = full day · soft = short day · outline = workday with
 *  nothing recorded · dashed = day off · blue ring = today (or selected). */
export function pillGrid(
  w: number, animate: boolean,
  o: { days: (DaySummary | null)[]; workdays: number[]; selected?: string; cols: number; header?: boolean; maxH: number },
): string {
  const GAP = 6;
  const rows = Math.max(1, Math.ceil(o.days.length / o.cols));
  const pw = (w - GAP * (o.cols - 1)) / o.cols;
  const ph = Math.min(o.maxH, pw * 0.6);
  const top = o.header ? 18 : 0;
  const H = Math.ceil(top + rows * ph + (rows - 1) * GAP + 6);
  const today = dayKey(new Date());
  const out: string[] = [];
  if (o.header)
    ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].forEach((c, i) =>
      out.push(`<text x="${n(i * (pw + GAP) + pw / 2)}" y="11" text-anchor="middle" style="fill:var(--ter);font-size:11px;font-weight:600">${c}</text>`));
  o.days.forEach((d, i) => {
    if (!d) return;
    const r = Math.floor(i / o.cols), c = i % o.cols;
    const x = c * (pw + GAP), y = top + 3 + r * (ph + GAP);
    const date = parseDay(d.day);
    const rx = ph / 2;
    let style: string;
    if (d.worked >= 4 * 3600) style = `fill:${mix("ink", 85)}`;
    else if (d.worked >= 60) style = `fill:${mix("ink", 32)}`;
    else if (d.day > today) style = "fill:var(--card2)";
    else if (o.workdays.includes(weekday(date))) style = "fill:none;stroke:var(--card3);stroke-width:1.5";
    else style = "fill:none;stroke:var(--card3);stroke-width:1.5;stroke-dasharray:3 3";
    const tipText = `${fmtDayShort(date)} · ${d.worked ? `${fmtHm(d.worked)} worked, ${d.breaks} breaks` : "nothing recorded"}`;
    const delay = animate ? `animation-delay:${Math.round((i / o.days.length) * 450)}ms` : "";
    const clickable = d.day <= today;
    out.push(`<g class="${animate ? "fade-in" : ""} ${clickable ? "clickable" : ""}" style="${delay}" data-day="${clickable ? d.day : ""}" data-tip="${esc(tipText)}">`);
    out.push(`<rect x="${n(x + 0.75)}" y="${n(y + 0.75)}" width="${n(pw - 1.5)}" height="${n(ph - 1.5)}" rx="${n(rx)}" style="${style}"/>`);
    if (d.day === (o.selected ?? today))
      out.push(`<rect x="${n(x - 2.5)}" y="${n(y - 2.5)}" width="${n(pw + 5)}" height="${n(ph + 5)}" rx="${n((ph + 5) / 2)}" style="fill:none;stroke:var(--blue);stroke-width:2"/>`);
    out.push("</g>");
  });
  return `<svg width="${w}" height="${H}" viewBox="0 0 ${w} ${H}">${out.join("")}</svg>`;
}

// ---------------------------------------------------------------- area trend
let gradId = 0;
export function areaTrend(w: number, animate: boolean, o: { values: number[]; labels: string[]; height: number }): string {
  const H = o.height, base = H - 18;
  const vals = o.values.length >= 2 ? o.values : [0, 0];
  const topV = Math.max(...vals, 1);
  const pts = vals.map((v, i) => [8 + (i * (w - 16)) / (vals.length - 1), 10 + (1 - v / topV) * (base - 16)]);
  let d = `M${n(pts[0][0])} ${n(pts[0][1])}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(i + 2, pts.length - 1)];
    d += ` C${n(p1[0] + (p2[0] - p0[0]) / 6)} ${n(p1[1] + (p2[1] - p0[1]) / 6)} ${n(p2[0] - (p3[0] - p1[0]) / 6)} ${n(p2[1] - (p3[1] - p1[1]) / 6)} ${n(p2[0])} ${n(p2[1])}`;
  }
  // label every k-th week so labels never collide (the latest is always shown)
  const slotW = (w - 16) / Math.max(1, pts.length - 1);
  const labelW = Math.max(...o.labels.map((l) => l.length * 6), 1) + 10;
  const every = Math.max(1, Math.ceil(labelW / slotW));
  const showLabel = (i: number) => (pts.length - 1 - i) % every === 0;
  const id = `trend${++gradId}`;
  const out: string[] = [
    `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--blue);stop-opacity:.30"/><stop offset="1" style="stop-color:var(--blue);stop-opacity:0"/></linearGradient></defs>`,
    `<g class="${animate ? "grow-x" : ""}">`,
    `<path d="${d} L${n(pts.at(-1)![0])} ${base} L${n(pts[0][0])} ${base} Z" fill="url(#${id})"/>`,
    `<path d="${d}" style="fill:none;stroke:var(--blue);stroke-width:2.4;stroke-linecap:round"/>`,
  ];
  pts.forEach(([x, y], i) => {
    const last = i === pts.length - 1;
    const tipText = `Week of ${o.labels[i] ?? ""} · ${fmtHm(o.values[i] ?? 0)}`;
    out.push(last
      ? `<circle cx="${n(x)}" cy="${n(y)}" r="4.5" style="fill:var(--blue)"/>`
      : `<circle cx="${n(x)}" cy="${n(y)}" r="2.6" style="fill:var(--card);stroke:var(--blue);stroke-width:1.6"/>`);
    out.push(`<rect x="${n(x - (w / pts.length) / 2)}" y="0" width="${n(w / pts.length)}" height="${H}" fill="transparent" data-tip="${esc(tipText)}"/>`);
    if (o.labels[i] && showLabel(i)) {
      const lw = o.labels[i].length * 6;
      const lx = Math.min(Math.max(x - lw / 2, 0), w - lw);
      out.push(`<text x="${n(lx)}" y="${H - 2}" style="fill:var(--${last ? "ink" : "ter"});font-size:11px;font-weight:${last ? 650 : 540}">${esc(o.labels[i])}</text>`);
    }
  });
  out.push("</g>");
  return `<svg width="${w}" height="${H}" viewBox="0 0 ${w} ${H}">${out.join("")}</svg>`;
}

// ---------------------------------------------------------------- bars
export interface BarItem { label: string; value: number; state: "hi" | "sel" | ""; tip: string; day?: string }

export function valueBars(w: number, animate: boolean, o: { items: BarItem[]; height: number; labelSize: number; values?: boolean }): string {
  const H = o.height, showValues = o.values !== false;
  const slot = w / Math.max(1, o.items.length);
  const topV = Math.max(...o.items.map((i) => i.value), 3600);
  const labelH = showValues ? 15 : 0, axisH = 18;
  const plot = H - axisH - labelH - 4;
  const bw = Math.min(34, slot * 0.62);
  const today = dayKey(new Date());
  const out: string[] = [];
  o.items.forEach((it, i) => {
    const cx = slot * (i + 0.5);
    const bh = it.value > 0 ? Math.max(4, (it.value / topV) * plot) : 4;
    const y = labelH + 4 + plot - bh;
    const fill = it.state === "sel" ? "var(--blue)" : it.state === "hi" ? mix("ink", 90) : it.value > 0 ? mix("ink", 20) : "var(--card2)";
    const clickable = it.day && it.day <= today;
    const delay = animate ? `animation-delay:${i * 50}ms` : "";
    out.push(`<g class="${clickable ? "clickable" : ""}" data-day="${clickable ? it.day : ""}" data-tip="${esc(it.tip)}">`);
    out.push(`<rect x="${n(slot * i)}" y="0" width="${n(slot)}" height="${H}" fill="transparent"/>`);
    out.push(`<rect class="${animate ? "grow-y" : ""}" style="${delay};fill:${fill}" x="${n(cx - bw / 2)}" y="${n(y)}" width="${n(bw)}" height="${n(bh)}" rx="${n(Math.min(7, bw / 3))}"/>`);
    if (showValues && it.value > 0)
      out.push(`<text class="${animate ? "fade-in" : ""}" style="${animate ? `animation-delay:${300 + i * 50}ms;` : ""}fill:var(--ink);fill-opacity:${it.state ? 0.9 : 0.6};font-size:${o.labelSize}px;font-weight:700" x="${n(cx)}" y="${n(y - 4)}" text-anchor="middle">${fmtHours(it.value)}</text>`);
    out.push(`<text x="${n(cx)}" y="${H - 3}" text-anchor="middle" style="fill:var(--${it.state ? "ink" : "ter"});font-size:${o.labelSize}px;font-weight:${it.state ? 680 : 540}">${esc(it.label)}</text>`);
    out.push("</g>");
  });
  return `<svg width="${w}" height="${H}" viewBox="0 0 ${w} ${H}">${out.join("")}</svg>`;
}

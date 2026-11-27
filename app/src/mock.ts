// Browser-only stand-in for the Rust core, with demo data. Mirrors the
// command results of src-tauri/src/commands.rs closely enough to design
// against; the Rust code is the reference.
import type { Api, Config, DaySummary, PeriodSummary, Segment, Status } from "./api.ts";
import { demoDay, demoTotal, DEMO_BREAKS, DEMO_DAYS } from "./demo.ts";
import { addDays, dayKey, fmtHM, fmtRangeHM, parseDay, weekday, dayName } from "./fmt.ts";

const MIN_BREAK = 60;

export function mockApi(): Api {
  const cfg: Config = {
    breaks: [...DEMO_BREAKS], days: [...DEMO_DAYS], port: 9333, dry_run: true, autostart: true,
    login: false, theme: "system",
    phone: { enabled: false, server: "https://ntfy.sh", topic: "tlb-demo0000000000", warn_min: 5,
             alarm: true, alarm_repeats: 3, laptop_sound: true },
    // ?setup=done skips the first-run screens in the browser preview
    onboarded: new URLSearchParams(location.search).get("setup") === "done",
    teamlogger_path: null, control_consent: false,
  };
  let running = cfg.autostart;
  const skipped = new Set<string>();
  const log: string[] = [];
  const say = (m: string) => log.push(`${new Date().toTimeString().slice(0, 8)}  ${m}`);
  say("Browser preview with demo data — nothing is saved.");

  const segsOf = (key: string): Segment[] => demoDay(parseDay(key), new Date(), DEMO_BREAKS, DEMO_DAYS) as Segment[];
  const daySummary = (key: string): DaySummary => {
    const segs = segsOf(key);
    const recorded = segs.filter((s) => s[2] === "active").reduce((a, s) => a + s[1] - s[0], 0);
    const brk = segs.filter((s) => s[2] === "break" && s[1] - s[0] >= MIN_BREAK);
    const work = segs.filter((s) => s[2] === "active");
    const tl = key !== dayKey(new Date()) ? demoTotal(segs as never) : null;
    return {
      day: key, worked: tl ?? recorded, recorded, source: tl != null ? "teamlogger" : "recorded",
      break: brk.reduce((a, s) => a + s[1] - s[0], 0), breaks: brk.length,
      first: work.length ? Math.min(...work.map((s) => s[0])) : null,
      last: work.length ? Math.max(...work.map((s) => s[1])) : null,
    };
  };
  const periodDays = (kind: "week" | "month", anchor: Date): Date[] => {
    if (kind === "week") {
      const start = addDays(anchor, -weekday(anchor));
      return Array.from({ length: 7 }, (_, i) => addDays(start, i));
    }
    const start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const n = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0).getDate();
    return Array.from({ length: n }, (_, i) => addDays(start, i));
  };
  const periodSummary = (kind: "week" | "month", anchor: Date): PeriodSummary => {
    const days = periodDays(kind, anchor).map((d) => daySummary(dayKey(d)));
    const wd = days.filter((d) => d.worked >= 60).length;
    const worked = days.reduce((a, d) => a + d.worked, 0);
    const brk = days.reduce((a, d) => a + d.break, 0);
    const n = days.reduce((a, d) => a + d.breaks, 0);
    return { days, worked, break: brk, breaks: n, days_worked: wd, avg_day: wd ? worked / wd : 0, avg_break: n ? brk / n : 0 };
  };
  const todaysBreaks = (day: Date): [number, number][] =>
    cfg.days.includes(weekday(day))
      ? [...cfg.breaks].sort((a, b) => a.start.localeCompare(b.start)).map((b) => {
          const t = (hm: string) => { const [h, m] = hm.split(":").map(Number); return new Date(day.getFullYear(), day.getMonth(), day.getDate(), h, m).getTime() / 1000; };
          return [t(b.start), t(b.end)];
        })
      : [];
  const status = (): Status => {
    const now = new Date(), n = now.getTime() / 1000;
    let seenNext = false;
    const today = todaysBreaks(now).map(([s, e]) => {
      const state = skipped.has(`${dayKey(now)}${s}`) ? "skipped" as const
        : e <= n ? "past" as const : s <= n ? "now" as const
        : !seenNext ? ((seenNext = true), "next" as const) : "later" as const;
      return { start: s, end: e, state };
    });
    const base = { running, target: null, frac: 0, next: null, active: null, can_skip: false,
                   planned_today: todaysBreaks(now).length, today };
    if (!running) return { ...base, mode: "off", caption: "Turn on Auto to follow your schedule", text: "Schedule is off" };
    for (let off = 0; off < 8; off++) {
      const day = addDays(now, off);
      for (const [s, e] of todaysBreaks(day)) {
        if (s <= n || skipped.has(`${dayKey(day)}${s}`)) continue;
        const when = off === 0 ? "" : `${dayName(day)} `;
        const caption = when + fmtRangeHM(hm(s), hm(e));
        let frac = 0;
        if (off === 0) {
          const ended = todaysBreaks(now).filter(([, be]) => be <= n).map(([, be]) => be);
          const first = segsOf(dayKey(now)).find((x) => x[2] === "active")?.[0];
          const b = ended.length ? Math.max(...ended) : first;
          if (b != null && b < s) frac = Math.min(1, Math.max(0, (n - b) / (s - b)));
        }
        return { ...base, mode: "work", target: s, frac, caption, text: `Next break ${caption}`, next: [s, e], can_skip: off === 0 };
      }
    }
    return { ...base, mode: "off", caption: "Add one in Settings", text: "No upcoming breaks" };
  };
  const hm = (ts: number) => { const d = new Date(ts * 1000); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const toMin = (s: string) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
  const copy = () => structuredClone(cfg);

  return {
    get_config: async () => copy(),
    update_config: async (patch) => {
      const { phone, ...rest } = patch;
      Object.assign(cfg, rest);
      if (phone) Object.assign(cfg.phone, phone);
      return copy();
    },
    add_break: async (start, end, replace) => {
      let list = cfg.breaks;
      if (replace) list = list.filter((b) => !(b.start === replace.start && b.end === replace.end));
      if (toMin(end) <= toMin(start)) throw "The end time must be after the start time";
      const clash = list.find((b) => toMin(start) < toMin(b.end) && toMin(b.start) < toMin(end));
      if (clash) throw `Overlaps with ${fmtRangeHM(clash.start, clash.end)}`;
      cfg.breaks = [...list, { start, end }];
      say(`${replace ? "Changed break to" : "Added break"} ${fmtRangeHM(start, end)}`);
      return copy();
    },
    remove_break: async (start, end) => {
      cfg.breaks = cfg.breaks.filter((b) => !(b.start === start && b.end === end));
      say(`Removed break ${fmtHM(start)}`);
      return copy();
    },
    new_phone_topic: async () => {
      cfg.phone.topic = "tlb-" + Array.from({ length: 14 }, () => "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random() * 36)]).join("");
      return copy();
    },
    status: async () => status(),
    set_running: async (on) => { running = on; cfg.autostart = on; say(on ? "Schedule on." : "Schedule off."); return status(); },
    skip_today: async () => {
      const now = new Date();
      const left = todaysBreaks(now).filter(([s]) => s > now.getTime() / 1000);
      left.forEach(([s]) => skipped.add(`${dayKey(now)}${s}`));
      return left.length;
    },
    dashboard: async () => {
      const today = new Date();
      const week = periodSummary("week", today);
      const prev = periodSummary("week", addDays(today, -7));
      const done = weekday(today);
      const sum = (p: PeriodSummary) => p.days.slice(0, done).reduce((a, d) => a + d.worked, 0);
      const monday = addDays(today, -done);
      let weeks = Array.from({ length: 8 }, (_, i) => {
        const start = addDays(monday, -7 * (7 - i));
        return { start: dayKey(start), worked: periodSummary("week", start).worked };
      });
      while (weeks.length > 4 && weeks[0].worked === 0) weeks = weeks.slice(1);
      const before = sum(prev);
      return {
        today: daySummary(dayKey(today)),
        last30: Array.from({ length: 30 }, (_, i) => daySummary(dayKey(addDays(today, i - 29)))),
        week, weeks,
        week_change: done && before > 0 ? Math.round(((sum(week) - before) / before) * 100) : null,
      };
    },
    period: async (kind, anchor) => {
      const summary = periodSummary(kind, parseDay(anchor));
      const first = parseDay(summary.days[0].day);
      const prev = periodSummary(kind, addDays(first, kind === "week" ? -7 : -1));
      return { summary, previous_worked: prev.worked };
    },
    day_detail: async (day) => ({ summary: daySummary(day), segments: segsOf(day), planned: todaysBreaks(parseDay(day)) }),
    activity_log: async () => [...log],
    not_yet: async (action) => { throw `“${action}” isn't available in this preview yet — it arrives with TeamLogger control.`; },
    teamlogger_status: async () => ({
      os: /Mac/.test(navigator.platform) ? "macos" : /Win/.test(navigator.platform) ? "windows" : "linux",
      install: cfg.teamlogger_path ? { path: cfg.teamlogger_path, how: "chosen" } : null,
      connected: false, port: cfg.port,
    }),
    set_teamlogger_path: async (path) => { cfg.teamlogger_path = path; return copy(); },
    set_breaks: async (breaks) => {
      const sorted = [...breaks].sort((a, b) => a.start.localeCompare(b.start));
      for (let i = 1; i < sorted.length; i++)
        if (toMin(sorted[i].start) < toMin(sorted[i - 1].end)) throw `Overlaps with ${fmtRangeHM(sorted[i - 1].start, sorted[i - 1].end)}`;
      cfg.breaks = sorted;
      return copy();
    },
    suggested_breaks: async () => structuredClone(DEMO_BREAKS),
    phone_qr: async () => ({
      url: `${cfg.phone.server}/${cfg.phone.topic}`,
      svg: `<svg xmlns="http://www.w3.org/2000/svg" width="184" height="184" viewBox="0 0 184 184"><rect width="184" height="184" fill="#fff"/><text x="92" y="88" text-anchor="middle" font-size="13" fill="#555">QR code appears</text><text x="92" y="106" text-anchor="middle" font-size="13" fill="#555">in the desktop app</text></svg>`,
    }),
  };
}

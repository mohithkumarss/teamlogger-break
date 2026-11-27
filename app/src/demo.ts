// Deterministic demo timeline, shared by the browser mock (src/mock.ts) and
// `npm run demo-data` (scripts/demo-data.ts, which writes real files for the
// Tauri app). Plain erasable TypeScript so Node can run it directly.

export interface DemoBreak { start: string; end: string }
export type DemoSegment = [number, number, "active" | "break"];

export const DEMO_BREAKS: DemoBreak[] = [
  { start: "11:30", end: "11:40" },
  { start: "13:00", end: "13:40" },
  { start: "17:00", end: "17:10" },
];
export const DEMO_DAYS = [0, 1, 2, 3, 4];

function rng(seed: number): () => number {
  // mulberry32
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const at = (day: Date, minutes: number) =>
  new Date(day.getFullYear(), day.getMonth(), day.getDate(), 0, minutes).getTime() / 1000;
const mins = (hm: string) => {
  const [h, m] = hm.split(":").map(Number);
  return h * 60 + m;
};

/** One day of recorded activity, cut off at `now`. Empty for days off and future days. */
export function demoDay(day: Date, now: Date, breaks = DEMO_BREAKS, workdays = DEMO_DAYS): DemoSegment[] {
  const r = rng(day.getFullYear() * 10000 + (day.getMonth() + 1) * 100 + day.getDate());
  const wd = (day.getDay() + 6) % 7;
  if (!workdays.includes(wd) || r() < 0.07) return [];
  const startMin = 9 * 60 + Math.round(r() * 60 - 25);
  const endMin = 17 * 60 + 30 + Math.round(r() * 100 - 40);
  const pauses: [number, number][] = breaks
    .map((b) => {
      const s = mins(b.start) + Math.round(r() * 6 - 2);
      return [s, s + mins(b.end) - mins(b.start) + Math.round(r() * 8 - 3)] as [number, number];
    })
    .filter(([s, e]) => s > startMin && e < endMin);
  if (r() < 0.4) {
    const s = 15 * 60 + Math.round(r() * 60);
    pauses.push([s, s + 5 + Math.round(r() * 7)]);
  }
  pauses.sort((a, b) => a[0] - b[0]);
  const segs: DemoSegment[] = [];
  let cur = startMin;
  for (const [s, e] of pauses) {
    if (s <= cur) continue;
    segs.push([at(day, cur), at(day, s), "active"], [at(day, s), at(day, e), "break"]);
    cur = e;
  }
  segs.push([at(day, cur), at(day, endMin), "active"]);
  const cut = now.getTime() / 1000;
  return segs.filter((x) => x[0] < cut).map((x) => [x[0], Math.min(x[1], cut), x[2]] as DemoSegment);
}

/** What TeamLogger itself would report for a finished day (rounded to the minute). */
export function demoTotal(segs: DemoSegment[]): number | null {
  const worked = segs.filter((s) => s[2] === "active").reduce((a, s) => a + s[1] - s[0], 0);
  return worked > 0 ? Math.round(worked / 60) * 60 : null;
}

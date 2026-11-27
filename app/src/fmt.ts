// Formatting helpers (same output as the Linux app).

export const pad2 = (n: number) => String(n).padStart(2, "0");

/** "YYYY-MM-DD" → local Date at midnight */
export function parseDay(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function dayKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

export const todayKey = () => dayKey(new Date());

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

/** Monday = 0 … Sunday = 6 */
export const weekday = (d: Date) => (d.getDay() + 6) % 7;

/** "1:05 PM" */
export function fmt12(d: Date): string {
  const h = d.getHours() % 12 || 12;
  return `${h}:${pad2(d.getMinutes())} ${d.getHours() < 12 ? "AM" : "PM"}`;
}

export const fmtTs = (ts: number) => fmt12(new Date(ts * 1000));

/** "HH:MM" → "1:00 PM" */
export function fmtHM(hm: string): string {
  const [h, m] = hm.split(":").map(Number);
  return fmt12(new Date(2000, 0, 1, h, m));
}

/** "1:00 – 1:40 PM" (drops the first AM/PM when both match) */
export function fmtRange(a: string, b: string): string {
  if (a.slice(-2) === b.slice(-2)) a = a.slice(0, -3);
  return `${a} – ${b}`;
}

export const fmtRangeHM = (s: string, e: string) => fmtRange(fmtHM(s), fmtHM(e));
export const fmtRangeTs = (s: number, e: number) => fmtRange(fmtTs(s), fmtTs(e));

/** "1:09:24" or "09:24" */
export function fmtClock(seconds: number): string {
  seconds = Math.max(0, Math.floor(seconds));
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return h ? `${h}:${pad2(m)}:${pad2(s)}` : `${pad2(m)}:${pad2(s)}`;
}

/** "7h 05m" or "45m" */
export function fmtHm(seconds: number): string {
  const total = Math.floor(seconds / 60);
  const h = Math.floor(total / 60), m = total % 60;
  return h ? `${h}h ${pad2(m)}m` : `${m}m`;
}

/** hours with one decimal under 10 ("7.5"), whole above */
export function fmtHours(seconds: number): string {
  const hrs = seconds / 3600;
  return hrs < 10 ? hrs.toFixed(1) : hrs.toFixed(0);
}

export function pctChange(now: number, before: number): number | null {
  return before > 0 ? Math.round(((now - before) / before) * 100) : null;
}

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export const dayName = (d: Date) => DAYS[weekday(d)];
export const dayShort = (d: Date) => DAYS[weekday(d)].slice(0, 3);
export const monthName = (d: Date) => MONTHS[d.getMonth()];
/** "Wed 25 Nov" */
export const fmtDayShort = (d: Date) => `${dayShort(d)} ${pad2(d.getDate())} ${monthName(d).slice(0, 3)}`;
/** "Wednesday, 25 November" */
export const fmtDayLong = (d: Date) => `${dayName(d)}, ${pad2(d.getDate())} ${monthName(d)}`;

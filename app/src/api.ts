// Bridge to the Rust core (src-tauri/src/commands.rs). Outside Tauri (plain
// browser, `npm run dev`) a mock with demo data stands in, so the UI can be
// worked on without building the app.

export type Mode = "work" | "break" | "off";

export interface Break { start: string; end: string }

export interface PhoneConfig {
  enabled: boolean; server: string; topic: string; warn_min: number;
  alarm: boolean; alarm_repeats: number; laptop_sound: boolean;
}

export interface Config {
  breaks: Break[]; days: number[]; port: number; dry_run: boolean;
  autostart: boolean; login: boolean; theme: "system" | "light" | "dark";
  phone: PhoneConfig;
  /** first-run setup finished */
  onboarded: boolean;
  /** TeamLogger picked in setup (null = auto-detect) */
  teamlogger_path: string | null;
  /** agreed that TeamLogger may restart with a local control port */
  control_consent: boolean;
}

export interface TeamLoggerStatus {
  os: "linux" | "macos" | "windows" | string;
  install: { path: string; how: "auto" | "chosen" } | null;
  connected: boolean;
  port: number;
  /** what TeamLogger is doing, read every few seconds (read-only) */
  state?: "working" | "break" | "meeting" | "unknown";
  /** TeamLogger's own total for today, seconds */
  total?: number | null;
}

export interface PhoneLink { url: string; svg: string }

export interface Status {
  mode: Mode; running: boolean; target: number | null; frac: number;
  caption: string; text: string;
  next: [number, number] | null; active: [number, number] | null;
  can_skip: boolean; planned_today: number;
  today: PlannedBreak[];
}

export type BreakState = "next" | "later" | "now" | "done" | "past" | "missed" | "skipped" | "failed";
export interface PlannedBreak { start: number; end: number; state: BreakState }

export interface DaySummary {
  day: string; worked: number; recorded: number; source: "teamlogger" | "recorded";
  break: number; breaks: number; first: number | null; last: number | null;
}

export interface PeriodSummary {
  days: DaySummary[]; worked: number; break: number; breaks: number;
  days_worked: number; avg_day: number; avg_break: number;
}

export interface Dashboard {
  today: DaySummary; last30: DaySummary[]; week: PeriodSummary;
  week_change: number | null; weeks: { start: string; worked: number }[];
}

export type Segment = [number, number, "active" | "break"];

export interface DayDetail { summary: DaySummary; segments: Segment[]; planned: [number, number][] }

export interface PeriodView { summary: PeriodSummary; previous_worked: number }

export interface Api {
  get_config(): Promise<Config>;
  update_config(patch: Partial<Omit<Config, "breaks" | "phone">> & { phone?: Partial<PhoneConfig> }): Promise<Config>;
  add_break(start: string, end: string, replace?: Break): Promise<Config>;
  remove_break(start: string, end: string): Promise<Config>;
  new_phone_topic(): Promise<Config>;
  status(): Promise<Status>;
  set_running(on: boolean): Promise<Status>;
  skip_today(): Promise<number>;
  dashboard(): Promise<Dashboard>;
  period(kind: "week" | "month", anchor: string): Promise<PeriodView>;
  day_detail(day: string): Promise<DayDetail>;
  activity_log(): Promise<string[]>;
  not_yet(action: string): Promise<void>;
  teamlogger_status(): Promise<TeamLoggerStatus>;
  /** restart TeamLogger once with its local control port (needs consent) */
  connect_teamlogger(): Promise<string>;
  set_teamlogger_path(path: string | null): Promise<Config>;
  set_breaks(breaks: Break[]): Promise<Config>;
  suggested_breaks(): Promise<Break[]>;
  phone_qr(): Promise<PhoneLink>;
}

export const inTauri = "__TAURI_INTERNALS__" in window;

async function tauriApi(): Promise<Api> {
  const { invoke } = await import("@tauri-apps/api/core");
  const call = <T>(cmd: string, args?: Record<string, unknown>) => invoke<T>(cmd, args);
  return {
    get_config: () => call("get_config"),
    update_config: (patch) => call("update_config", { patch }),
    add_break: (start, end, replace) => call("add_break", { start, end, replace: replace ?? null }),
    remove_break: (start, end) => call("remove_break", { start, end }),
    new_phone_topic: () => call("new_phone_topic"),
    status: () => call("status"),
    set_running: (on) => call("set_running", { on }),
    skip_today: () => call("skip_today"),
    dashboard: () => call("dashboard"),
    period: (kind, anchor) => call("period", { kind, anchor }),
    day_detail: (day) => call("day_detail", { day }),
    activity_log: () => call("activity_log"),
    not_yet: (action) => call("not_yet", { action }),
    teamlogger_status: () => call("teamlogger_status"),
    connect_teamlogger: () => call("connect_teamlogger"),
    set_teamlogger_path: (path) => call("set_teamlogger_path", { path }),
    set_breaks: (breaks) => call("set_breaks", { breaks }),
    suggested_breaks: () => call("suggested_breaks"),
    phone_qr: () => call("phone_qr"),
  };
}

export const api: Api = inTauri ? await tauriApi() : (await import("./mock.ts")).mockApi();

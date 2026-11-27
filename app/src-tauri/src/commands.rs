//! Commands the web UI calls (`invoke(...)` in src/api.ts).

use chrono::{Duration, Local, NaiveDate, NaiveDateTime, NaiveTime};
use serde::Serialize;
use serde_json::{Map, Value};
use tauri::State;

use crate::activity::{self, DaySummary, Period, PeriodSummary, Segment};
use crate::schedule::{self, Status};
use crate::store::{self, fmt_range, parse_hm, Config};
use crate::AppState;

type Res<T> = Result<T, String>;

fn now() -> NaiveDateTime {
    Local::now().naive_local()
}

fn today() -> NaiveDate {
    Local::now().date_naive()
}

fn hm(s: &str) -> Res<NaiveTime> {
    parse_hm(s).ok_or_else(|| format!("bad time '{s}', use HH:MM"))
}

fn date(s: &str) -> Res<NaiveDate> {
    NaiveDate::parse_from_str(s, "%Y-%m-%d").map_err(|_| format!("bad date '{s}', use YYYY-MM-DD"))
}

fn save(state: &AppState, cfg: &Config) -> Res<()> {
    store::save_config(&state.paths.config_file, cfg).map_err(|e| format!("Couldn't save settings: {e}"))
}

// ---------------------------------------------------------------- settings

#[tauri::command]
pub fn get_config(state: State<AppState>) -> Config {
    state.cfg.lock().unwrap().clone()
}

/// Change settings other than breaks, e.g. `{"theme": "dark"}` or `{"phone": {"warn_min": 2}}`.
#[tauri::command]
pub fn update_config(state: State<AppState>, patch: Map<String, Value>) -> Res<Config> {
    let mut cfg = state.cfg.lock().unwrap();
    let new = store::apply_patch(&cfg, &patch)?;
    save(&state, &new)?;
    *cfg = new;
    Ok(cfg.clone())
}

/// Add a break, or change one when `replace` gives the old start/end.
#[tauri::command]
pub fn add_break(state: State<AppState>, start: String, end: String, replace: Option<store::Break>) -> Res<Config> {
    let (s, e) = (hm(&start)?, hm(&end)?);
    let mut cfg = state.cfg.lock().unwrap();
    let mut new = cfg.clone();
    if let Some(old) = &replace {
        new.remove_break(hm(&old.start)?, hm(&old.end)?);
    }
    new.add_break(s, e)?;
    save(&state, &new)?;
    *cfg = new;
    drop(cfg);
    state.add_log(match replace {
        Some(_) => format!("Changed break to {}", fmt_range(s, e)),
        None => format!("Added break {}", fmt_range(s, e)),
    });
    Ok(state.cfg.lock().unwrap().clone())
}

#[tauri::command]
pub fn remove_break(state: State<AppState>, start: String, end: String) -> Res<Config> {
    let (s, e) = (hm(&start)?, hm(&end)?);
    let mut cfg = state.cfg.lock().unwrap();
    let mut new = cfg.clone();
    new.remove_break(s, e);
    save(&state, &new)?;
    *cfg = new;
    drop(cfg);
    state.add_log(format!("Removed break {}", fmt_range(s, e)));
    Ok(state.cfg.lock().unwrap().clone())
}

#[tauri::command]
pub fn new_phone_topic(state: State<AppState>) -> Res<Config> {
    let mut cfg = state.cfg.lock().unwrap();
    let mut new = cfg.clone();
    new.phone.topic = store::new_topic();
    save(&state, &new)?;
    *cfg = new;
    Ok(cfg.clone())
}

// ---------------------------------------------------------------- schedule

#[tauri::command]
pub fn status(state: State<AppState>) -> Status {
    let cfg = state.cfg.lock().unwrap();
    state.sched.lock().unwrap().status(&cfg, &state.log, now())
}

#[tauri::command]
pub fn set_running(state: State<AppState>, on: bool) -> Res<Status> {
    apply_running(&state, on)
}

/// Turn automatic breaks on/off and remember it (used by the UI and the tray menu).
pub fn apply_running(state: &AppState, on: bool) -> Res<Status> {
    let mut cfg = state.cfg.lock().unwrap();
    let mut new = cfg.clone();
    new.autostart = on;
    save(state, &new)?;
    *cfg = new;
    let mut sched = state.sched.lock().unwrap();
    sched.set_running(&cfg, on, now());
    let st = sched.status(&cfg, &state.log, now());
    drop((cfg, sched));
    state.add_log(if on { "Schedule on." } else { "Schedule off." });
    Ok(st)
}

#[tauri::command]
pub fn skip_today(state: State<AppState>) -> usize {
    let cfg = state.cfg.lock().unwrap();
    let n = state.sched.lock().unwrap().skip_today(&cfg, now());
    drop(cfg);
    state.add_log("Remaining breaks today will be skipped.");
    n
}

// ---------------------------------------------------------------- stats

#[derive(Serialize)]
pub struct WeekPoint {
    start: NaiveDate,
    worked: f64,
}

#[derive(Serialize)]
pub struct Dashboard {
    today: DaySummary,
    last30: Vec<DaySummary>,
    week: PeriodSummary,
    /// Mon–yesterday vs. the same days last week, in percent (None on Mondays).
    week_change: Option<i64>,
    /// Weekly totals, oldest first (leading empty weeks trimmed, at least 4).
    weeks: Vec<WeekPoint>,
}

pub fn pct_change(now: f64, before: f64) -> Option<i64> {
    (before > 0.0).then(|| ((now - before) / before * 100.0).round() as i64)
}

#[tauri::command]
pub fn dashboard(state: State<AppState>) -> Dashboard {
    use chrono::Datelike;
    if !state.ui_seen.swap(true, std::sync::atomic::Ordering::Relaxed) {
        state.add_log("Window connected");
    }
    let log = &state.log;
    let today = today();
    let week = activity::period_summary(log, Period::Week, today);
    let prev = activity::period_summary(log, Period::Week, today - Duration::days(7));
    let done = today.weekday().num_days_from_monday() as usize;
    let this_done: f64 = week.days[..done].iter().map(|d| d.worked).sum();
    let prev_same: f64 = prev.days[..done].iter().map(|d| d.worked).sum();
    let monday = today - Duration::days(done as i64);
    let mut weeks: Vec<WeekPoint> = (0..8)
        .rev()
        .map(|k| {
            let start = monday - Duration::days(7 * k);
            WeekPoint { start, worked: activity::period_summary(log, Period::Week, start).worked }
        })
        .collect();
    while weeks.len() > 4 && weeks[0].worked == 0.0 {
        weeks.remove(0);
    }
    Dashboard {
        today: activity::day_summary(log, today),
        last30: (0..30).rev().map(|i| activity::day_summary(log, today - Duration::days(i))).collect(),
        week_change: if done > 0 { pct_change(this_done, prev_same) } else { None },
        week,
        weeks,
    }
}

#[derive(Serialize)]
pub struct PeriodView {
    summary: PeriodSummary,
    previous_worked: f64,
}

#[tauri::command]
pub fn period(state: State<AppState>, kind: Period, anchor: String) -> Res<PeriodView> {
    let anchor = date(&anchor)?;
    let summary = activity::period_summary(&state.log, kind, anchor);
    let first = summary.days[0].day;
    let prev_anchor = match kind {
        Period::Week => first - Duration::days(7),
        Period::Month => first - Duration::days(1),
    };
    let previous_worked = activity::period_summary(&state.log, kind, prev_anchor).worked;
    Ok(PeriodView { summary, previous_worked })
}

#[derive(Serialize)]
pub struct DayDetail {
    summary: DaySummary,
    segments: Vec<Segment>,
    /// Planned breaks that day as (start, end) Unix times.
    planned: Vec<(f64, f64)>,
}

#[tauri::command]
pub fn day_detail(state: State<AppState>, day: String) -> Res<DayDetail> {
    let day = date(&day)?;
    let cfg = state.cfg.lock().unwrap();
    let planned = schedule::todays_breaks(&cfg, day).into_iter().map(|(s, e)| (schedule::ts(s), schedule::ts(e))).collect();
    drop(cfg);
    Ok(DayDetail { summary: activity::day_summary(&state.log, day), segments: state.log.load(day), planned })
}

#[tauri::command]
pub fn activity_log(state: State<AppState>) -> Vec<String> {
    state.log_lines.lock().unwrap().clone()
}

/// Actions that need TeamLogger control, the tray or the phone module, which
/// later milestones add. Returns an error the UI shows as a toast.
#[tauri::command]
pub fn not_yet(action: String) -> Res<()> {
    Err(format!("“{action}” isn't available in this preview yet — it arrives with TeamLogger control."))
}

// ---------------------------------------------------------------- setup

#[derive(Serialize)]
pub struct TeamLoggerStatus {
    /// "linux" | "macos" | "windows"
    os: &'static str,
    install: Option<crate::teamlogger::Install>,
    /// The control port answers (TeamLogger is running with it open).
    connected: bool,
    port: u16,
    /// "working" | "break" | "meeting" | "unknown" (from the poller)
    state: &'static str,
    /// TeamLogger's total for today, seconds
    total: Option<f64>,
}

#[tauri::command]
pub async fn teamlogger_status(state: State<'_, AppState>) -> Res<TeamLoggerStatus> {
    let (chosen, port) = {
        let cfg = state.cfg.lock().unwrap();
        (cfg.teamlogger_path.clone(), cfg.port)
    };
    let live = state.live.lock().unwrap().clone();
    // file system + a local socket: keep it off the UI thread
    tauri::async_runtime::spawn_blocking(move || {
        let connected = crate::teamlogger::control_port_open(port);
        TeamLoggerStatus {
            os: std::env::consts::OS,
            install: crate::teamlogger::find(chosen.as_deref()),
            connected,
            port,
            state: if connected { live.state } else { "unknown" },
            total: live.total,
        }
    })
    .await
    .map_err(|e| e.to_string())
}

/// "Connect": restart TeamLogger once with its local control port. Needs the
/// consent given in setup; takes up to a minute.
#[tauri::command]
pub async fn connect_teamlogger(app: tauri::AppHandle) -> Res<String> {
    use tauri::Manager;
    let (chosen, port, consent) = {
        let state = app.state::<AppState>();
        let cfg = state.cfg.lock().unwrap();
        (cfg.teamlogger_path.clone(), cfg.port, cfg.control_consent)
    };
    let install = crate::teamlogger::find(chosen.as_deref())
        .ok_or("TeamLogger wasn't found — choose it in Settings → General")?;
    let app2 = app.clone();
    let res = tauri::async_runtime::spawn_blocking(move || {
        let log = |m: String| app2.state::<AppState>().add_log(m);
        crate::launch::connect(&install.path, port, consent, &log)
    })
    .await
    .map_err(|e| e.to_string())?;
    app.state::<AppState>().add_log(match &res {
        Ok(m) => m.clone(),
        Err(e) => format!("Connect failed: {e}"),
    });
    res
}

/// Use this TeamLogger (picked with "Browse…"); `None` goes back to auto-detect.
#[tauri::command]
pub fn set_teamlogger_path(state: State<AppState>, path: Option<String>) -> Res<Config> {
    if let Some(p) = &path {
        crate::teamlogger::looks_like_teamlogger(std::path::Path::new(p))?;
    }
    let mut cfg = state.cfg.lock().unwrap();
    let mut new = cfg.clone();
    new.teamlogger_path = path.clone();
    save(&state, &new)?;
    *cfg = new;
    drop(cfg);
    state.add_log(match path {
        Some(p) => format!("TeamLogger: {p}"),
        None => "TeamLogger: auto-detect".into(),
    });
    Ok(state.cfg.lock().unwrap().clone())
}

/// Replace the whole schedule (setup's suggested breaks).
#[tauri::command]
pub fn set_breaks(state: State<AppState>, breaks: Vec<store::Break>) -> Res<Config> {
    let mut cfg = state.cfg.lock().unwrap();
    let mut new = cfg.clone();
    new.set_breaks(&breaks)?;
    save(&state, &new)?;
    *cfg = new;
    Ok(cfg.clone())
}

#[tauri::command]
pub fn suggested_breaks() -> Vec<store::Break> {
    store::suggested_breaks()
}

#[derive(Serialize)]
pub struct PhoneLink {
    /// What the QR code opens: the topic on the ntfy server (subscribe from there).
    url: String,
    svg: String,
}

/// QR code for pairing the phone with this computer's ntfy topic.
#[tauri::command]
pub fn phone_qr(state: State<AppState>) -> Res<PhoneLink> {
    let cfg = state.cfg.lock().unwrap();
    let url = format!("{}/{}", cfg.phone.server.trim_end_matches('/'), cfg.phone.topic);
    drop(cfg);
    let code = qrcode::QrCode::new(url.as_bytes()).map_err(|e| e.to_string())?;
    let svg = code
        .render::<qrcode::render::svg::Color>()
        .min_dimensions(184, 184)
        .quiet_zone(true)
        .dark_color(qrcode::render::svg::Color("#0E0E10"))
        .light_color(qrcode::render::svg::Color("#FFFFFF"))
        .build();
    Ok(PhoneLink { url, svg })
}

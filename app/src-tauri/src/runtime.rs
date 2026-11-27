//! Runs the schedule: every second asks [`Scheduler::tick`] what to do and does
//! it — notifications, sound, phone, and TeamLogger clicks (always through the
//! click guard in `control.rs`, with retries while TeamLogger is busy).
//!
//! The break in progress is saved to `state.json`, so quitting or restarting
//! the app **doesn't** end a break: on start it picks the break back up, or
//! resumes TeamLogger if the break's end has already passed.

use chrono::{Local, NaiveDateTime};
use serde::{Deserialize, Serialize};
use std::sync::atomic::Ordering;
use std::time::Duration;
use tauri::{AppHandle, Manager};
use tauri_plugin_notification::NotificationExt;

use crate::control::{self, ClickGuard};
use crate::schedule::{ts, Action, Event};
use crate::sound::{self, Sound};
use crate::store::{fmt12, fmt_range};
use crate::AppState;

// ---------------------------------------------------------------- persistence

#[derive(Serialize, Deserialize, Default)]
struct Saved {
    /// (start, end) as Unix seconds
    active: Option<(i64, i64)>,
}

fn state_file(app: &AppState) -> std::path::PathBuf {
    app.paths.data_dir.join("state.json")
}

fn save_active(st: &AppState, active: Option<(NaiveDateTime, NaiveDateTime)>) {
    let saved = Saved { active: active.map(|(s, e)| (ts(s) as i64, ts(e) as i64)) };
    if let Ok(json) = serde_json::to_vec(&saved) {
        let _ = crate::store::write_atomic(&state_file(st), &json);
    }
}

fn from_ts(t: i64) -> Option<NaiveDateTime> {
    chrono::DateTime::from_timestamp(t, 0).map(|d| d.with_timezone(&Local).naive_local())
}

/// Pick up a break that was running when the app last stopped.
pub fn restore(st: &AppState) {
    let saved: Saved = std::fs::read(state_file(st))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default();
    if let Some((s, e)) = saved.active.and_then(|(s, e)| Some((from_ts(s)?, from_ts(e)?))) {
        let mut sched = st.sched.lock().unwrap();
        sched.active = Some((s, e));
        sched.events.insert((s.date(), s.time()), Event::Started);
        st.add_log(format!("Picked up the break {} (it ends or ended at {})", fmt_range(s.time(), e.time()), fmt12(e.time())));
    }
}

// ---------------------------------------------------------------- helpers

fn now() -> NaiveDateTime {
    Local::now().naive_local()
}

pub fn notify(app: &AppHandle, title: &str, body: &str) {
    let _ = app.notification().builder().title(title).body(body).show();
}

fn phone(st: &AppState) -> Option<&crate::phone::Phone> {
    st.phone.get()
}

/// Click in TeamLogger in the background, retrying while it's busy (up to ~1 min).
fn click_async(app: &AppHandle, what: &'static str, minutes: u32, on_fail: impl FnOnce(&AppHandle, String) + Send + 'static) {
    let app = app.clone();
    let st = app.state::<AppState>();
    st.busy.store(true, Ordering::SeqCst);
    let (port, dry_run) = {
        let cfg = st.cfg.lock().unwrap();
        (cfg.port, cfg.dry_run)
    };
    std::thread::spawn(move || {
        let guard = ClickGuard::new(dry_run);
        let mut last = String::new();
        let mut result = None;
        for attempt in 0..10 {
            let r = if what == "break" { control::take_break(port, minutes, guard) } else { control::resume(port, guard) };
            match r {
                Ok(c) => {
                    result = Some(c);
                    break;
                }
                Err(e) => {
                    last = e;
                    if attempt < 9 {
                        std::thread::sleep(Duration::from_secs(6));
                    }
                }
            }
        }
        let st = app.state::<AppState>();
        match result {
            Some(c) if c.sent => st.add_log(format!("Clicked {} in TeamLogger", c.label)),
            Some(c) => st.add_log(format!("Test mode — {} (nothing sent to TeamLogger)", c.label)),
            None => {
                st.add_log(format!("FAILED to click in TeamLogger: {last}"));
                notify(&app, "TeamLogger Break", &format!("Couldn't click in TeamLogger: {last}"));
                on_fail(&app, last);
            }
        }
        st.busy.store(false, Ordering::SeqCst);
    });
}

// ---------------------------------------------------------------- actions

/// Carry out one scheduler action.
pub fn perform(app: &AppHandle, action: Action) {
    let st = app.state::<AppState>();
    let pc = st.cfg.lock().unwrap().phone.clone();
    match action {
        Action::Warn { start, end } => {
            st.add_log(format!("Break at {} starts in 2 minutes", fmt12(start.time())));
            notify(app, "Break in 2 minutes", &fmt_range(start.time(), end.time()));
            if let Some(p) = phone(&st) {
                p.reminder(&pc, start, end);
            }
        }
        Action::Begin { start, end } => {
            save_active(&st, Some((start, end)));
            st.add_log(format!("Break time: {}", fmt_range(start.time(), end.time())));
            notify(app, "Break time", &format!("{} — taking a break in TeamLogger.", fmt_range(start.time(), end.time())));
            if let Some(p) = phone(&st) {
                p.break_started(&pc, start, end);
            }
            let minutes = ((end - start).num_seconds() as f64 / 60.0).round() as u32;
            click_async(app, "break", minutes, move |app, _| {
                let st = app.state::<AppState>();
                st.sched.lock().unwrap().fail_break(start);
                save_active(&st, None);
                let pc = st.cfg.lock().unwrap().phone.clone();
                if let Some(p) = phone(&st) {
                    p.break_ended(&pc, start, true);
                }
            });
        }
        Action::WarnEnd { end, minutes } => {
            notify(app, &format!("{minutes} minutes left"), &format!("Break ends at {}", fmt12(end.time())));
            if pc.laptop_sound {
                sound::play(Sound::Chime, 1);
            }
        }
        Action::End { start, end: _, early } => {
            save_active(&st, None);
            if let Some(p) = phone(&st) {
                p.break_ended(&pc, start, early);
            }
            if !early && pc.laptop_sound {
                sound::play(Sound::Alarm, 2);
            }
            notify(app, "Back to work", if early { "Resumed early — resuming TeamLogger." } else { "Break over — resuming TeamLogger." });
            st.add_log(if early { "Resumed early" } else { "Break over" });
            click_async(app, "resume", 0, |_, _| {});
        }
        Action::Extended { start, end, by } => {
            save_active(&st, Some((start, end)));
            st.add_log(format!("Break extended by {by} min, until {}", fmt12(end.time())));
            notify(app, "Break extended", &format!("+{by} min — back at {}", fmt12(end.time())));
            if let Some(p) = phone(&st) {
                p.break_extended(&pc, start, end);
            }
        }
        Action::Missed { start } => {
            st.add_log(format!("Missed break at {} (computer asleep?)", fmt12(start.time())));
        }
    }
}

// ---------------------------------------------------------------- manual + phone controls

pub fn break_now(app: &AppHandle, minutes: u32) -> Result<(), String> {
    let st = app.state::<AppState>();
    let action = {
        let mut s = st.sched.lock().unwrap();
        if s.active.is_some() {
            return Err("You're already on a break".into());
        }
        let n = now();
        s.begin_break(n, n + chrono::Duration::minutes(minutes as i64))
    };
    perform(app, action);
    Ok(())
}

pub fn resume_now(app: &AppHandle) -> Result<(), String> {
    let action = app.state::<AppState>().sched.lock().unwrap().end_break(now()).ok_or("You're not on a break")?;
    perform(app, action);
    Ok(())
}

pub fn extend(app: &AppHandle, minutes: u32) {
    let action = app.state::<AppState>().sched.lock().unwrap().extend(minutes, now());
    perform(app, action);
}

/// A button pressed on the phone.
pub fn phone_command(app: &AppHandle, cmd: &str) {
    let st = app.state::<AppState>();
    st.add_log(format!("Phone: {cmd}"));
    if let Some(m) = cmd.strip_prefix("extend:").and_then(|m| m.parse::<u32>().ok()) {
        extend(app, m.clamp(1, 120));
    } else if cmd == "resume" {
        let _ = resume_now(app);
    } else if cmd == "ack" {
        let pc = st.cfg.lock().unwrap().phone.clone();
        if let Some(p) = phone(&st) {
            p.stop_alarm(&pc);
        }
    } else if cmd == "ping" {
        notify(app, "Phone connected", "The button on your phone reached this computer.");
    }
}

pub fn start_phone_listener(app: &AppHandle) {
    let (a1, a2) = (app.clone(), app.clone());
    let st = app.state::<AppState>();
    if let Some(p) = phone(&st) {
        p.start_listener(
            move || a1.state::<AppState>().cfg.lock().unwrap().phone.clone(),
            move |cmd| phone_command(&a2, &cmd),
        );
    }
}

// ---------------------------------------------------------------- the loop

/// Tick once per wall-clock second for as long as the app runs.
pub fn start(app: AppHandle) {
    std::thread::spawn(move || loop {
        let st = app.state::<AppState>();
        if !st.busy.load(Ordering::SeqCst) {
            let n = now();
            let (actions, pc, active) = {
                let cfg = st.cfg.lock().unwrap();
                let mut s = st.sched.lock().unwrap();
                let a = s.tick(&cfg, n);
                (a, cfg.phone.clone(), s.active)
            };
            for a in actions {
                perform(&app, a);
            }
            if let (Some((s, e)), Some(p)) = (active, phone(&st)) {
                p.update_live(&pc, s, e, false);
            }
        }
        let ms = 1000 - (Local::now().timestamp_subsec_millis() as u64 % 1000) + 15;
        std::thread::sleep(Duration::from_millis(ms));
    });
}

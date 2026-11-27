//! Break schedule state (port of the scheduling parts of `BreakApp`).
//!
//! This milestone computes what the Today screen and tray show — next break,
//! countdown target, progress through the work stretch — and handles the
//! Auto switch and "skip today". Taking and resuming breaks in TeamLogger comes
//! with the DevTools client (milestone 3).

use chrono::{Duration, Local, NaiveDate, NaiveDateTime, NaiveTime, TimeZone};
use serde::Serialize;
use std::collections::HashMap;

use crate::activity::ActivityLog;
use crate::store::{fmt12, fmt_range, Config};

#[allow(dead_code)] // the 2-minute warning fires from the scheduler loop (milestone 4)
pub const WARN_BEFORE: Duration = Duration::minutes(2);
pub const LATE_GRACE: Duration = Duration::minutes(5);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Warned/Started/Done/Failed are set by the scheduler loop (milestone 4)
pub enum Event {
    Warned,
    Started,
    Done,
    Missed,
    Failed,
    Skipped,
}

#[derive(Default)]
pub struct Scheduler {
    pub running: bool,
    pub events: HashMap<(NaiveDate, NaiveTime), Event>,
    /// The break in progress (start, end) — set once TeamLogger control lands.
    pub active: Option<(NaiveDateTime, NaiveDateTime)>,
}

pub fn ts(dt: NaiveDateTime) -> f64 {
    Local.from_local_datetime(&dt).earliest().map(|d| d.timestamp() as f64).unwrap_or(0.0)
}

pub fn todays_breaks(cfg: &Config, day: NaiveDate) -> Vec<(NaiveDateTime, NaiveDateTime)> {
    use chrono::Datelike;
    if !cfg.days.contains(&(day.weekday().num_days_from_monday() as u8)) {
        return vec![];
    }
    cfg.break_times().into_iter().map(|(s, e)| (day.and_time(s), day.and_time(e))).collect()
}

impl Scheduler {
    pub fn new(running: bool) -> Self {
        Scheduler { running, ..Default::default() }
    }

    pub fn next_break(&self, cfg: &Config, now: NaiveDateTime) -> Option<(NaiveDateTime, NaiveDateTime)> {
        (0..8).flat_map(|off| todays_breaks(cfg, now.date() + Duration::days(off))).find(|(s, _)| {
            *s > now && self.events.get(&(s.date(), s.time())) != Some(&Event::Skipped)
        })
    }

    /// Turn automatic breaks on/off. Breaks already more than 5 minutes past
    /// their start today are marked missed so they aren't taken late.
    pub fn set_running(&mut self, cfg: &Config, on: bool, now: NaiveDateTime) {
        self.running = on;
        if on {
            for (s, _) in todays_breaks(cfg, now.date()) {
                if s + LATE_GRACE < now {
                    self.events.entry((s.date(), s.time())).or_insert(Event::Missed);
                }
            }
        }
    }

    /// Skip the rest of today's breaks. Returns how many were skipped.
    pub fn skip_today(&mut self, cfg: &Config, now: NaiveDateTime) -> usize {
        let mut n = 0;
        for (s, _) in todays_breaks(cfg, now.date()) {
            if s > now {
                self.events.insert((s.date(), s.time()), Event::Skipped);
                n += 1;
            }
        }
        n
    }

    pub fn status(&self, cfg: &Config, log: &ActivityLog, now: NaiveDateTime) -> Status {
        let mut st = Status { running: self.running, ..Default::default() };
        if let Some((s, e)) = self.active {
            let total = (e - s).num_seconds().max(1) as f64;
            let left = (e - now).num_seconds() as f64;
            st.mode = "break";
            st.target = Some(ts(e));
            st.frac = (1.0 - left / total).clamp(0.0, 1.0);
            st.caption = format!("Back to work at {}", fmt12(e.time()));
            st.text = format!("On break until {}", fmt12(e.time()));
            st.active = Some((ts(s), ts(e)));
        } else if !self.running {
            st.mode = "off";
            st.caption = "Turn on Auto to follow your schedule".into();
            st.text = "Schedule is off".into();
        } else if let Some((s, e)) = self.next_break(cfg, now) {
            let when = if s.date() == now.date() { String::new() } else { format!("{} ", s.format("%A")) };
            st.mode = "work";
            st.target = Some(ts(s));
            st.frac = work_progress(cfg, log, now, s);
            st.caption = format!("{when}{}", fmt_range(s.time(), e.time()));
            st.text = format!("Next break {}", st.caption);
            st.next = Some((ts(s), ts(e)));
            st.can_skip = s.date() == now.date();
        } else {
            st.mode = "off";
            st.caption = "Add one in Settings".into();
            st.text = "No upcoming breaks".into();
        }
        st.planned_today = todays_breaks(cfg, now.date()).len();
        st.today = self.today_list(cfg, now);
        st
    }

    /// Today's planned breaks with what happened to each, for the Today list.
    pub fn today_list(&self, cfg: &Config, now: NaiveDateTime) -> Vec<PlannedBreak> {
        let mut seen_next = false;
        todays_breaks(cfg, now.date())
            .into_iter()
            .map(|(s, e)| {
                let state = match self.events.get(&(s.date(), s.time())) {
                    Some(Event::Skipped) => "skipped",
                    Some(Event::Missed) => "missed",
                    Some(Event::Failed) => "failed",
                    _ if self.active.is_some_and(|(a, _)| a == s) => "now",
                    Some(Event::Done) | Some(Event::Started) => "done",
                    _ if e <= now => "past",
                    _ if s <= now => "now",
                    _ if !seen_next => {
                        seen_next = true;
                        "next"
                    }
                    _ => "later",
                };
                PlannedBreak { start: ts(s), end: ts(e), state }
            })
            .collect()
    }
}

/// How far through the current work stretch (last break end, or first work
/// today → next break) we are, 0…1.
pub fn work_progress(cfg: &Config, log: &ActivityLog, now: NaiveDateTime, next_start: NaiveDateTime) -> f64 {
    if next_start.date() != now.date() {
        return 0.0;
    }
    let mut begin: Option<f64> =
        todays_breaks(cfg, now.date()).into_iter().filter(|(_, e)| *e <= now).map(|(_, e)| ts(e)).reduce(f64::max);
    if begin.is_none() {
        begin = log.load(now.date()).iter().find(|s| s.is_active()).map(|s| s.0);
    }
    let (Some(b), n, ns) = (begin, ts(now), ts(next_start)) else { return 0.0 };
    if b >= ns {
        return 0.0;
    }
    ((n - b) / (ns - b)).clamp(0.0, 1.0)
}

#[derive(Debug, Clone, Serialize)]
pub struct PlannedBreak {
    pub start: f64,
    pub end: f64,
    /// "next" | "later" | "now" | "done" | "past" | "missed" | "skipped" | "failed"
    pub state: &'static str,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct Status {
    /// "work" | "break" | "off"
    pub mode: &'static str,
    pub running: bool,
    /// Unix time the countdown runs to (next break start, or break end).
    pub target: Option<f64>,
    pub frac: f64,
    pub caption: String,
    /// One-line summary (tray tooltip / menu).
    pub text: String,
    pub next: Option<(f64, f64)>,
    pub active: Option<(f64, f64)>,
    pub can_skip: bool,
    pub planned_today: usize,
    pub today: Vec<PlannedBreak>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::Break;

    fn cfg() -> Config {
        Config {
            breaks: vec![
                Break { start: "13:00".into(), end: "13:40".into() },
                Break { start: "11:30".into(), end: "11:40".into() },
            ],
            days: vec![0, 1, 2, 3, 4],
            ..Default::default()
        }
    }

    fn at(y: i32, mo: u32, d: u32, h: u32, mi: u32) -> NaiveDateTime {
        NaiveDate::from_ymd_opt(y, mo, d).unwrap().and_hms_opt(h, mi, 0).unwrap()
    }

    #[test]
    fn next_break_skips_days_off_and_skipped() {
        let c = cfg();
        let mut s = Scheduler::new(true);
        // Wed 25 Nov 2026, 12:00 → 13:00 today
        assert_eq!(s.next_break(&c, at(2026, 11, 25, 12, 0)).unwrap().0, at(2026, 11, 25, 13, 0));
        // Fri 18:00 → Monday 11:30
        assert_eq!(s.next_break(&c, at(2026, 11, 27, 18, 0)).unwrap().0, at(2026, 11, 30, 11, 30));
        assert_eq!(s.skip_today(&c, at(2026, 11, 25, 12, 0)), 1);
        assert_eq!(s.next_break(&c, at(2026, 11, 25, 12, 0)).unwrap().0, at(2026, 11, 26, 11, 30));
    }

    #[test]
    fn status_modes_and_progress() {
        let c = cfg();
        let dir = tempfile::tempdir().unwrap();
        let log = ActivityLog::new(dir.path().to_path_buf());
        let mut s = Scheduler::new(false);
        assert_eq!(s.status(&c, &log, at(2026, 11, 25, 12, 0)).mode, "off");
        s.set_running(&c, true, at(2026, 11, 25, 12, 0));
        assert_eq!(s.events.get(&(at(2026, 11, 25, 11, 30).date(), at(2026, 11, 25, 11, 30).time())), Some(&Event::Missed));
        let st = s.status(&c, &log, at(2026, 11, 25, 12, 20));
        assert_eq!(st.mode, "work");
        assert_eq!(st.caption, "1:00 – 1:40 PM");
        // 11:40 → 13:00 is 80 min; at 12:20 we're 40 min in
        assert!((st.frac - 0.5).abs() < 1e-9);
        assert!(st.can_skip);
        let states: Vec<_> = st.today.iter().map(|b| b.state).collect();
        assert_eq!(states, vec!["missed", "next"]);
        s.skip_today(&c, at(2026, 11, 25, 12, 20));
        assert_eq!(s.status(&c, &log, at(2026, 11, 25, 12, 20)).today[1].state, "skipped");
        let fri = s.status(&c, &log, at(2026, 11, 27, 18, 0));
        assert_eq!(fri.caption, "Monday 11:30 – 11:40 AM");
        assert_eq!(fri.frac, 0.0);
    }
}

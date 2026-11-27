//! Break schedule (port of `BreakApp`'s scheduling).
//!
//! Pure logic: [`Scheduler::tick`] decides *what* should happen now — warn,
//! begin a break, end it, "x minutes left" — and returns [`Action`]s. The
//! runtime (`runtime.rs`) carries them out (notifications, sound, phone, and
//! TeamLogger clicks behind the click guard). That split keeps every rule here
//! unit-testable without TeamLogger.

use chrono::{Duration, Local, NaiveDate, NaiveDateTime, NaiveTime, TimeZone};
use serde::Serialize;
use std::collections::HashMap;

use crate::activity::ActivityLog;
use crate::store::{fmt12, fmt_range, Config};

pub const WARN_BEFORE: Duration = Duration::minutes(2);
pub const LATE_GRACE: Duration = Duration::minutes(5);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
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
    /// The break in progress (start, end).
    pub active: Option<(NaiveDateTime, NaiveDateTime)>,
    /// Break end whose "x minutes left" warning already went out.
    pub warned_end: Option<NaiveDateTime>,
}

/// What the runtime should do now.
#[derive(Debug, Clone, PartialEq)]
pub enum Action {
    /// "Break in 2 minutes"
    Warn { start: NaiveDateTime, end: NaiveDateTime },
    /// Take a break in TeamLogger
    Begin { start: NaiveDateTime, end: NaiveDateTime },
    /// "x minutes left"
    WarnEnd { end: NaiveDateTime, minutes: u32 },
    /// Resume in TeamLogger; `early` = before the planned end
    End { start: NaiveDateTime, end: NaiveDateTime, early: bool },
    /// Break end moved (extended)
    Extended { start: NaiveDateTime, end: NaiveDateTime, by: u32 },
    /// A scheduled break was missed (computer asleep)
    Missed { start: NaiveDateTime },
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

    /// One step of the schedule (call about once a second).
    pub fn tick(&mut self, cfg: &Config, now: NaiveDateTime) -> Vec<Action> {
        let mut out = Vec::new();
        if let Some((s, e)) = self.active {
            if now >= e {
                out.push(self.end_break(now).expect("active"));
                return out;
            }
            let warn = cfg.phone.warn_min;
            if warn > 0
                && self.warned_end != Some(e)
                && e - now <= Duration::minutes(warn as i64)
                && (e - s) > Duration::minutes(warn as i64) + Duration::seconds(30)
            {
                self.warned_end = Some(e);
                out.push(Action::WarnEnd { end: e, minutes: warn });
            }
            return out;
        }
        if !self.running {
            return out;
        }
        for (s, e) in todays_breaks(cfg, now.date()) {
            let key = (s.date(), s.time());
            let state = self.events.get(&key).copied();
            if matches!(state, Some(Event::Started | Event::Done | Event::Missed | Event::Skipped | Event::Failed)) {
                continue;
            }
            if s - WARN_BEFORE <= now && now < s && state != Some(Event::Warned) {
                self.events.insert(key, Event::Warned);
                out.push(Action::Warn { start: s, end: e });
            } else if s <= now && now < e {
                if now - s > LATE_GRACE {
                    self.events.insert(key, Event::Missed);
                    out.push(Action::Missed { start: s });
                } else {
                    out.push(self.begin_break(s, e));
                }
                break;
            }
        }
        out
    }

    pub fn begin_break(&mut self, start: NaiveDateTime, end: NaiveDateTime) -> Action {
        self.events.insert((start.date(), start.time()), Event::Started);
        self.active = Some((start, end));
        self.warned_end = None;
        Action::Begin { start, end }
    }

    /// End the break in progress (also used for "Resume now").
    pub fn end_break(&mut self, now: NaiveDateTime) -> Option<Action> {
        let (s, e) = self.active.take()?;
        self.events.insert((s.date(), s.time()), Event::Done);
        Some(Action::End { start: s, end: e, early: now < e - Duration::seconds(5) })
    }

    /// TeamLogger refused the click: forget the break.
    pub fn fail_break(&mut self, start: NaiveDateTime) {
        self.events.insert((start.date(), start.time()), Event::Failed);
        if self.active.is_some_and(|(s, _)| s == start) {
            self.active = None;
        }
    }

    /// +N minutes: lengthen the break in progress, or start an N-minute break now.
    pub fn extend(&mut self, minutes: u32, now: NaiveDateTime) -> Action {
        match self.active {
            Some((s, e)) => {
                let e = e + Duration::minutes(minutes as i64);
                self.active = Some((s, e));
                self.warned_end = None;
                Action::Extended { start: s, end: e, by: minutes }
            }
            None => self.begin_break(now, now + Duration::minutes(minutes as i64)),
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
    fn tick_warns_begins_and_ends() {
        let mut c = cfg();
        c.phone.warn_min = 5;
        let mut s = Scheduler::new(true);
        let d = |h, m| at(2026, 11, 25, h, m);
        assert!(s.tick(&c, d(12, 0)).is_empty());
        assert_eq!(s.tick(&c, d(12, 58)), vec![Action::Warn { start: d(13, 0), end: d(13, 40) }]);
        assert!(s.tick(&c, d(12, 59)).is_empty(), "warn only once");
        assert_eq!(s.tick(&c, d(13, 0)), vec![Action::Begin { start: d(13, 0), end: d(13, 40) }]);
        assert!(s.tick(&c, d(13, 10)).is_empty());
        assert_eq!(s.tick(&c, d(13, 35)), vec![Action::WarnEnd { end: d(13, 40), minutes: 5 }]);
        assert!(s.tick(&c, d(13, 36)).is_empty(), "minutes-left only once");
        assert_eq!(s.tick(&c, d(13, 40)), vec![Action::End { start: d(13, 0), end: d(13, 40), early: false }]);
        assert!(s.active.is_none());
        assert!(s.tick(&c, d(13, 41)).is_empty(), "a finished break doesn't restart");
    }

    #[test]
    fn late_breaks_are_missed_not_taken() {
        let c = cfg();
        let mut s = Scheduler::new(true);
        let d = |h, m| at(2026, 11, 25, h, m);
        assert_eq!(s.tick(&c, d(13, 4)), vec![Action::Begin { start: d(13, 0), end: d(13, 40) }], "within 5 min grace");
        let mut s = Scheduler::new(true);
        assert_eq!(s.tick(&c, d(13, 6)), vec![Action::Missed { start: d(13, 0) }]);
        assert!(s.active.is_none());
    }

    #[test]
    fn off_or_skipped_does_nothing() {
        let c = cfg();
        let d = |h, m| at(2026, 11, 25, h, m);
        assert!(Scheduler::new(false).tick(&c, d(13, 0)).is_empty());
        let mut s = Scheduler::new(true);
        s.skip_today(&c, d(12, 0));
        assert!(s.tick(&c, d(13, 0)).is_empty());
        // Saturday: not a break day
        assert!(Scheduler::new(true).tick(&c, at(2026, 11, 28, 13, 0)).is_empty());
    }

    #[test]
    fn manual_break_extend_and_early_resume() {
        let c = cfg();
        let d = |h, m| at(2026, 11, 25, h, m);
        let mut s = Scheduler::new(false);
        assert_eq!(s.extend(15, d(10, 0)), Action::Begin { start: d(10, 0), end: d(10, 15) });
        assert_eq!(s.extend(5, d(10, 5)), Action::Extended { start: d(10, 0), end: d(10, 20), by: 5 });
        let acts = s.tick(&c, d(10, 16));
        assert!(!acts.iter().any(|a| matches!(a, Action::End { .. })), "extended break keeps going");
        assert_eq!(acts, vec![Action::WarnEnd { end: d(10, 20), minutes: 5 }], "warning follows the new end");
        assert_eq!(s.end_break(d(10, 10)), Some(Action::End { start: d(10, 0), end: d(10, 20), early: true }));
        assert_eq!(s.end_break(d(10, 11)), None);
        // a refused click forgets the break
        let mut s = Scheduler::new(true);
        s.tick(&c, d(13, 0));
        s.fail_break(d(13, 0));
        assert!(s.active.is_none());
        assert_eq!(s.today_list(&c, d(13, 1))[1].state, "failed");
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

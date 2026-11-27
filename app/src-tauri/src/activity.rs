//! Activity timeline and statistics (port of `teamlogger_activity.py`).
//!
//! Each day is stored as segments in `activity-YYYY-MM-DD.json`:
//! `[[start_ts, end_ts, "active" | "break"], ...]` (Unix seconds, local day).
//! TeamLogger's own "current working day" total, one number per day, is kept in
//! `teamlogger-totals.json` and wins over the recorded estimate when present.

use chrono::{Datelike, Duration, Local, NaiveDate, TimeZone};
use serde::Serialize;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::SystemTime;

use crate::store::write_atomic;

pub const SAMPLE_EVERY: f64 = 5.0;
/// Longer gaps (app closed, laptop asleep) stay empty.
pub const MAX_GAP: f64 = 3.0 * SAMPLE_EVERY;
/// Break slivers shorter than this are ignored (e.g. the moment TeamLogger restarts).
pub const MIN_BREAK: f64 = 60.0;

#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct Segment(pub f64, pub f64, pub String);

impl Segment {
    pub fn is_active(&self) -> bool {
        self.2 == "active"
    }
    pub fn len(&self) -> f64 {
        self.1 - self.0
    }
}

type Cached<T> = Mutex<HashMap<PathBuf, (Option<SystemTime>, T)>>;

/// Reads (and, for the recorder, writes) the timeline files. Reads are cached
/// per file and re-read when the file changes — the Linux app may be writing
/// the same files.
pub struct ActivityLog {
    dir: PathBuf,
    days: Cached<Vec<Segment>>,
    totals: Cached<HashMap<String, f64>>,
}

fn mtime(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).and_then(|m| m.modified()).ok()
}

fn read_cached<T: Clone + Default>(cache: &Cached<T>, path: &Path, parse: impl Fn(&str) -> Option<T>) -> T {
    let m = mtime(path);
    let mut c = cache.lock().unwrap();
    if let Some((cm, v)) = c.get(path) {
        if *cm == m && m.is_some() {
            return v.clone();
        }
    }
    let v = fs::read_to_string(path).ok().and_then(|s| parse(&s)).unwrap_or_default();
    c.insert(path.to_path_buf(), (m, v.clone()));
    v
}

pub fn local_date(ts: f64) -> NaiveDate {
    Local
        .timestamp_opt(ts.floor() as i64, 0)
        .earliest()
        .map(|d| d.date_naive())
        .unwrap_or_else(|| Local::now().date_naive())
}

impl ActivityLog {
    pub fn new(dir: PathBuf) -> Self {
        let _ = fs::create_dir_all(&dir);
        ActivityLog { dir, days: Mutex::new(HashMap::new()), totals: Mutex::new(HashMap::new()) }
    }

    fn day_path(&self, day: NaiveDate) -> PathBuf {
        self.dir.join(format!("activity-{}.json", day.format("%Y-%m-%d")))
    }

    fn totals_path(&self) -> PathBuf {
        self.dir.join("teamlogger-totals.json")
    }

    pub fn load(&self, day: NaiveDate) -> Vec<Segment> {
        read_cached(&self.days, &self.day_path(day), |s| serde_json::from_str(s).ok())
    }

    pub fn tl_total(&self, day: NaiveDate) -> Option<f64> {
        let totals = read_cached(&self.totals, &self.totals_path(), |s| serde_json::from_str(s).ok());
        totals.get(&day.format("%Y-%m-%d").to_string()).copied()
    }

    #[allow(dead_code)] // used once TeamLogger control lands (milestone 3)
    pub fn set_tl_total(&self, day: NaiveDate, seconds: f64) -> std::io::Result<()> {
        let path = self.totals_path();
        let mut totals: HashMap<String, f64> =
            fs::read_to_string(&path).ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or_default();
        let key = day.format("%Y-%m-%d").to_string();
        if totals.get(&key) == Some(&seconds) {
            return Ok(());
        }
        totals.insert(key, seconds);
        write_atomic(&path, serde_json::to_string(&totals)?.as_bytes())?;
        self.totals.lock().unwrap().remove(&path);
        Ok(())
    }

    /// Extend the timeline with one sample (same joining rules as the Linux app).
    #[allow(dead_code)] // used by the recorder (milestone 3)
    pub fn record(&self, state: &str, now_ts: f64) -> std::io::Result<()> {
        let day = local_date(now_ts);
        let mut segs = self.load(day);
        match segs.last_mut() {
            Some(last) if now_ts - last.1 <= MAX_GAP && last.2 == state => last.1 = now_ts,
            Some(last) if now_ts - last.1 <= MAX_GAP => {
                let from = last.1;
                segs.push(Segment(from, now_ts, state.into()))
            }
            _ => segs.push(Segment(now_ts, now_ts, state.into())),
        }
        let path = self.day_path(day);
        write_atomic(&path, serde_json::to_string(&segs)?.as_bytes())?;
        self.days.lock().unwrap().insert(path.clone(), (mtime(&path), segs));
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DaySummary {
    pub day: NaiveDate,
    /// TeamLogger's total when known, else the recorded estimate.
    pub worked: f64,
    pub recorded: f64,
    pub source: &'static str,
    #[serde(rename = "break")]
    pub break_secs: f64,
    pub breaks: usize,
    pub first: Option<f64>,
    pub last: Option<f64>,
}

pub fn day_summary(log: &ActivityLog, day: NaiveDate) -> DaySummary {
    let segs = log.load(day);
    let recorded: f64 = segs.iter().filter(|s| s.is_active()).map(Segment::len).sum();
    let breaks: Vec<&Segment> = segs.iter().filter(|s| s.2 == "break" && s.len() >= MIN_BREAK).collect();
    let work = segs.iter().filter(|s| s.is_active());
    let tl = log.tl_total(day);
    DaySummary {
        day,
        worked: tl.unwrap_or(recorded),
        recorded,
        source: if tl.is_some() { "teamlogger" } else { "recorded" },
        break_secs: breaks.iter().map(|s| s.len()).sum(),
        breaks: breaks.len(),
        first: work.clone().map(|s| s.0).reduce(f64::min),
        last: work.map(|s| s.1).reduce(f64::max),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Period {
    Week,
    Month,
}

/// Days in the week (Mon–Sun) or month containing `anchor`.
pub fn period_days(kind: Period, anchor: NaiveDate) -> Vec<NaiveDate> {
    match kind {
        Period::Week => {
            let start = anchor - Duration::days(anchor.weekday().num_days_from_monday() as i64);
            (0..7).map(|i| start + Duration::days(i)).collect()
        }
        Period::Month => {
            let start = anchor.with_day(1).unwrap();
            start.iter_days().take_while(|d| d.month() == start.month()).collect()
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct PeriodSummary {
    pub days: Vec<DaySummary>,
    pub worked: f64,
    #[serde(rename = "break")]
    pub break_secs: f64,
    pub breaks: usize,
    pub days_worked: usize,
    pub avg_day: f64,
    pub avg_break: f64,
}

pub fn period_summary(log: &ActivityLog, kind: Period, anchor: NaiveDate) -> PeriodSummary {
    let days: Vec<DaySummary> = period_days(kind, anchor).into_iter().map(|d| day_summary(log, d)).collect();
    let worked_days = days.iter().filter(|d| d.worked >= 60.0).count();
    let worked: f64 = days.iter().map(|d| d.worked).sum();
    let brk: f64 = days.iter().map(|d| d.break_secs).sum();
    let n_breaks: usize = days.iter().map(|d| d.breaks).sum();
    PeriodSummary {
        worked,
        break_secs: brk,
        breaks: n_breaks,
        days_worked: worked_days,
        avg_day: if worked_days > 0 { worked / worked_days as f64 } else { 0.0 },
        avg_break: if n_breaks > 0 { brk / n_breaks as f64 } else { 0.0 },
        days,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveTime;

    fn ts(day: NaiveDate, h: u32, m: u32) -> f64 {
        Local.from_local_datetime(&day.and_time(NaiveTime::from_hms_opt(h, m, 0).unwrap())).unwrap().timestamp()
            as f64
    }

    #[test]
    fn day_and_period_summaries_match_the_linux_rules() {
        let dir = tempfile::tempdir().unwrap();
        let log = ActivityLog::new(dir.path().to_path_buf());
        let d = NaiveDate::from_ymd_opt(2026, 11, 25).unwrap(); // a Wednesday
        let segs = vec![
            Segment(ts(d, 9, 0), ts(d, 11, 30), "active".into()),
            Segment(ts(d, 11, 30), ts(d, 11, 40), "break".into()),
            Segment(ts(d, 11, 40), ts(d, 13, 0), "active".into()),
            Segment(ts(d, 13, 0), ts(d, 13, 0) + 30.0, "break".into()), // sliver: ignored
            Segment(ts(d, 13, 0) + 30.0, ts(d, 17, 0), "active".into()),
        ];
        fs::write(dir.path().join("activity-2026-11-25.json"), serde_json::to_string(&segs).unwrap()).unwrap();

        let s = day_summary(&log, d);
        assert_eq!(s.source, "recorded");
        assert_eq!(s.recorded, (2.5 * 3600.0) + (80.0 * 60.0) + (4.0 * 3600.0 - 30.0));
        assert_eq!(s.breaks, 1);
        assert_eq!(s.break_secs, 600.0);
        assert_eq!(s.first, Some(ts(d, 9, 0)));
        assert_eq!(s.last, Some(ts(d, 17, 0)));

        // TeamLogger's own total wins
        log.set_tl_total(d, 25_000.0).unwrap();
        assert_eq!(day_summary(&log, d).worked, 25_000.0);
        assert_eq!(day_summary(&log, d).source, "teamlogger");

        let w = period_summary(&log, Period::Week, d);
        assert_eq!(w.days.len(), 7);
        assert_eq!(w.days[0].day, NaiveDate::from_ymd_opt(2026, 11, 23).unwrap());
        assert_eq!(w.days_worked, 1);
        assert_eq!(w.worked, 25_000.0);
        assert_eq!(w.avg_break, 600.0);
        assert_eq!(period_summary(&log, Period::Month, d).days.len(), 30);
        assert_eq!(period_days(Period::Month, NaiveDate::from_ymd_opt(2028, 2, 10).unwrap()).len(), 29);
    }

    #[test]
    fn record_joins_samples() {
        let dir = tempfile::tempdir().unwrap();
        let log = ActivityLog::new(dir.path().to_path_buf());
        let d = NaiveDate::from_ymd_opt(2026, 11, 25).unwrap();
        let t0 = ts(d, 10, 0);
        log.record("active", t0).unwrap();
        log.record("active", t0 + 5.0).unwrap();
        log.record("break", t0 + 10.0).unwrap();
        log.record("break", t0 + 100.0).unwrap(); // gap > MAX_GAP: new segment
        assert_eq!(
            log.load(d),
            vec![
                Segment(t0, t0 + 5.0, "active".into()),
                Segment(t0 + 5.0, t0 + 10.0, "break".into()),
                Segment(t0 + 100.0, t0 + 100.0, "break".into()),
            ]
        );
    }

    #[test]
    fn reads_python_written_files() {
        // json.dump output from the Python app: floats, compact arrays
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            dir.path().join("activity-2026-11-26.json"),
            "[[1795672800.123, 1795676400.5, \"active\"], [1795676400.5, 1795677000.0, \"break\"]]",
        )
        .unwrap();
        fs::write(dir.path().join("teamlogger-totals.json"), "{\n\"2026-11-26\": 6900\n}").unwrap();
        let log = ActivityLog::new(dir.path().to_path_buf());
        let d = NaiveDate::from_ymd_opt(2026, 11, 26).unwrap();
        assert_eq!(log.load(d).len(), 2);
        assert_eq!(log.tl_total(d), Some(6900.0));
    }
}

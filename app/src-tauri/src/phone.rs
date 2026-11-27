//! Phone alerts via ntfy (https://ntfy.sh) — port of `teamlogger_phone.py`.
//!
//! For every break:
//!   * an "On break" notification that counts down (replaced in place each minute),
//!   * a warning a few minutes before the end (optional),
//!   * an alarm at the end that repeats every minute until "Stop alarm".
//!
//! The warning and alarm are **scheduled on the ntfy server** when the break
//! starts, so they still arrive if this computer goes offline. Phone buttons
//! (+5 min, +10 min, Resume now, Stop alarm) post to a second "control" topic
//! that this app listens to.
//!
//! Privacy: messages go through the chosen ntfy server and contain only break
//! times. Anyone who knows the topic could read them or press the buttons, so
//! the topic is a long random name.

use chrono::NaiveDateTime;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use crate::schedule::ts;
use crate::store::{fmt12, Phone as PhoneCfg};

const UA: &str = concat!("teamlogger-break/", env!("CARGO_PKG_VERSION"));
/// ntfy needs at least 10 s for scheduled delivery.
const MIN_DELAY: f64 = 12.0;

fn agent(ipv4_only: bool, timeout: Option<Duration>) -> ureq::Agent {
    let mut b = ureq::Agent::config_builder().user_agent(UA).http_status_as_error(false);
    b = b.timeout_global(timeout);
    if ipv4_only {
        // networks that advertise IPv6 but don't route it would otherwise hang ~20-45 s
        b = b.ip_family(ureq::config::IpFamily::Ipv4Only);
    }
    b.build().into()
}

enum Job {
    Post { server: String, body: Value },
    Delete { url: String },
}

fn run_job(job: &Job) -> Result<(), String> {
    for v4 in [true, false] {
        let a = agent(v4, Some(Duration::from_secs(15)));
        let r = match job {
            Job::Post { server, body } => a
                .post(format!("{}/", server.trim_end_matches('/')))
                .header("Content-Type", "application/json")
                .send(body.to_string()),
            Job::Delete { url } => a.delete(url).call(),
        };
        match r {
            Ok(resp) if resp.status().is_success() || resp.status() == 404 => return Ok(()),
            Ok(resp) => return Err(format!("ntfy answered {}", resp.status())),
            Err(e) if v4 => {
                let _ = e; // try again without the IPv4-only preference
            }
            Err(e) => return Err(e.to_string()),
        }
    }
    Err("ntfy unreachable".into())
}

#[derive(Default)]
struct Inner {
    scheduled: Vec<String>,
    live_seq: Option<String>,
    last_live_min: Option<i64>,
}

pub struct Phone {
    tx: mpsc::Sender<Job>,
    inner: Mutex<Inner>,
    listener_gen: Arc<AtomicU64>,
}

fn base(start: NaiveDateTime) -> String {
    format!("b{}", start.format("%m%d%H%M%S"))
}

fn button(pc: &PhoneCfg, label: &str, command: &str, clear: bool) -> Value {
    json!({ "action": "http", "label": label, "method": "POST",
            "url": format!("{}/{}-ctl", pc.server.trim_end_matches('/'), pc.topic),
            "body": command, "clear": clear })
}

impl Phone {
    /// `log` receives network errors (they never break the app).
    pub fn new(log: impl Fn(String) + Send + 'static) -> Self {
        let (tx, rx) = mpsc::channel::<Job>();
        std::thread::spawn(move || {
            for job in rx {
                if let Err(e) = run_job(&job) {
                    log(format!("Phone: {e}"));
                }
            }
        });
        Phone { tx, inner: Mutex::new(Inner::default()), listener_gen: Arc::new(AtomicU64::new(0)) }
    }

    fn enabled(pc: &PhoneCfg) -> bool {
        pc.enabled && !pc.topic.is_empty()
    }

    #[allow(clippy::too_many_arguments)]
    fn publish(&self, pc: &PhoneCfg, seq: &str, title: &str, message: &str, priority: u8, tags: &[&str],
               actions: Vec<Value>, at: Option<f64>) {
        if !Self::enabled(pc) {
            return;
        }
        let mut body = json!({ "topic": pc.topic, "title": title, "message": message,
                               "priority": priority, "tags": tags, "sequence_id": seq });
        if !actions.is_empty() {
            body["actions"] = Value::Array(actions);
        }
        if let Some(at) = at {
            if at - chrono::Local::now().timestamp() as f64 >= MIN_DELAY {
                body["delay"] = Value::String(format!("{}", at as i64));
                self.inner.lock().unwrap().scheduled.push(seq.to_string());
            }
        }
        let _ = self.tx.send(Job::Post { server: pc.server.clone(), body });
    }

    /// Cancel a scheduled message, or remove a delivered one from the phone.
    fn delete(&self, pc: &PhoneCfg, seq: &str) {
        if !Self::enabled(pc) {
            return;
        }
        self.inner.lock().unwrap().scheduled.retain(|s| s != seq);
        let url = format!("{}/{}/{}", pc.server.trim_end_matches('/'), pc.topic, seq);
        let _ = self.tx.send(Job::Delete { url });
    }

    pub fn reminder(&self, pc: &PhoneCfg, s: NaiveDateTime, e: NaiveDateTime) {
        self.publish(pc, &format!("{}-soon", base(s)), "Break in 2 minutes",
                     &format!("{} – {}", fmt12(s.time()), fmt12(e.time())), 3, &["hourglass_flowing_sand"], vec![], None);
    }

    pub fn break_started(&self, pc: &PhoneCfg, s: NaiveDateTime, e: NaiveDateTime) {
        self.delete(pc, &format!("{}-soon", base(s)));
        {
            let mut i = self.inner.lock().unwrap();
            i.live_seq = Some(format!("{}-live", base(s)));
            i.last_live_min = None;
        }
        self.update_live(pc, s, e, true);
        self.schedule_end(pc, s, e);
    }

    /// Refresh the countdown notification (call every second; sends only when the minute changes).
    pub fn update_live(&self, pc: &PhoneCfg, s: NaiveDateTime, e: NaiveDateTime, first: bool) {
        let seq = {
            let mut i = self.inner.lock().unwrap();
            let Some(seq) = i.live_seq.clone() else { return };
            let left = (ts(e) - chrono::Local::now().timestamp() as f64).max(0.0);
            let mins = (left / 60.0).ceil() as i64;
            let total = (e - s).num_minutes();
            let step = if total <= 60 { 1 } else { 5 };
            if !first && (Some(mins) == i.last_live_min || (mins % step != 0 && mins > 1)) {
                return;
            }
            i.last_live_min = Some(mins);
            (seq, mins)
        };
        let (seq, mins) = seq;
        let title = if mins > 0 { format!("On break · {mins} min left") } else { "Break is ending".into() };
        let actions = vec![button(pc, "+5 min", "extend:5", false), button(pc, "+10 min", "extend:10", false),
                           button(pc, "Resume now", "resume", true)];
        self.publish(pc, &seq, &title, &format!("Back to work at {}", fmt12(e.time())),
                     if first { 4 } else { 2 }, &["coffee"], actions, None);
    }

    fn schedule_end(&self, pc: &PhoneCfg, s: NaiveDateTime, e: NaiveDateTime) {
        let b = base(s);
        let warn = pc.warn_min as i64;
        if warn > 0 && (e - s).num_seconds() > warn * 60 + 30 {
            self.publish(pc, &format!("{b}-warn"), &format!("{warn} minutes left"),
                         &format!("Break ends at {}", fmt12(e.time())), 4, &["hourglass"],
                         vec![button(pc, "+5 min", "extend:5", true)], Some(ts(e) - (warn * 60) as f64));
        }
        if pc.alarm {
            let repeats = pc.alarm_repeats.max(1);
            for i in 0..repeats {
                let extra = if i > 0 { format!(" (reminder {}/{repeats})", i + 1) } else { String::new() };
                self.publish(pc, &format!("{b}-alarm{i}"), "⏰ Break over — back to work",
                             &format!("Your break ended at {}{extra}", fmt12(e.time())), 5, &["alarm_clock"],
                             vec![button(pc, "Stop alarm", "ack", true), button(pc, "+5 min", "extend:5", true)],
                             Some(ts(e) + (i as f64) * 60.0));
            }
        } else {
            self.publish(pc, &format!("{b}-alarm0"), "Break over", &format!("Back to work — break ended at {}", fmt12(e.time())),
                         4, &["briefcase"], vec![], Some(ts(e)));
        }
    }

    fn cancel_scheduled(&self, pc: &PhoneCfg) {
        let pending: Vec<String> = self.inner.lock().unwrap().scheduled.clone();
        for seq in pending {
            self.delete(pc, &seq);
        }
    }

    /// Break end moved: cancel the old warning/alarms, schedule new ones.
    pub fn break_extended(&self, pc: &PhoneCfg, s: NaiveDateTime, e: NaiveDateTime) {
        self.cancel_scheduled(pc);
        self.schedule_end(pc, s, e);
        self.inner.lock().unwrap().last_live_min = None;
        self.update_live(pc, s, e, false);
    }

    pub fn break_ended(&self, pc: &PhoneCfg, s: NaiveDateTime, early: bool) {
        let live = self.inner.lock().unwrap().live_seq.take();
        if let Some(seq) = live {
            self.delete(pc, &seq);
        }
        if early {
            self.cancel_scheduled(pc);
            self.publish(pc, &format!("{}-back", base(s)), "Back to work",
                         &format!("Resumed at {}", fmt12(chrono::Local::now().time())), 2, &["briefcase"], vec![], None);
        } else {
            // the first alarm is going out now; later repeats wait for "Stop alarm"
            self.inner.lock().unwrap().scheduled.retain(|q| q.contains("-alarm") && !q.ends_with("-alarm0"));
        }
    }

    /// Phone "Stop alarm": cancel the remaining repeats.
    pub fn stop_alarm(&self, pc: &PhoneCfg) {
        let pending: Vec<String> =
            self.inner.lock().unwrap().scheduled.iter().filter(|q| q.contains("-alarm")).cloned().collect();
        for seq in pending {
            self.delete(pc, &seq);
        }
    }

    pub fn send_test(&self, pc: &PhoneCfg) -> Result<(), String> {
        if pc.topic.is_empty() {
            return Err("No phone topic yet".into());
        }
        let mut pc = pc.clone();
        pc.enabled = true; // a test is explicit
        self.publish(&pc, &format!("test{}", chrono::Local::now().timestamp()), "TeamLogger Break is connected",
                     "Phone notifications work. You'll get a countdown and an alarm for each break.", 3,
                     &["white_check_mark"], vec![button(&pc, "Test a button", "ping", true)], None);
        Ok(())
    }

    /// (Re)start listening for phone buttons. `get` reads the current phone settings;
    /// `on_command` gets "extend:5", "resume", "ack" or "ping".
    pub fn start_listener(&self, get: impl Fn() -> PhoneCfg + Send + 'static, on_command: impl Fn(String) + Send + 'static) {
        let gen = self.listener_gen.fetch_add(1, Ordering::SeqCst) + 1;
        let current = self.listener_gen.clone();
        std::thread::spawn(move || {
            let mut since = chrono::Local::now().timestamp().to_string();
            let mut backoff = 5u64;
            while current.load(Ordering::SeqCst) == gen {
                let pc = get();
                if !Self::enabled(&pc) {
                    std::thread::sleep(Duration::from_secs(5));
                    continue;
                }
                let url = format!("{}/{}-ctl/json?since={}", pc.server.trim_end_matches('/'), pc.topic, since);
                let resp = agent(true, None).get(&url).config().timeout_recv_body(Some(Duration::from_secs(90))).build().call();
                match resp {
                    Ok(r) if r.status().is_success() => {
                        backoff = 5;
                        let reader = BufReader::new(r.into_body().into_reader());
                        for line in reader.lines() {
                            if current.load(Ordering::SeqCst) != gen {
                                return;
                            }
                            let Ok(line) = line else { break };
                            let Ok(ev) = serde_json::from_str::<Value>(&line) else { continue };
                            if ev["event"] != "message" {
                                continue;
                            }
                            if let Some(id) = ev["id"].as_str() {
                                since = id.to_string();
                            }
                            let cmd = ev["message"].as_str().unwrap_or_default().trim().to_lowercase();
                            if !cmd.is_empty() {
                                on_command(cmd);
                            }
                        }
                    }
                    _ => {
                        std::thread::sleep(Duration::from_secs(backoff));
                        backoff = (backoff * 2).min(120);
                    }
                }
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sequence_ids_and_buttons() {
        let s = chrono::NaiveDate::from_ymd_opt(2026, 11, 27).unwrap().and_hms_opt(13, 0, 0).unwrap();
        assert_eq!(base(s), "b1127130000");
        let pc = PhoneCfg { server: "https://ntfy.sh/".into(), topic: "tlb-x".into(), ..Default::default() };
        let b = button(&pc, "+5 min", "extend:5", false);
        assert_eq!(b["url"], "https://ntfy.sh/tlb-x-ctl");
        assert_eq!(b["body"], "extend:5");
    }

    #[test]
    fn disabled_phone_sends_nothing() {
        let p = Phone::new(|_| {});
        let pc = PhoneCfg { enabled: false, ..Default::default() };
        let s = chrono::Local::now().naive_local();
        p.break_started(&pc, s, s + chrono::Duration::minutes(10));
        assert!(p.inner.lock().unwrap().scheduled.is_empty());
    }
}

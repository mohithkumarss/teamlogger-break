//! Reading TeamLogger's window and pressing its buttons, over DevTools.
//!
//! Same JavaScript as the Linux app (`teamlogger_break.py`), so both behave alike:
//! buttons are found by their visible text, and the break-length dropdown some
//! companies get prefers "Indefinite" (this app ends the break itself).
//!
//! ## Click guard
//! Pressing "Take a break" / "Resume" is recorded by TeamLogger, so clicks only
//! happen when **all** of these hold:
//!   * test mode (`dry_run`) is off, and
//!   * this is a release build, or `TLB_ALLOW_CLICKS=1` is set,
//!   * and `TLB_ALLOW_CLICKS` isn't `0` (forces clicks off everywhere).
//!
//! Otherwise the action is reported as "would click …" and nothing is sent.
//! Development builds therefore can never press TeamLogger's buttons by accident.

use serde::Serialize;
use serde_json::Value;
use std::time::Duration;

use crate::cdp;

const EVAL_TIMEOUT: Duration = Duration::from_secs(8);

const JS_HELPERS: &str = r#"
(() => {
  const visible = el => !!el && el.offsetParent !== null && getComputedStyle(el).visibility !== 'hidden';
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const find = (selector, texts) => [...document.querySelectorAll(selector)]
      .find(el => visible(el) && texts.some(t => norm(el.textContent) === t || norm(el.textContent).startsWith(t)));
  window.__tlab = { visible, norm, find };
})();
"#;

/// Timer state + today's "current working day" total, in one round trip.
const JS_STATE: &str = r#"
(() => {
  const { find } = window.__tlab;
  const lab = [...document.querySelectorAll('div')]
    .find(e => e.children.length === 0 && /current working day/.test(e.textContent || ''));
  const text = lab && lab.previousElementSibling ? lab.previousElementSibling.textContent : '';
  const m = (text || '').match(/(\d+)\s*hours?\D+(\d+)\s*min/i);
  let total = m ? (parseInt(m[1]) * 3600 + parseInt(m[2]) * 60) : null;
  try {
    if (total === null) {
      const r = angular.element(document.body).injector().get('$rootScope');
      const h = parseFloat(r.activeHours || 0) + parseFloat(r.offComputerHours || 0);
      if (h > 0) total = Math.round(h * 3600);
    }
  } catch (e) {}
  return {
    canBreak: !!find('button', ['take a break']),
    canResume: !!find('button', ['resume working', 'start timer', 'punch in']),
    inMeeting: !!find('button', ['end meeting mode']),
    total,
    title: document.title,
  };
})()
"#;

fn js_take_break(minutes: u32) -> String {
    format!(
        r#"{JS_HELPERS}
(async () => {{
  const {{ find, visible, norm }} = window.__tlab;
  const btn = find('button', ['take a break']);
  if (!btn) return {{ ok: false, reason: 'Take a break button not visible' }};
  if (btn.disabled) return {{ ok: false, reason: 'Take a break button is disabled' }};
  btn.click();
  await new Promise(r => setTimeout(r, 800));
  const items = [...document.querySelectorAll('ul.ddmenu li')].filter(visible);
  if (items.length === 0) return {{ ok: true, label: 'Take a break' }};
  const want = {minutes};
  let pick = items.find(li => norm(li.textContent) === 'indefinite')
          || items.find(li => norm(li.textContent) === want + 'm')
          || items.filter(li => /^\d+m$/.test(norm(li.textContent))).pop();
  if (!pick) return {{ ok: false, reason: 'Break menu opened but no option found' }};
  const label = norm(pick.textContent);
  pick.click();
  return {{ ok: true, label: 'Take a break (' + label + ')' }};
}})()"#
    )
}

fn js_resume() -> String {
    format!(
        r#"{JS_HELPERS}
(() => {{
  const {{ find }} = window.__tlab;
  const btn = find('button', ['resume working', 'start timer']);
  if (!btn && find('button', ['take a break'])) return {{ ok: true, label: 'nothing (already working)' }};
  if (!btn) return {{ ok: false, reason: 'Resume button not visible' }};
  if (btn.disabled) return {{ ok: false, reason: 'Resume button is disabled (no project/task selected?)' }};
  btn.click();
  return {{ ok: true, label: btn.textContent.replace(/\s+/g, ' ').trim() }};
}})()"#
    )
}

/// What TeamLogger is doing right now.
#[derive(Debug, Clone, Serialize, Default, PartialEq)]
pub struct Live {
    pub connected: bool,
    /// "working" | "break" | "meeting" | "unknown"
    pub state: &'static str,
    /// TeamLogger's own total for the current working day, seconds.
    pub total: Option<f64>,
}

/// The TeamLogger timer page: the first page that shows its timer buttons.
fn timer_page(port: u16) -> Result<(cdp::Page, Value), String> {
    let pages = cdp::list_pages(port)?;
    let js = format!("{JS_HELPERS}{JS_STATE}");
    for p in pages {
        if let Ok(v) = cdp::evaluate(&p.ws_url, &js, EVAL_TIMEOUT) {
            if v["canBreak"] == true || v["canResume"] == true {
                return Ok((p, v));
            }
        }
    }
    Err("TeamLogger's timer screen wasn't found (is it signed in and on the timer page?)".into())
}

fn live_from(v: &Value) -> Live {
    let state = if v["inMeeting"] == true {
        "meeting"
    } else if v["canResume"] == true && v["canBreak"] != true {
        "break"
    } else if v["canBreak"] == true {
        "working"
    } else {
        "unknown"
    };
    Live { connected: true, state, total: v["total"].as_f64() }
}

/// Read-only: timer state and today's total. Never clicks anything.
pub fn read_live(port: u16) -> Live {
    match timer_page(port) {
        Ok((_, v)) => live_from(&v),
        Err(_) => Live { connected: crate::teamlogger::control_port_open(port), state: "unknown", total: None },
    }
}

// ---------------------------------------------------------------- clicks

#[derive(Debug, Clone, Copy)]
pub struct ClickGuard {
    allowed: bool,
}

impl ClickGuard {
    pub fn new(dry_run: bool) -> Self {
        let env = std::env::var("TLB_ALLOW_CLICKS").ok();
        let forced_off = env.as_deref() == Some("0");
        let opted_in = env.as_deref() == Some("1");
        ClickGuard { allowed: !dry_run && !forced_off && (opted_in || !cfg!(debug_assertions)) }
    }

    pub fn allowed(&self) -> bool {
        self.allowed
    }

    #[cfg(test)]
    pub fn for_mock_page() -> Self {
        ClickGuard { allowed: true }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Clicked {
    /// false = nothing was sent (test mode / development build)
    pub sent: bool,
    pub label: String,
}

fn click(port: u16, guard: ClickGuard, what: &str, js: String) -> Result<Clicked, String> {
    if !guard.allowed() {
        return Ok(Clicked { sent: false, label: format!("would click {what}") });
    }
    let (page, _) = timer_page(port)?;
    let v = cdp::evaluate(&page.ws_url, &format!("{JS_HELPERS}{js}"), EVAL_TIMEOUT)?;
    if v["ok"] == true {
        Ok(Clicked { sent: true, label: v["label"].as_str().unwrap_or(what).to_string() })
    } else {
        Err(v["reason"].as_str().unwrap_or("TeamLogger didn't respond").to_string())
    }
}

/// Press "Take a break" (subject to the click guard).
pub fn take_break(port: u16, minutes: u32, guard: ClickGuard) -> Result<Clicked, String> {
    click(port, guard, "Take a break", js_take_break(minutes))
}

/// Press "Resume working" (subject to the click guard).
pub fn resume(port: u16, guard: ClickGuard) -> Result<Clicked, String> {
    click(port, guard, "Resume", js_resume())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn guard_blocks_clicks_in_dev_and_test_mode() {
        // these tests run as a debug build without TLB_ALLOW_CLICKS
        if std::env::var("TLB_ALLOW_CLICKS").is_err() {
            assert!(!ClickGuard::new(false).allowed(), "debug builds must not click");
        }
        assert!(!ClickGuard::new(true).allowed(), "test mode never clicks");
        // a blocked click sends nothing — even with no TeamLogger at all
        let r = take_break(1, 10, ClickGuard::new(true)).unwrap();
        assert_eq!(r, Clicked { sent: false, label: "would click Take a break".into() });
        let r = resume(1, ClickGuard::new(true)).unwrap();
        assert!(!r.sent);
    }

    #[test]
    fn state_mapping() {
        let j = |s: &str| serde_json::from_str::<Value>(s).unwrap();
        assert_eq!(live_from(&j(r#"{"canBreak":true,"canResume":false,"total":6960}"#)).state, "working");
        assert_eq!(live_from(&j(r#"{"canBreak":false,"canResume":true}"#)).state, "break");
        assert_eq!(live_from(&j(r#"{"canBreak":true,"inMeeting":true}"#)).state, "meeting");
        assert_eq!(live_from(&j(r#"{"canBreak":true,"total":6960}"#)).total, Some(6960.0));
    }

    /// READ-ONLY check against the real TeamLogger: reads state and total, never clicks.
    /// Run with: cargo test real_teamlogger_read_only -- --ignored --nocapture
    #[test]
    #[ignore]
    fn real_teamlogger_read_only() {
        let live = read_live(crate::store::DEFAULT_PORT);
        println!("real TeamLogger (read-only): {live:?}");
        assert!(live.connected);
    }

    /// Clicks against a MOCK TeamLogger page in headless Chrome — never the real one.
    /// Run with: TLB_MOCK_PORT=9444 cargo test mock_page -- --ignored
    #[test]
    #[ignore]
    fn mock_page_take_break_and_resume() {
        let port: u16 = std::env::var("TLB_MOCK_PORT").expect("TLB_MOCK_PORT").parse().unwrap();
        assert_ne!(port, crate::store::DEFAULT_PORT, "never point this test at the real TeamLogger port");
        let (page, _) = timer_page(port).unwrap();
        assert!(page.title.contains("MOCK"), "refusing to click a page that isn't the mock: {}", page.title);
        let before = read_live(port);
        assert_eq!(before.state, "working");
        assert_eq!(before.total, Some(6960.0));
        let r = take_break(port, 40, ClickGuard::for_mock_page()).unwrap();
        assert!(r.sent && r.label.contains("indefinite"), "{r:?}");
        assert_eq!(read_live(port).state, "break");
        let r = resume(port, ClickGuard::for_mock_page()).unwrap();
        assert!(r.sent, "{r:?}");
        assert_eq!(read_live(port).state, "working");
    }
}

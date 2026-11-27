//! Settings and data locations.
//!
//! The schema is the one the Linux (Python) app writes, so existing files keep
//! working: `config.json` with `breaks`, `days`, `port`, `dry_run`, `autostart`,
//! `login`, `theme` and `phone`. Keys this version doesn't know are kept as-is.
//!
//! Locations (`dirs` crate):
//!   Linux    ~/.config/teamlogger-break/config.json, ~/.local/share/teamlogger-break/   (same as the Python app)
//!   macOS    ~/Library/Application Support/teamlogger-break/
//!   Windows  %APPDATA%\teamlogger-break\
//! `TLB_CONFIG_DIR` / `TLB_DATA_DIR` override them (used for demo data in development).

use chrono::NaiveTime;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

pub const APP_DIR: &str = "teamlogger-break";
pub const DEFAULT_PORT: u16 = 9333;
pub const DEFAULT_SERVER: &str = "https://ntfy.sh";

#[derive(Debug, Clone)]
pub struct Paths {
    pub config_file: PathBuf,
    pub data_dir: PathBuf,
}

impl Paths {
    pub fn resolve() -> Self {
        let from_env = |key: &str| std::env::var_os(key).filter(|v| !v.is_empty()).map(PathBuf::from);
        let home = || dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
        let config_dir = from_env("TLB_CONFIG_DIR")
            .unwrap_or_else(|| dirs::config_dir().unwrap_or_else(home).join(APP_DIR));
        let data_dir = from_env("TLB_DATA_DIR")
            .unwrap_or_else(|| dirs::data_dir().unwrap_or_else(home).join(APP_DIR));
        Paths { config_file: config_dir.join("config.json"), data_dir }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Break {
    pub start: String,
    pub end: String,
}

impl Break {
    pub fn times(&self) -> Option<(NaiveTime, NaiveTime)> {
        Some((parse_hm(&self.start)?, parse_hm(&self.end)?))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Phone {
    pub enabled: bool,
    pub server: String,
    pub topic: String,
    pub warn_min: u32,
    pub alarm: bool,
    pub alarm_repeats: u32,
    pub laptop_sound: bool,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl Default for Phone {
    fn default() -> Self {
        Phone {
            enabled: false,
            server: DEFAULT_SERVER.into(),
            topic: new_topic(),
            warn_min: 5,
            alarm: true,
            alarm_repeats: 3,
            laptop_sound: true,
            extra: Map::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub breaks: Vec<Break>,
    pub days: Vec<u8>,
    pub port: u16,
    pub dry_run: bool,
    /// Automatic breaks on (remembered across restarts).
    pub autostart: bool,
    /// Start at login.
    pub login: bool,
    pub theme: String,
    pub phone: Phone,
    /// First-run setup finished (cross-platform app only).
    pub onboarded: bool,
    /// TeamLogger chosen by hand in setup; `None` = auto-detect.
    pub teamlogger_path: Option<String>,
    /// The user agreed that TeamLogger may be restarted with a local control port.
    pub control_consent: bool,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            breaks: vec![Break { start: "13:00".into(), end: "13:40".into() }],
            days: vec![0, 1, 2, 3, 4],
            port: DEFAULT_PORT,
            dry_run: false,
            autostart: false,
            login: false,
            theme: "system".into(),
            phone: Phone::default(),
            onboarded: false,
            teamlogger_path: None,
            control_consent: false,
            extra: Map::new(),
        }
    }
}

/// The schedule suggested in setup: 11:30 · 10 min, 1:00 · 40 min, 5:00 · 10 min.
pub fn suggested_breaks() -> Vec<Break> {
    [("11:30", "11:40"), ("13:00", "13:40"), ("17:00", "17:10")]
        .iter()
        .map(|(s, e)| Break { start: (*s).into(), end: (*e).into() })
        .collect()
}

impl Config {
    /// Replace all breaks, with the same checks as adding them one by one.
    pub fn set_breaks(&mut self, breaks: &[Break]) -> Result<(), String> {
        let mut next = Config { breaks: vec![], ..self.clone() };
        for b in breaks {
            let (s, e) = b.times().ok_or_else(|| format!("bad time in {} – {}", b.start, b.end))?;
            next.add_break(s, e)?;
        }
        self.breaks = next.breaks;
        Ok(())
    }

    /// Breaks as sorted (start, end) times; malformed entries are skipped.
    pub fn break_times(&self) -> Vec<(NaiveTime, NaiveTime)> {
        let mut v: Vec<_> = self.breaks.iter().filter_map(Break::times).collect();
        v.sort();
        v
    }

    /// Add a break, rejecting bad or overlapping ones (same rules as the Linux app).
    pub fn add_break(&mut self, start: NaiveTime, end: NaiveTime) -> Result<(), String> {
        if end <= start {
            return Err("The end time must be after the start time".into());
        }
        for (s, e) in self.break_times() {
            if start < e && s < end {
                return Err(format!("Overlaps with {}", fmt_range(s, e)));
            }
        }
        self.breaks.push(Break { start: start.format("%H:%M").to_string(), end: end.format("%H:%M").to_string() });
        Ok(())
    }

    pub fn remove_break(&mut self, start: NaiveTime, end: NaiveTime) {
        let (s, e) = (start.format("%H:%M").to_string(), end.format("%H:%M").to_string());
        self.breaks.retain(|b| !(b.start == s && b.end == e));
    }
}

pub fn parse_hm(s: &str) -> Option<NaiveTime> {
    let (h, m) = s.trim().split_once(':')?;
    NaiveTime::from_hms_opt(h.trim().parse().ok()?, m.trim().parse().ok()?, 0)
}

pub fn fmt12(t: NaiveTime) -> String {
    t.format("%-I:%M %p").to_string()
}

/// "1:00 – 1:40 PM" (drops the first AM/PM when both match).
pub fn fmt_range(s: NaiveTime, e: NaiveTime) -> String {
    let (a, b) = (fmt12(s), fmt12(e));
    if a[a.len() - 2..] == b[b.len() - 2..] {
        format!("{} – {}", &a[..a.len() - 3], b)
    } else {
        format!("{a} – {b}")
    }
}

/// A private ntfy topic: "tlb-" + 14 random lowercase letters/digits.
pub fn new_topic() -> String {
    const ALPHABET: &[u8] = b"abcdefghijklmnopqrstuvwxyz0123456789";
    let mut buf = [0u8; 14];
    getrandom::fill(&mut buf).expect("system random source");
    // 256 % 36 != 0: reject values that would bias the distribution
    let mut out = String::from("tlb-");
    let mut i = 0;
    while out.len() < 18 {
        if i == buf.len() {
            getrandom::fill(&mut buf).expect("system random source");
            i = 0;
        }
        let b = buf[i];
        i += 1;
        if b < 252 {
            out.push(ALPHABET[(b % 36) as usize] as char);
        }
    }
    out
}

/// Load settings. A missing file is created with defaults; a file that can't be
/// read as settings is kept as `config.json.bad` instead of being overwritten.
pub fn load_config(path: &Path) -> Config {
    let text = match fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => {
            let cfg = Config::default();
            let _ = save_config(path, &cfg);
            return cfg;
        }
    };
    let parsed = serde_json::from_str::<Value>(&text).ok().and_then(|v| {
        let had_phone = v.get("phone").is_some();
        let cfg: Config = serde_json::from_value(v).ok()?;
        cfg.breaks.iter().all(|b| b.times().is_some()).then_some((cfg, had_phone))
    });
    match parsed {
        Some((cfg, had_phone)) => {
            if !had_phone {
                let _ = save_config(path, &cfg); // keep the new phone topic
            }
            cfg
        }
        None => {
            let _ = fs::copy(path, path.with_extension("json.bad"));
            let cfg = Config::default();
            let _ = save_config(path, &cfg);
            cfg
        }
    }
}

pub fn save_config(path: &Path, cfg: &Config) -> io::Result<()> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    write_atomic(path, serde_json::to_string_pretty(cfg)?.as_bytes())
}

pub fn write_atomic(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, bytes)?;
    fs::rename(&tmp, path)
}

/// Shallow-merge `patch` into the settings (one level deeper for `phone`).
/// `breaks` can't be changed this way — use `add_break` / `remove_break`.
pub fn apply_patch(cfg: &Config, patch: &Map<String, Value>) -> Result<Config, String> {
    let mut v = serde_json::to_value(cfg).map_err(|e| e.to_string())?;
    let obj = v.as_object_mut().expect("config is an object");
    for (k, val) in patch {
        match k.as_str() {
            "breaks" => return Err("use add_break / remove_break to change breaks".into()),
            "phone" => {
                let Some(p) = val.as_object() else { return Err("phone must be an object".into()) };
                let phone = obj.entry("phone").or_insert_with(|| Value::Object(Map::new()));
                if let Some(po) = phone.as_object_mut() {
                    for (pk, pv) in p {
                        po.insert(pk.clone(), pv.clone());
                    }
                }
            }
            _ => {
                obj.insert(k.clone(), val.clone());
            }
        }
    }
    let new: Config = serde_json::from_value(v).map_err(|e| format!("invalid setting: {e}"))?;
    if new.days.iter().any(|d| *d > 6) {
        return Err("days must be 0 (Monday) … 6 (Sunday)".into());
    }
    if !["system", "light", "dark"].contains(&new.theme.as_str()) {
        return Err("theme must be system, light or dark".into());
    }
    Ok(new)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(s: &str) -> NaiveTime {
        parse_hm(s).unwrap()
    }

    #[test]
    fn keeps_unknown_keys_and_python_layout() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(
            &path,
            r#"{"breaks":[{"start":"11:30","end":"11:40"}],"days":[0,2],"port":9333,"dry_run":false,
               "autostart":true,"login":false,"theme":"dark","future_key":{"a":1},
               "phone":{"enabled":true,"server":"https://ntfy.sh","topic":"tlb-abc","warn_min":2,
                        "alarm":true,"alarm_repeats":3,"laptop_sound":false,"extra_phone":7}}"#,
        )
        .unwrap();
        let cfg = load_config(&path);
        assert_eq!(cfg.phone.topic, "tlb-abc");
        assert_eq!(cfg.days, vec![0, 2]);
        assert!(cfg.autostart);
        save_config(&path, &cfg).unwrap();
        let v: Value = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(v["future_key"]["a"], 1);
        assert_eq!(v["phone"]["extra_phone"], 7);
        assert_eq!(v["phone"]["laptop_sound"], false);
    }

    #[test]
    fn missing_phone_gets_a_topic_and_is_saved() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, r#"{"breaks":[],"days":[1]}"#).unwrap();
        let cfg = load_config(&path);
        assert!(cfg.phone.topic.starts_with("tlb-") && cfg.phone.topic.len() == 18);
        let again = load_config(&path);
        assert_eq!(again.phone.topic, cfg.phone.topic);
        assert_eq!(again.port, DEFAULT_PORT);
    }

    #[test]
    fn bad_file_is_backed_up_not_lost() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, r#"{"breaks":[{"start":"nope","end":"13:00"}]}"#).unwrap();
        let cfg = load_config(&path);
        assert_eq!(cfg.breaks.len(), 1);
        assert!(path.with_extension("json.bad").exists());
    }

    #[test]
    fn add_break_rules() {
        let mut cfg = Config::default(); // 13:00–13:40
        assert!(cfg.add_break(t("14:00"), t("13:00")).is_err());
        assert_eq!(cfg.add_break(t("13:30"), t("14:00")).unwrap_err(), "Overlaps with 1:00 – 1:40 PM");
        cfg.add_break(t("13:40"), t("13:50")).unwrap(); // touching is fine
        cfg.add_break(t("11:30"), t("11:40")).unwrap();
        assert_eq!(cfg.break_times()[0], (t("11:30"), t("11:40")));
        cfg.remove_break(t("13:40"), t("13:50"));
        assert_eq!(cfg.breaks.len(), 2);
    }

    #[test]
    fn set_breaks_validates_the_whole_list() {
        let mut cfg = Config::default();
        cfg.set_breaks(&suggested_breaks()).unwrap();
        assert_eq!(cfg.breaks.len(), 3);
        let clash = vec![
            Break { start: "10:00".into(), end: "10:30".into() },
            Break { start: "10:15".into(), end: "10:45".into() },
        ];
        assert!(cfg.set_breaks(&clash).is_err());
        assert_eq!(cfg.breaks.len(), 3, "unchanged after a failed replace");
    }

    #[test]
    fn setup_fields_default_off_for_linux_configs() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, r#"{"breaks":[],"days":[0],"phone":{"topic":"tlb-x"}}"#).unwrap();
        let cfg = load_config(&path);
        assert!(!cfg.onboarded && !cfg.control_consent && cfg.teamlogger_path.is_none());
    }

    #[test]
    fn formats_like_the_linux_app() {
        assert_eq!(fmt_range(t("13:00"), t("13:40")), "1:00 – 1:40 PM");
        assert_eq!(fmt_range(t("11:30"), t("12:10")), "11:30 AM – 12:10 PM");
    }

    #[test]
    fn patch_validates() {
        let cfg = Config::default();
        let ok = apply_patch(&cfg, serde_json::json!({"theme":"dark","phone":{"warn_min":2}}).as_object().unwrap())
            .unwrap();
        assert_eq!(ok.theme, "dark");
        assert_eq!(ok.phone.warn_min, 2);
        assert_eq!(ok.phone.topic, cfg.phone.topic);
        assert!(apply_patch(&cfg, serde_json::json!({"theme":"pink"}).as_object().unwrap()).is_err());
        assert!(apply_patch(&cfg, serde_json::json!({"days":[7]}).as_object().unwrap()).is_err());
        assert!(apply_patch(&cfg, serde_json::json!({"breaks":[]}).as_object().unwrap()).is_err());
    }
}

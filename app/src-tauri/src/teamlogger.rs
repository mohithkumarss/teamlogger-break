//! Finding TeamLogger and checking its control (DevTools) port.
//!
//! Install locations per OS. Linux is verified (the Python app uses it);
//! the Windows and macOS candidates are educated guesses until checked on a
//! machine with TeamLogger installed (plan milestone 7) — setup offers
//! "Browse…" when none matches.

use serde::Serialize;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::time::Duration;

#[derive(Debug, Clone, Serialize)]
pub struct Install {
    pub path: String,
    /// "auto" (found in a usual place) or "chosen" (picked in setup)
    pub how: &'static str,
}

/// Usual install locations on this OS, most likely first.
pub fn candidates() -> Vec<PathBuf> {
    let mut v = Vec::new();
    #[cfg(target_os = "linux")]
    {
        v.push(PathBuf::from("/opt/teamlogger/teamlogger"));
        v.push(PathBuf::from("/opt/TeamLogger/teamlogger"));
        v.push(PathBuf::from("/usr/bin/teamlogger"));
    }
    #[cfg(target_os = "macos")]
    {
        v.push(PathBuf::from("/Applications/TeamLogger.app"));
        if let Some(home) = dirs::home_dir() {
            v.push(home.join("Applications/TeamLogger.app"));
        }
    }
    #[cfg(target_os = "windows")]
    {
        let env = |k: &str| std::env::var_os(k).map(PathBuf::from);
        if let Some(local) = env("LOCALAPPDATA") {
            v.push(local.join(r"Programs\teamlogger\TeamLogger.exe"));
            v.push(local.join(r"Programs\TeamLogger\TeamLogger.exe"));
            v.push(local.join(r"TeamLogger\TeamLogger.exe"));
        }
        for k in ["ProgramFiles", "ProgramFiles(x86)"] {
            if let Some(p) = env(k) {
                v.push(p.join(r"TeamLogger\TeamLogger.exe"));
            }
        }
    }
    v
}

/// macOS: also accept any app in /Applications whose name contains "teamlogger".
fn scan_applications() -> Option<PathBuf> {
    if !cfg!(target_os = "macos") {
        return None;
    }
    std::fs::read_dir("/Applications").ok()?.flatten().map(|e| e.path()).find(|p| {
        p.extension().is_some_and(|x| x == "app")
            && p.file_name().is_some_and(|n| n.to_string_lossy().to_lowercase().contains("teamlogger"))
    })
}

pub fn detect() -> Option<PathBuf> {
    candidates().into_iter().find(|p| p.exists()).or_else(scan_applications)
}

/// The install to use: the one chosen in setup if it still exists, else auto-detected.
pub fn find(chosen: Option<&str>) -> Option<Install> {
    if let Some(c) = chosen.filter(|c| Path::new(c).exists()) {
        return Some(Install { path: c.to_string(), how: "chosen" });
    }
    detect().map(|p| Install { path: p.display().to_string(), how: "auto" })
}

/// Is a plausible TeamLogger pick? (an .app on macOS, an .exe on Windows, an existing file on Linux)
pub fn looks_like_teamlogger(path: &Path) -> Result<(), String> {
    if !path.exists() {
        return Err("That file doesn't exist".into());
    }
    let ext = path.extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
    let ok = if cfg!(target_os = "macos") {
        ext == "app"
    } else if cfg!(target_os = "windows") {
        ext == "exe"
    } else {
        path.is_file()
    };
    if ok {
        Ok(())
    } else if cfg!(target_os = "macos") {
        Err("Pick the TeamLogger app (TeamLogger.app)".into())
    } else if cfg!(target_os = "windows") {
        Err("Pick TeamLogger.exe".into())
    } else {
        Err("Pick the TeamLogger program file".into())
    }
}

/// True when something answers like Chromium's DevTools on 127.0.0.1:`port`
/// (TeamLogger started with --remote-debugging-port). Never leaves this computer.
pub fn control_port_open(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(300)) else { return false };
    let _ = s.set_read_timeout(Some(Duration::from_millis(700)));
    let _ = s.set_write_timeout(Some(Duration::from_millis(300)));
    if s.write_all(format!("GET /json/version HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n").as_bytes()).is_err() {
        return false;
    }
    let mut buf = Vec::new();
    let _ = s.take(64 * 1024).read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    text.starts_with("HTTP/1.") && text.contains("webSocketDebuggerUrl")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn port_check_needs_a_devtools_answer() {
        // closed port
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        drop(l);
        assert!(!control_port_open(port));

        // something answers, but it isn't DevTools
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        let t = std::thread::spawn(move || {
            let (mut c, _) = l.accept().unwrap();
            let mut b = [0u8; 512];
            let _ = c.read(&mut b);
            c.write_all(b"HTTP/1.0 200 OK\r\n\r\nhello").unwrap();
            let (mut c, _) = l.accept().unwrap();
            let _ = c.read(&mut b);
            c.write_all(b"HTTP/1.1 200 OK\r\n\r\n{\"Browser\":\"Chrome\",\"webSocketDebuggerUrl\":\"ws://x\"}").unwrap();
        });
        assert!(!control_port_open(port));
        assert!(control_port_open(port));
        t.join().unwrap();
    }

    #[test]
    fn chosen_path_must_exist() {
        let dir = tempfile::tempdir().unwrap();
        assert!(find(Some(dir.path().join("nope").to_str().unwrap())).is_none_or(|i| i.how == "auto"));
        let f = dir.path().join(if cfg!(target_os = "macos") { "TeamLogger.app" } else { "TeamLogger.exe" });
        if cfg!(target_os = "macos") {
            std::fs::create_dir(&f).unwrap();
        } else {
            std::fs::write(&f, b"").unwrap();
        }
        assert_eq!(find(Some(f.to_str().unwrap())).unwrap().how, "chosen");
        assert!(looks_like_teamlogger(&f).is_ok());
        assert!(looks_like_teamlogger(&dir.path().join("missing")).is_err());
    }
}

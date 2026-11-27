//! "Connect": restart TeamLogger once with its local DevTools port open.
//!
//! Linux is verified (same steps as the Python app). macOS and Windows follow
//! the same idea but are unverified until run on those systems (milestone 7).
//!
//! Linux details that matter:
//! * Stop only TeamLogger's **main** process (no `--type=` argument). Killing its
//!   renderer makes TeamLogger think it crashed and relaunch itself instantly —
//!   without the port — which then holds its single-instance lock.
//! * Start it inside a `app-gnome-teamlogger-*` systemd scope. GNOME decides which
//!   apps may take silent screenshots by that identity; started as a child of
//!   this app it would inherit our identity and its screenshots would be refused.

use std::path::Path;
use std::time::{Duration, Instant};

use crate::teamlogger::control_port_open;

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Procs {
    /// main processes (TeamLogger itself)
    pub main: Vec<u32>,
    /// every TeamLogger process (main + helpers)
    pub all: Vec<u32>,
    /// main processes that already have the DevTools port flag
    pub main_with_port: Vec<u32>,
}

/// Scan a `/proc`-like folder for TeamLogger processes (by process name).
pub fn scan(proc_root: &Path) -> Procs {
    let mut p = Procs::default();
    let Ok(entries) = std::fs::read_dir(proc_root) else { return p };
    for e in entries.flatten() {
        let Some(pid) = e.file_name().to_str().and_then(|n| n.parse::<u32>().ok()) else { continue };
        let comm = std::fs::read_to_string(e.path().join("comm")).unwrap_or_default();
        if comm.trim() != "teamlogger" {
            continue;
        }
        let cmdline = std::fs::read(e.path().join("cmdline")).unwrap_or_default();
        let args: Vec<String> =
            cmdline.split(|b| *b == 0).filter(|a| !a.is_empty()).map(|a| String::from_utf8_lossy(a).into()).collect();
        p.all.push(pid);
        if !args.iter().any(|a| a.starts_with("--type=")) {
            p.main.push(pid);
            if args.iter().any(|a| a.starts_with("--remote-debugging-port")) {
                p.main_with_port.push(pid);
            }
        }
    }
    p.main.sort_unstable();
    p.all.sort_unstable();
    p
}

/// The command that starts TeamLogger with the port (as its own GNOME app on Linux).
pub fn start_command(exe: &str, port: u16, systemd_run: bool, unit_suffix: &str) -> Vec<String> {
    let mut cmd = Vec::new();
    if systemd_run {
        cmd.extend(
            ["systemd-run", "--user", "--scope", "--quiet", "--collect"].iter().map(|s| s.to_string()),
        );
        cmd.push(format!("--unit=app-gnome-teamlogger-{unit_suffix}"));
    }
    cmd.push(exe.to_string());
    cmd.push(format!("--remote-debugging-port={port}"));
    cmd.push("--remote-allow-origins=*".to_string());
    cmd
}

#[cfg(target_os = "linux")]
mod imp {
    use super::*;
    use std::process::{Command, Stdio};

    fn signal(pid: u32, sig: &str) {
        let _ = Command::new("kill").args([sig, &pid.to_string()]).stdout(Stdio::null()).stderr(Stdio::null()).status();
    }

    /// Quit TeamLogger cleanly (main process only) and wait until it's fully gone.
    pub fn stop() -> bool {
        let root = Path::new("/proc");
        for pid in scan(root).main {
            signal(pid, "-TERM");
        }
        let deadline = Instant::now() + Duration::from_secs(15);
        while Instant::now() < deadline {
            if scan(root).all.is_empty() {
                return true;
            }
            std::thread::sleep(Duration::from_millis(300));
        }
        for pid in scan(root).main {
            signal(pid, "-KILL"); // main only: no JS runs, so no self-relaunch
        }
        std::thread::sleep(Duration::from_secs(2));
        scan(root).all.is_empty()
    }

    pub fn start(exe: &str, port: u16) -> Result<(), String> {
        use std::os::unix::process::CommandExt;
        let has_systemd_run = which("systemd-run");
        let suffix = format!(
            "{}{}",
            std::process::id(),
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs() % 100_000).unwrap_or(0)
        );
        let cmd = start_command(exe, port, has_systemd_run, &suffix);
        Command::new(&cmd[0])
            .args(&cmd[1..])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .process_group(0)
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("couldn't start TeamLogger: {e}"))
    }

    fn which(prog: &str) -> bool {
        std::env::var_os("PATH")
            .map(|p| std::env::split_paths(&p).any(|d| d.join(prog).is_file()))
            .unwrap_or(false)
    }

    pub fn connect(exe: &str, port: u16, log: &dyn Fn(String)) -> Result<String, String> {
        if control_port_open(port) {
            return Ok("TeamLogger is already connected".into());
        }
        for attempt in 1..=3 {
            log(format!("Restarting TeamLogger with the control port (attempt {attempt})…"));
            stop();
            start(exe, port)?;
            let deadline = Instant::now() + Duration::from_secs(45);
            while Instant::now() < deadline {
                std::thread::sleep(Duration::from_secs(1));
                if control_port_open(port) {
                    std::thread::sleep(Duration::from_secs(5)); // let its window finish loading
                    return Ok("TeamLogger connected".into());
                }
                // our copy lost the race to a self-relaunched TeamLogger without the port
                let p = scan(Path::new("/proc"));
                if !p.main.is_empty() && p.main_with_port.is_empty() {
                    log("A TeamLogger without the control port took over; retrying".into());
                    break;
                }
            }
        }
        Err("TeamLogger didn't open its control port".into())
    }
}

/// Wait for the control port after a start; shared by macOS and Windows.
#[cfg(any(target_os = "macos", target_os = "windows"))]
fn wait_for_port(port: u16, secs: u64) -> bool {
    let deadline = Instant::now() + Duration::from_secs(secs);
    while Instant::now() < deadline {
        std::thread::sleep(Duration::from_secs(1));
        if control_port_open(port) {
            std::thread::sleep(Duration::from_secs(5));
            return true;
        }
    }
    false
}

// NOTE: macOS and Windows are written from TeamLogger's documented behaviour as an
// Electron app but are UNVERIFIED until run on those systems (plan milestone 7).
#[cfg(target_os = "macos")]
mod imp {
    use super::*;
    use std::process::{Command, Stdio};

    fn app_name(app: &str) -> String {
        Path::new(app).file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_else(|| "TeamLogger".into())
    }

    fn running(name: &str) -> bool {
        Command::new("pgrep").args(["-x", name]).stdout(Stdio::null()).status().is_ok_and(|s| s.success())
    }

    pub fn connect(app: &str, port: u16, log: &dyn Fn(String)) -> Result<String, String> {
        if control_port_open(port) {
            return Ok("TeamLogger is already connected".into());
        }
        let name = app_name(app);
        for attempt in 1..=3 {
            log(format!("Restarting TeamLogger with the control port (attempt {attempt})…"));
            let _ = Command::new("osascript").args(["-e", &format!("quit app \"{name}\"")]).status();
            let deadline = Instant::now() + Duration::from_secs(15);
            while running(&name) && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(300));
            }
            if running(&name) {
                let _ = Command::new("pkill").args(["-x", &name]).status();
                std::thread::sleep(Duration::from_secs(2));
            }
            let port_arg = format!("--remote-debugging-port={port}");
            Command::new("open")
                .args(["-n", "-a", app, "--args", &port_arg, "--remote-allow-origins=*"])
                .status()
                .map_err(|e| format!("couldn't start TeamLogger: {e}"))?;
            if wait_for_port(port, 45) {
                return Ok("TeamLogger connected".into());
            }
        }
        Err("TeamLogger didn't open its control port".into())
    }
}

#[cfg(target_os = "windows")]
mod imp {
    use super::*;
    use std::os::windows::process::CommandExt;
    use std::process::{Command, Stdio};

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;

    fn exe_name(exe: &str) -> String {
        Path::new(exe).file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_else(|| "TeamLogger.exe".into())
    }

    /// PIDs of TeamLogger main processes (command line without `--type=`).
    fn main_pids(name: &str) -> Vec<u32> {
        let ps = format!(
            "Get-CimInstance Win32_Process -Filter \"Name='{name}'\" | \
             Where-Object {{ $_.CommandLine -notmatch '--type=' }} | ForEach-Object {{ $_.ProcessId }}"
        );
        let out = Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", &ps])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        out.map(|o| String::from_utf8_lossy(&o.stdout).lines().filter_map(|l| l.trim().parse().ok()).collect())
            .unwrap_or_default()
    }

    fn any_running(name: &str) -> bool {
        Command::new("tasklist")
            .args(["/FI", &format!("IMAGENAME eq {name}"), "/NH"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).to_lowercase().contains(&name.to_lowercase()))
            .unwrap_or(false)
    }

    pub fn connect(exe: &str, port: u16, log: &dyn Fn(String)) -> Result<String, String> {
        if control_port_open(port) {
            return Ok("TeamLogger is already connected".into());
        }
        let name = exe_name(exe);
        for attempt in 1..=3 {
            log(format!("Restarting TeamLogger with the control port (attempt {attempt})…"));
            // end the main process together with its helpers (/T), so nothing is left to relaunch it
            for pid in main_pids(&name) {
                let _ = Command::new("taskkill")
                    .args(["/PID", &pid.to_string(), "/T", "/F"])
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .creation_flags(CREATE_NO_WINDOW)
                    .status();
            }
            let deadline = Instant::now() + Duration::from_secs(15);
            while any_running(&name) && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(400));
            }
            Command::new(exe)
                .args([format!("--remote-debugging-port={port}"), "--remote-allow-origins=*".to_string()])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
                .spawn()
                .map_err(|e| format!("couldn't start TeamLogger: {e}"))?;
            if wait_for_port(port, 45) {
                return Ok("TeamLogger connected".into());
            }
        }
        Err("TeamLogger didn't open its control port".into())
    }
}

#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
mod imp {
    pub fn connect(_exe: &str, _port: u16, _log: &dyn Fn(String)) -> Result<String, String> {
        Err("Connecting isn't supported on this system".into())
    }
}

/// Restart TeamLogger with its local control port (needs the user's consent).
pub fn connect(exe: &str, port: u16, consent: bool, log: &dyn Fn(String)) -> Result<String, String> {
    if !consent {
        return Err("Allow this app to restart TeamLogger first (Settings → General, or setup step 3).".into());
    }
    imp::connect(exe, port, log)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fake_proc(dir: &Path, pid: u32, comm: &str, args: &[&str]) {
        let p = dir.join(pid.to_string());
        std::fs::create_dir_all(&p).unwrap();
        std::fs::write(p.join("comm"), format!("{comm}\n")).unwrap();
        let mut cmd = Vec::new();
        for a in args {
            cmd.extend_from_slice(a.as_bytes());
            cmd.push(0);
        }
        std::fs::write(p.join("cmdline"), cmd).unwrap();
    }

    #[test]
    fn scan_finds_main_and_helpers() {
        let d = tempfile::tempdir().unwrap();
        fake_proc(d.path(), 100, "teamlogger", &["/opt/teamlogger/teamlogger"]);
        fake_proc(d.path(), 101, "teamlogger", &["/opt/teamlogger/teamlogger", "--type=renderer"]);
        fake_proc(d.path(), 102, "teamlogger", &["/opt/teamlogger/teamlogger", "--type=zygote"]);
        fake_proc(d.path(), 200, "bash", &["bash", "-c", "pkill -f /opt/teamlogger/teamlogger"]);
        std::fs::create_dir_all(d.path().join("self")).unwrap();
        let p = scan(d.path());
        assert_eq!(p.main, vec![100]);
        assert_eq!(p.all, vec![100, 101, 102], "matches by process name only — never a shell mentioning the path");
        assert!(p.main_with_port.is_empty());

        fake_proc(d.path(), 300, "teamlogger", &["/opt/teamlogger/teamlogger", "--remote-debugging-port=9333"]);
        assert_eq!(scan(d.path()).main_with_port, vec![300]);
    }

    #[test]
    fn start_command_keeps_teamloggers_identity() {
        let c = start_command("/opt/teamlogger/teamlogger", 9333, true, "42");
        assert_eq!(&c[..5], ["systemd-run", "--user", "--scope", "--quiet", "--collect"]);
        assert_eq!(c[5], "--unit=app-gnome-teamlogger-42");
        assert_eq!(&c[6..], ["/opt/teamlogger/teamlogger", "--remote-debugging-port=9333", "--remote-allow-origins=*"]);
        let c = start_command("/x/TeamLogger", 9444, false, "");
        assert_eq!(c, ["/x/TeamLogger", "--remote-debugging-port=9444", "--remote-allow-origins=*"]);
    }

    #[test]
    fn connect_needs_consent() {
        let e = connect("/nonexistent", 1, false, &|_| {}).unwrap_err();
        assert!(e.contains("Allow"));
    }
}

//! Alarm and chime sounds, using each OS's own player and built-in sounds
//! (no audio libraries to bundle).

use std::process::{Command, Stdio};

#[derive(Debug, Clone, Copy)]
pub enum Sound {
    /// Short chime: "x minutes left".
    Chime,
    /// Break over.
    Alarm,
}

fn quiet(cmd: &mut Command) -> &mut Command {
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd
}

fn play_once(kind: Sound) -> bool {
    #[cfg(target_os = "linux")]
    {
        let f = match kind {
            Sound::Chime => "/usr/share/sounds/freedesktop/stereo/bell.oga",
            Sound::Alarm => "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
        };
        for (prog, args) in [("pw-play", vec![f]), ("paplay", vec![f]), ("canberra-gtk-play", vec!["-f", f])] {
            if quiet(Command::new(prog).args(&args)).status().is_ok_and(|s| s.success()) {
                return true;
            }
        }
        false
    }
    #[cfg(target_os = "macos")]
    {
        let f = match kind {
            Sound::Chime => "/System/Library/Sounds/Glass.aiff",
            Sound::Alarm => "/System/Library/Sounds/Hero.aiff",
        };
        quiet(Command::new("afplay").arg(f)).status().is_ok_and(|s| s.success())
    }
    #[cfg(target_os = "windows")]
    {
        let ps = match kind {
            Sound::Chime => "[System.Media.SystemSounds]::Asterisk.Play(); Start-Sleep -Milliseconds 800",
            Sound::Alarm => "(New-Object Media.SoundPlayer \"$env:WINDIR\\Media\\Alarm01.wav\").PlaySync()",
        };
        quiet(Command::new("powershell").args(["-NoProfile", "-NonInteractive", "-Command", ps]))
            .status()
            .is_ok_and(|s| s.success())
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
    {
        let _ = kind;
        false
    }
}

/// Play `times` times in the background.
pub fn play(kind: Sound, times: u32) {
    std::thread::spawn(move || {
        for _ in 0..times.max(1) {
            if !play_once(kind) {
                break;
            }
        }
    });
}

# Cross-platform plan (Windows · macOS · Linux)

Status: **milestones 1–2 and 6 done** (27 Nov 2026) — Tauri app in [`app/`](../app/README.md): shell,
full UI port, settings store, timeline + stats, schedule status, first-run setup. The working app is still the
Linux/GNOME version in the repo root (Python + GTK 4/libadwaita) until the Tauri build reaches
parity. This document is the plan for a version that installs and runs on Windows, macOS and
Linux, with a first-run setup screen.

## 1. What the app has to do (and what is OS-specific)

| Capability | Today (Linux) | Windows | macOS |
|---|---|---|---|
| Control TeamLogger (take/resume break, read state + today's total) | Chrome DevTools Protocol on `--remote-debugging-port=9333` | same (TeamLogger is Electron) — **verify** the flag isn't blocked | same — **verify** |
| Start TeamLogger with the debug port | `/opt/teamlogger/teamlogger …` inside a `systemd-run --user --scope app-gnome-teamlogger-*` (keeps its screenshot permission identity) | `%LOCALAPPDATA%\Programs\…\TeamLogger.exe --remote-debugging-port=9333` (**find real path**) | `open -n -a TeamLogger --args --remote-debugging-port=9333` |
| Stop TeamLogger cleanly (main process only, else it self-relaunches) | SIGTERM main pid (`pgrep -x teamlogger`, skip `--type=`) | graceful close of main process (`WM_CLOSE`/`taskkill /PID <main>` without `/F`, then `/F` fallback) | `osascript -e 'quit app "TeamLogger"'` |
| Scheduler (runs when window hidden) | GLib timer in Python | must live in the backend, not the web view | same |
| Tray / menu-bar with live countdown | AppIndicator icon + label (ring frames + `1:09:24`) | tray icons can't show text → draw minutes into the 16/32 px icon + tooltip | menu-bar **title** text works natively |
| Notifications | `notify-send` | toast (needs AppUserModelID from installer) | `UNUserNotificationCenter` — **ask permission** |
| Alarm sound | `pw-play` | built-in audio | built-in audio |
| Start at login | `~/.config/autostart/*.desktop` | `HKCU\…\Run` or Startup folder | Login Item (`SMAppService`/LaunchAgent) |
| Single instance + "show window" | Unix socket | named pipe / plugin | plugin |
| Phone (ntfy) | HTTP + JSON stream (Python) | same, OS-independent | same |
| Data | `~/.config/teamlogger-break/config.json`, `~/.local/share/teamlogger-break/*.json` | `%APPDATA%\…` | `~/Library/Application Support/…` |

Most of the logic (scheduler, ntfy, stats, CDP) is OS-independent; the OS-specific parts are
**launching/stopping TeamLogger, tray presentation, notifications, autostart, sound, paths.**

## 2. Options compared

| | **Tauri v2 (Rust core + web UI)** | Python + Qt (PySide6) | Electron | GTK everywhere |
|---|---|---|---|---|
| Installer size | ~8–15 MB | ~60–90 MB | ~100–150 MB | ~80 MB + rough |
| Tray countdown text | macOS title ✔, Linux label ✔, Windows icon-digits | no text on any OS (icon only) | macOS ✔, Linux partial, Windows icon | Linux only |
| Notifications / autostart / single-instance | official plugins on all 3 | DIY per OS | built-in / libs | DIY |
| Runs logic while window hidden | Rust backend ✔ | ✔ | main process ✔ | ✔ |
| Reuse current code | UI design ports to HTML/CSS; logic ported to Rust | keeps Python logic, UI rewrite | logic → TS, UI → HTML | max reuse |
| Animations | CSS / Web Animations — easiest | Qt Quick — good | CSS | GTK limited |
| Signing/notarization | `tauri-action` supports it | PyInstaller + manual | electron-builder | manual |
| Memory next to TeamLogger | low | medium | high (2nd Chromium) | low |

## 3. Recommendation

**Tauri v2** for all three platforms, with a small OS-adapter layer in the Rust core:

```
src-tauri/            Rust core (always running, also when the window is closed)
  scheduler.rs        break schedule, warnings, take/resume, extend (port of BreakApp logic)
  teamlogger/
    cdp.rs            DevTools client: find page, evaluate JS (port of teamlogger_break.py)
    launch_linux.rs   systemd-run scope + /opt path + main-pid SIGTERM
    launch_windows.rs exe discovery, graceful close, relaunch with flag
    launch_macos.rs   open -a … --args, osascript quit
  phone.rs            ntfy publish/schedule/delete + control-topic listener (port of teamlogger_phone.py)
  activity.rs         recorder + day/period summaries + TeamLogger totals (port of teamlogger_activity.py)
  tray.rs             per-OS presentation (title / label / icon digits), ring frames
  store.rs            config + data (same JSON schema → migrate existing files)
src/                  web UI (HTML/CSS/TS): Today, Stats, Settings, Setup — port of teamlogger_ui.py design
```

Why not one stack per OS: three UIs triple the work and drift apart. Tauri gives one UI and
one core, and the genuinely different bits are isolated in small adapter files. The current
GTK app stays as the Linux reference until the Tauri build reaches parity.

Plugins: `tray-icon`, `notification`, `autostart`, `single-instance`, `store`, `http`
(ntfy), `shell`/`process`; crates: `tokio-tungstenite` (CDP websocket), `rodio` (sound),
`sysinfo` (find TeamLogger processes).

## 4. First-run setup screen (build in the new stack)

1. **Welcome** — what the app does; it takes breaks *in* TeamLogger (they're recorded as breaks); data stays on this computer.
2. **Find TeamLogger** — auto-detect per OS, show ✔ / not found + "Browse…".
3. **Permission to control TeamLogger** — explain: TeamLogger restarts once with a local-only debug port so this app can press its buttons; consent checkbox; **Connect now** with live status.
4. **Notifications** — request permission (macOS/Windows), play a test sound.
5. **Your breaks** — presets (e.g. 11:30·10m, 1:00·40m, 5:00·10m) + days.
6. **Phone (optional)** — ntfy topic shown as a **QR code**, Send test.
7. **Start at login + theme** → Done. Store `onboarded: true`; re-run from Settings → General.

## 5. Milestones

1. ✅ Scaffold Tauri app, port design (Today/Stats/Settings) — runs in a browser with demo data too.
2. ✅ Rust core: store + activity + stats (reads existing JSON) + schedule status (next break, progress).
3. CDP client + Linux adapter → parity with current Linux app.
4. Scheduler + notifications + sound + tray (per-OS presentation). ✅ tray ring + countdown and hide-on-close done.
5. ntfy phone module.
6. ✅ Setup screen (all 7 steps). Steps that need later milestones save the choice now and say so:
   "Connect now" (3), phone "Send test" (5). Windows/macOS TeamLogger paths are guesses until 7.
7. Windows + macOS adapters (needs a Windows and a Mac with TeamLogger to verify the debug flag and paths).
8. GitHub Actions: build `.msi`, `.dmg`, `.AppImage`/`.deb`; smoke tests on all three runners.
9. Signing (Apple Developer ID + notarization; Windows code-signing cert optional).

## 6. Decisions still needed from the owner

- **License** for the app code (MIT / Apache-2.0 / GPL-3.0). The bundled font is OFL-1.1 (see `fonts/`).
- **Public name.** "TeamLogger" is another company's product name; an open-source tool should
  use its own name (e.g. "Breakly — for TeamLogger") and say it's unofficial / not affiliated.
- **Repo visibility** (private until the name/license are settled?).
- Whether the setup screen may offer to change TeamLogger's own login entry so it always starts
  with the debug port (removes the daily "Connect" step) — only with the user's explicit opt-in.

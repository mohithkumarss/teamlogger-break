# Handoff notes (for the next session / laptop)

## Where things are

- **Working app:** Linux/GNOME version in the repo root. Run `python3 teamlogger_break_gui.py`.
- **Cross-platform version:** [`app/`](../app/README.md) (Tauri v2). Milestones 1–2 done: UI port, config store,
  timeline/stats, schedule status, first-run setup (milestone 6). Next: milestone 3 (DevTools client + launch adapters). Plan → [CROSS_PLATFORM_PLAN.md](CROSS_PLATFORM_PLAN.md).
  Dev on macOS: Rust via `brew install rustup` (keg-only → `PATH=/opt/homebrew/opt/rustup/bin:$PATH`);
  `npm run dev` previews the UI in a browser with demo data; `npm run tauri:demo` runs the desktop app on `app/dev-data`.
- **Package:** `packaging/build-deb.sh <version>` (last built: 1.5.0; `dist/` is git-ignored).

## User data (not in the repo)

- Settings: `~/.config/teamlogger-break/config.json` (breaks, days, theme, phone topic, …)
- Timeline: `~/.local/share/teamlogger-break/activity-YYYY-MM-DD.json`
- TeamLogger's daily totals: `~/.local/share/teamlogger-break/teamlogger-totals.json`
- Copy these to the new machine to keep history and the phone topic.

## Verified on the original machine (Ubuntu, GNOME on Wayland)

- Take/resume break via DevTools; TeamLogger "Take a break" dropdown handled (prefers *Indefinite*).
- Restart TeamLogger: stop **main** process only (killing renderers makes it self-relaunch without the flag),
  start under `systemd-run --scope --unit=app-gnome-teamlogger-*` (otherwise GNOME's screenshot portal refuses it).
- ntfy end-to-end on a throwaway topic: live countdown updates, scheduled alarms, cancel/extend, phone buttons.
- IPv6 on that network was broken → `teamlogger_phone.py` prefers IPv4.
- UI rendered in light/dark, wide/narrow; animations not checkable in screenshots.

## Known limitations / gotchas

- Font: Google Sans Flex is the default face everywhere. Tauri app: bundled in the web UI. Linux GTK app:
  registered with fontconfig for its own process before GTK starts (any Pango), falling back to
  Pango ≥ 1.56's add_font_file — **not yet checked on a Linux machine**.

- After each login TeamLogger starts without the debug port → press **Connect** once (TeamLogger restarts).
- Restarting this app **during a break** resumes TeamLogger (quit ends the break) — avoid, or change `quit_app`.
- Stats before 27 Nov 2026 use the recorded estimate; from then on the TeamLogger total.
- `teamlogger_break.py` contains a CLI scheduler too (older, still works).

## Open decisions

License · public name (avoid implying affiliation with TeamLogger) · repo visibility ·
whether setup may modify TeamLogger's own login entry (explicit opt-in only).

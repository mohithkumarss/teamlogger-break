# TeamLogger Break

Scheduled breaks for the **TeamLogger** desktop client — with a live countdown, a phone alarm,
and daily / weekly / monthly stats. *Unofficial; not affiliated with TeamLogger.*

At the times you set it clicks TeamLogger's **Take a break**, and **Resume** when the break
ends — so breaks are recorded as breaks. You can extend a break (+5 / +10 min) from the app
or your phone.

> Current version: **Linux (GNOME)**, Python + GTK 4 / libadwaita.
> Windows and macOS are planned — see [docs/CROSS_PLATFORM_PLAN.md](docs/CROSS_PLATFORM_PLAN.md).

## Features

- Today dashboard: countdown, "your day" strip (work, breaks, planned breaks — click to edit), progress.
- Worked time synced with TeamLogger's own "current working day" total.
- Stats: week bars / month calendar, per-day timeline, history.
- Top-bar progress ring + countdown; start at login; runs in the background.
- Phone notifications via [ntfy](https://ntfy.sh): live countdown, warning, repeating alarm, +5 min / Resume buttons.
- Light / dark theme, micro-animations. Typeface: Google Sans Flex (OFL-1.1, bundled).

## Run (Linux)

Requirements: Python 3, `python3-gi`, GTK 4, libadwaita ≥ 1.7, AyatanaAppIndicator3
(Ubuntu: `gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-ayatanaappindicator3-0.1 libnotify-bin`),
and the TeamLogger desktop app.

```bash
python3 teamlogger_break_gui.py          # open (runs in background when closed)
python3 teamlogger_break_gui.py --quit   # stop
```

Build a `.deb`: `packaging/build-deb.sh 1.5.0` → `dist/`.

## How it talks to TeamLogger

TeamLogger is an Electron app. This app (re)starts it once with
`--remote-debugging-port=9333` (local only) and presses its buttons through the
Chrome DevTools Protocol. On GNOME it's started in its own `app-gnome-teamlogger-*`
scope so its screenshot permission is unchanged.

## Files

| File | What |
|---|---|
| `teamlogger_break_gui.py` | app: scheduler, tray/socket plumbing, settings |
| `teamlogger_ui.py` | interface (GTK 4) and design system |
| `teamlogger_break.py` | TeamLogger control via DevTools; also a CLI |
| `teamlogger_activity.py` | timeline recorder + stats |
| `teamlogger_phone.py` | ntfy phone notifications |
| `teamlogger_break_tray.py` | top-bar indicator (progress ring + countdown) |
| `data/`, `fonts/` | logo, bundled font + its license |
| `docs/` | plans and handoff notes |

## License

To be decided (see the plan). Font: SIL Open Font License 1.1 — `fonts/OFL.txt`.

# TeamLogger Break — cross-platform app (Tauri v2)

The Windows / macOS / Linux version from [../docs/CROSS_PLATFORM_PLAN.md](../docs/CROSS_PLATFORM_PLAN.md).
**Status: feature-complete on Linux** (milestones 1–6, 8). It takes and resumes breaks in TeamLogger on
your schedule, with notifications, sound, phone alerts (ntfy), Connect, stats from the same files the
Linux app writes, and a 7-step first-run setup. **Windows/macOS:** built by CI; TeamLogger start/stop
there is written but not yet tested on real machines (milestone 7).

**First-run setup** (re-run from Settings → General): Welcome · Find TeamLogger (auto-detect per OS
+ Browse…) · Permission to control TeamLogger (consent, live connection check) · Notifications
(permission + test, alarm sound) · Your breaks (suggested schedule, days) · Phone (QR code for the
ntfy topic) · Start at login + theme. `?setup=done` in the browser preview skips it.

**Menu bar / tray:** a progress ring with the live countdown — macOS menu bar (ring + countdown
text), Linux top bar (coloured ring + label, like the GTK app), Windows tray (ring; countdown in the
tooltip). Its menu: status, Open, Automatic breaks, Skip today, Quit. Closing the window keeps the
app running; reopen it from the tray, the Dock (macOS) or by launching it again.

**Feels native:** the window never bounces or scrolls as a page; no browser right-click menu,
reload/find/print shortcuts or zoom keys in builds; on macOS the title bar merges into the header
(drag the header to move the window).

**Typeface:** Google Sans Flex is bundled into the app and is the default on Linux, macOS and
Windows — it doesn't depend on installed fonts. The window waits for it before the first paint.

## Run

Needs Node ≥ 22.18 (runs `.ts` scripts directly) and Rust (stable). On macOS with Homebrew:
`brew install rustup && rustup default stable` — rustup is keg-only, so add
`/opt/homebrew/opt/rustup/bin` to `PATH`. Linux also needs the
[Tauri system packages](https://tauri.app/start/prerequisites/) (webkit2gtk etc.).

```bash
npm install
npm run dev            # UI only, in a browser, with built-in demo data (no Rust needed)
npm run tauri:demo     # desktop app on generated demo data in ./dev-data
npm run tauri dev      # desktop app on your real settings + timeline
npm run tauri build    # installers / app bundle in src-tauri/target/release/bundle
```

Real data locations (shared with the Linux app on Linux):

| OS | Settings | Timeline |
|---|---|---|
| Linux | `~/.config/teamlogger-break/config.json` | `~/.local/share/teamlogger-break/` |
| macOS | `~/Library/Application Support/teamlogger-break/config.json` | same folder |
| Windows | `%APPDATA%\teamlogger-break\config.json` | same folder |

`TLB_CONFIG_DIR` / `TLB_DATA_DIR` override them. Copying the Linux files to these folders
brings history and the phone topic along.

## Layout

```
src-tauri/src/
  lib.rs        app state, plugin setup, command registry
  store.rs      config.json (same schema as the Linux app; unknown keys kept; bad file → .bad backup)
  activity.rs   timeline files, TeamLogger totals, day/period summaries (+ recorder's record())
  schedule.rs   pure rules: warn / begin / end / "minutes left" / missed / extend (unit-tested)
  runtime.rs    runs the schedule every second: notifications, sound, phone, clicks; keeps the
                active break across restarts (quitting never ends a break)
  control.rs    read TeamLogger (state, today's total); take break / resume behind the click guard
  cdp.rs        DevTools client, 127.0.0.1 only
  launch.rs     Connect: restart TeamLogger with its local port (Linux verified; macOS/Windows untested)
  phone.rs      ntfy: live countdown, scheduled warning + repeating alarm, phone buttons
  sound.rs      chime / alarm with each OS's own player
  teamlogger.rs find TeamLogger per OS, check its local control port
  tray.rs       menu-bar / top-bar / tray ring + countdown and its menu
  commands.rs   the commands the UI invokes
src/
  main.ts       shell: header (brand · Today/Stats · settings), 1-second tick
  today.ts      countdown + one primary action, your day (timeline + 3 numbers), today's breaks
  stats.ts      period total + bars/calendar, 3 numbers, 8-week trend, selected day, history
  dialogs.ts    break editor, take a break, settings, phone setup, activity log
  setup.ts      first-run setup (7 steps)       platform.ts  notifications, file picker, login, sound
  charts.ts     SVG charts (ports of the GTK widgets)
  app.ts        shared state + actions     api.ts  bridge to Rust (mock outside Tauri)
  mock.ts       browser preview backend    demo.ts demo timeline (also scripts/demo-data.ts)
  styles.css    design system: one centered column, hairlines not boxes, palettes, type, motion
```

## Tests

```bash
cd src-tauri && cargo test     # rules vs. the Linux app, click guard, DevTools client, Connect, phone
npm run typecheck
```

Opt-in live tests (see ../docs/HANDOFF.md): clicks against a **mock** TeamLogger page only, and a
read-only check of the real one. Developer builds never click TeamLogger unless `TLB_ALLOW_CLICKS=1`.

## Next

7. Verify macOS/Windows on real machines with TeamLogger (paths, Connect, clicks, sounds).
9. Signing (needs Apple / Windows certificates) — see ../docs/RELEASING.md.

# TeamLogger Break — cross-platform app (Tauri v2)

The Windows / macOS / Linux version from [../docs/CROSS_PLATFORM_PLAN.md](../docs/CROSS_PLATFORM_PLAN.md).
**Status: preview — milestones 1–2 and the first-run setup (6) done.** It shows your schedule,
countdown and stats from the same files the Linux app writes, you can edit breaks and settings, and
a 7-step setup runs on first launch. It can't press TeamLogger's buttons yet (milestone 3), so
actions that need that (take/resume/extend a break, Connect, phone test) show a "not available yet"
message.

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
  schedule.rs   next break, countdown target, work-stretch progress, Auto switch, skip today
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
cd src-tauri && cargo test     # store, activity/stats and schedule rules vs. the Linux app
npm run typecheck
```

## Next (plan milestones)

3. DevTools client + per-OS launch adapters → take/resume/extend, Connect, recorder, TeamLogger totals
4. Scheduler loop, notifications, sound (✅ tray / menu-bar countdown, hide-on-close)
5. ntfy phone module · 6. ✅ first-run setup · 7. Windows/macOS adapters verified on real machines · 8–9. CI builds, signing

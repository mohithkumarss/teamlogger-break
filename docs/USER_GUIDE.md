# TeamLogger Break — user guide

Breaks on a schedule, for the TeamLogger desktop app. *Unofficial — not affiliated with TeamLogger.*

- [Before you start](#before-you-start)
- [Install](#install) — [Windows](#windows) · [macOS](#macos) · [Linux](#linux) · [from source](#build-from-source)
- [First-run setup](#first-run-setup)
- [Every day](#every-day)
- [Phone alerts](#phone-alerts)
- [Settings](#settings)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)

---

## Before you start

- The **TeamLogger desktop app** must be installed and signed in on the same computer.
- A break taken by TeamLogger Break is a **real break in TeamLogger** — it's recorded exactly as if
  you had clicked *Take a break* yourself. Use it the way your employer's break rules allow.
- Want to try it without anything happening in TeamLogger? Turn on **Test mode** right after setup
  (Settings → General). Everything runs, but nothing is clicked.

## Install

Download the installer for your system from the project's **[Releases](../../../releases)** page
(the latest release is at the top; open **Assets**).

### Windows

1. Download **`TeamLogger Break_…_x64-setup.exe`** (or the `.msi`).
2. Open it. Windows SmartScreen may say *"Windows protected your PC"* because the installer isn't
   signed yet — click **More info → Run anyway**.
3. Follow the installer, then open **TeamLogger Break** from the Start menu.

The countdown lives in the **system tray** (bottom right; it may be under the **^** arrow — drag it
out to keep it visible). Hover it to see the time left.

### macOS

1. Download **`TeamLogger Break_…_universal.dmg`** (works on Apple Silicon and Intel).
2. Open it and drag **TeamLogger Break** into **Applications**.
3. The first time, **right-click (or Control-click) the app → Open → Open**. macOS asks this once
   because the app isn't notarized yet. (If it still refuses: System Settings → Privacy & Security →
   *Open Anyway*.)
4. Allow notifications when asked.

The countdown lives in the **menu bar** (top right) as a small ring with the time.

### Linux

**Ubuntu / Debian** — download **`TeamLogger Break_…_amd64.deb`**, then:

```bash
sudo apt install ./TeamLogger*Break_*_amd64.deb
```

**Fedora / openSUSE** — download the `.rpm`, then `sudo dnf install ./TeamLogger*Break-*.rpm`.

**Any distribution** — download the `.AppImage`, make it executable and run it:

```bash
chmod +x TeamLogger*Break_*_amd64.AppImage
./TeamLogger*Break_*_amd64.AppImage
```

The countdown lives in the **top bar**. On GNOME this needs the *AppIndicator* extension — Ubuntu has
it built in; on Fedora and others install **"AppIndicator and KStatusNotifierItem Support"**.

### Build from source

Needs Node 22 and Rust (stable). On Linux also:
`sudo apt install libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev`.

```bash
git clone https://github.com/mohithkumarss/teamlogger-break.git
cd teamlogger-break/app
npm ci
npx tauri build        # installers end up in src-tauri/target/release/bundle/
```

## First-run setup

The first time you open the app, seven short steps walk you through everything. You can run them
again any time: **Settings → General → Run setup again**.

| Step | What to do |
|---|---|
| **1. Welcome** | What the app does. Click **Get started**. |
| **2. Find TeamLogger** | Usually found automatically (✓). If not, click **Browse…** and pick TeamLogger (`TeamLogger.exe` on Windows, `TeamLogger.app` on macOS, the `teamlogger` program on Linux). |
| **3. Permission** | Read what happens, tick **"I agree…"**, then **Connect now**. TeamLogger closes and reopens once (its timer pauses for a few seconds) with a control port that only this computer can reach. When it says **TeamLogger is connected**, continue. |
| **4. Notifications and sound** | Click **Allow** and **Play** to check you can hear the alarm. |
| **5. Your breaks** | Use the suggested schedule (11:30 · 10 min, 1:00 · 40 min, 5:00 · 10 min) or add your own with **+ Add break**. Tap a break to change its time or length. Pick the days (M T W T F S S). |
| **6. Your phone** *(optional)* | See [Phone alerts](#phone-alerts). You can skip this and do it later. |
| **7. Almost done** | Turn on **Start at login** so breaks happen even if you forget to open the app, and pick a theme. |

## Every day

### The Today screen

- **The big number** — time until your next break, or, during a break, time until you're back.
  The blue bar under it fills as your work stretch (or break) goes by.
- **Auto** switch — automatic breaks on/off. Off = nothing happens on its own.
- **Your day** — a line from morning to evening: your work (solid), breaks (amber), planned breaks
  (amber outline, with their time above) and *now* (blue). **Click a planned break to change it**;
  **+ Add break** adds one.
- **Take a break now** — pick 5–60 minutes; the break starts in TeamLogger straight away.
- **During a break:** **Resume work** to come back early, **+5 min** / **+10 min** to stretch it.
- **Skip today** — skip the rest of today's breaks (they come back tomorrow).
- On the right: today's worked time (from TeamLogger), breaks, this week, your 30-day average,
  the last 30 days and this week's hours per day.

### What happens at break time

1. **2 minutes before:** a notification (and on your phone, if set up).
2. **At the start:** TeamLogger's *Take a break* is pressed for you. If your company shows a menu
   of break lengths, *Indefinite* is chosen and the app ends the break on time itself.
3. **A few minutes before the end** (if turned on): "x minutes left", with a chime.
4. **At the end:** an alarm, and TeamLogger's *Resume* is pressed for you.

If your computer was asleep and wakes more than 5 minutes after a break should have started, that
break is skipped (marked *missed*) rather than started late. Closing or quitting the app never ends
a break — next time it opens it carries on (or resumes TeamLogger if the break is already over).

### The menu bar / tray

Closing the window keeps the app running. The ring + countdown in the menu bar (macOS), top bar
(Linux) or tray (Windows) has a menu: **Open TeamLogger Break**, **Automatic breaks**,
**Skip today's remaining breaks**, **Quit TeamLogger Break**.

### After you log in

TeamLogger starts on its own when you log in — **without** the control port. If the app shows
**Connect TeamLogger**, click it once (TeamLogger restarts for a few seconds), and breaks work for the
rest of the day.

### Stats

Click **Stats** at the top (or press **Ctrl/⌘ + 2**). Choose **Week** or **Month**, step back with
**‹ ›**, and click a bar, a day in the calendar or a row in **History** to see that day's timeline
and breaks. Worked time comes from TeamLogger's own "current working day" total.

### Keyboard shortcuts

| | |
|---|---|
| **Ctrl/⌘ + 1** | Today |
| **Ctrl/⌘ + 2** | Stats |
| **Ctrl/⌘ + ,** | Settings |

## Phone alerts

Get a live countdown, a warning before the end and an alarm on your phone — handy when you step out.
It uses the free **ntfy** app; no account needed.

1. Install **ntfy** — [Android (Play Store)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   · [iPhone (App Store)](https://apps.apple.com/app/ntfy/id1625396347).
2. In TeamLogger Break: **Settings → Phone & alarm → Set up your phone** (or setup step 6).
3. In ntfy, tap **+** and **scan the QR code**, or type the topic shown (it starts with `tlb-`).
4. Click **Send test** — a notification should appear on your phone within seconds.
5. **For a loud alarm on Android:** in ntfy open the topic → *Notification settings* → *Urgent
   priority* → allow it to override *Do Not Disturb*.

On the phone notifications you'll find buttons: **+5 min**, **+10 min**, **Resume now** and, on the
alarm, **Stop alarm**. The warning and alarm are scheduled on the ntfy server when the break starts,
so they still ring if your computer goes to sleep or offline.

> **Privacy:** notifications go through ntfy.sh and contain only your break times. Anyone who knows
> your topic could see them or press the buttons, so keep it private. **New topic** in the phone
> setup replaces it (then subscribe to the new one on your phone).

## Settings

**Settings** (gear icon, or **Ctrl/⌘ + ,**) has three tabs:

**Schedule**
- *Automatic breaks* — on/off.
- *Breaks* — tap one to change or delete it; **+** to add one.
- *Repeat on* — the days your breaks apply.

**Phone & alarm**
- *Phone notifications* on/off · *Set up your phone* (QR code, Send test, New topic).
- *Warn before the break ends* — Off / 2 / 5 / 10 minutes.
- *Alarm when the break ends* — urgent sound that repeats until you press Stop; *Rings* — how many times.
- *Ring on this computer too*.

**General**
- *Theme* — Follow system / Light / Dark (also the ◐ button at the top).
- *TeamLogger* — where it is, and **Connect**.
- *Start at login*.
- *Test mode* — run everything without clicking anything in TeamLogger.
- *Activity log* — what the app did and when (handy if something didn't happen).
- *Run setup again*.

## Troubleshooting

| Problem | What to do |
|---|---|
| **"Connect TeamLogger"** keeps showing | Click it. If it fails, make sure TeamLogger is installed and signed in, and that setup step 3's "I agree" is ticked (Settings → General → Run setup again). |
| **"TeamLogger wasn't found"** | Settings → General → choose TeamLogger with **Browse…**. |
| **A break didn't start** | Is **Auto** on? Is today one of your break days? Was the computer asleep at the time (then it's *missed*)? Check **Settings → General → Activity log**. |
| **"Couldn't click in TeamLogger"** | TeamLogger must be on its timer screen and signed in. *Resume* can't be pressed if no project/task is selected in TeamLogger. |
| **Nothing happens in TeamLogger, but the log says "Test mode"** | Turn off **Test mode** (Settings → General). |
| **No notifications** | Allow them for TeamLogger Break in your system's notification settings (macOS/Windows), then try **Allow** in setup step 4. |
| **No ring/countdown in the Linux top bar** | Install/enable the GNOME *AppIndicator* extension (see [Linux](#linux)). |
| **Phone test doesn't arrive** | Check the topic in ntfy matches exactly; make sure phone alerts are on; try **New topic** and resubscribe. |
| **macOS says the app "can't be opened"** | Right-click → Open (once). See [macOS](#macos). |
| **Windows SmartScreen warning** | More info → Run anyway. See [Windows](#windows). |

## Uninstall

- **Windows:** Settings → Apps → *TeamLogger Break* → Uninstall.
- **macOS:** quit it from the menu bar, then drag it from Applications to the Bin.
- **Linux:** `sudo apt remove team-logger-break` (or `sudo dnf remove team-logger-break`; for the
  AppImage just delete the file).

Your settings and history stay behind in case you reinstall. To remove them too, delete:

| | |
|---|---|
| Windows | `%APPDATA%\teamlogger-break\` |
| macOS | `~/Library/Application Support/teamlogger-break/` |
| Linux | `~/.config/teamlogger-break/` and `~/.local/share/teamlogger-break/` |

TeamLogger itself isn't changed by uninstalling. If it's still running with the control port, quit and
reopen it once to start it normally again.

#!/usr/bin/env python3
"""
TeamLogger Break Scheduler — GNOME app (GTK 4 + libadwaita).

Pick break windows (e.g. 1:00 PM – 1:40 PM) and days, and the app:
  * shows a live countdown to the next break (and in the top bar),
  * pops a desktop notification 2 minutes before a break,
  * clicks TeamLogger's "Take a break" at the start time,
  * clicks "Resume Working" at the end time,
  * draws a timeline of when you worked and when you were on break,
  * sends a countdown + alarm to your phone (ntfy app) — see teamlogger_phone.py,
  * shows daily / weekly / monthly time spent (Stats tab).

Runs in the background: closing the window only hides it. Launching it again
just shows the running window.

  python3 teamlogger_break_gui.py            # open the window
  python3 teamlogger_break_gui.py --hidden   # start in the background (used at login)
  python3 teamlogger_break_gui.py --quit     # stop the running app

Settings: ~/.config/teamlogger-break/config.json
Timeline: ~/.local/share/teamlogger-break/activity-YYYY-MM-DD.json
"""

import argparse
import datetime as dt
import json
import math
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import teamlogger_activity as ta  # noqa: E402
import teamlogger_break as tl  # noqa: E402
import teamlogger_phone as tp  # noqa: E402
import teamlogger_ui as tui  # noqa: E402

SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "teamlogger-break.sock")
TRAY_SCRIPT = os.path.join(HERE, "teamlogger_break_tray.py")
APP_SCRIPT = os.path.abspath(__file__)
APP_ID = "io.github.local.TeamLoggerBreak"
LAUNCHER_PATH = os.path.expanduser("~/.local/share/applications/teamlogger-break.desktop")
AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/teamlogger-break.desktop")
CONFIG_PATH = os.path.expanduser("~/.config/teamlogger-break/config.json")
APP_ICON = next((p for p in (os.path.join(HERE, "data", "teamlogger-break.svg"),
                             "/usr/share/icons/hicolor/scalable/apps/teamlogger-break.svg") if os.path.exists(p)),
                os.path.join(HERE, "data", "teamlogger-break.svg"))
DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=TeamLogger Break
Comment=Take and resume TeamLogger breaks on a schedule
Exec=/usr/bin/python3 "{script}"{args}
Icon={icon}
Terminal=false
Categories=Utility;
StartupNotify=false
StartupWMClass={app_id}
"""

DAY_LETTERS = ["M", "T", "W", "T", "F", "S", "S"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WARN_BEFORE = dt.timedelta(minutes=2)
LATE_GRACE = dt.timedelta(minutes=5)

DEFAULT_CONFIG = {
    "breaks": [{"start": "13:00", "end": "13:40"}],
    "days": [0, 1, 2, 3, 4],
    "port": tl.DEFAULT_PORT,
    "dry_run": False,
    "autostart": False,   # schedule on when the app starts (remembers the switch)
    "login": False,
    "theme": "system",   # system | light | dark
    # "phone": filled from teamlogger_phone.default_phone_config() on first run
}

ALARM_SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
WARN_SOUND = "/usr/share/sounds/freedesktop/stereo/bell.oga"


def play_sound(path, times=1):
    """Play a sound on this computer (non-blocking)."""
    def run():
        for i in range(times):
            for cmd in (["pw-play", path], ["canberra-gtk-play", "-f", path], ["paplay", path]):
                try:
                    if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      timeout=30).returncode == 0:
                        break
                except (OSError, subprocess.TimeoutExpired):
                    continue
    threading.Thread(target=run, daemon=True).start()




# ----------------------------------------------------------------- helpers
def fmt12(t):
    return t.strftime("%I:%M %p").lstrip("0")


def fmt_range(s, e):
    """1:00 – 1:40 PM  (drops the first AM/PM when both match)."""
    a, b = fmt12(s), fmt12(e)
    if a[-2:] == b[-2:]:
        a = a[:-3]
    return f"{a} – {b}"


def fmt_clock(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_in(seconds):
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return f"in {h}h {m}m" if h else f"in {m}m" if m else "in <1m"


def ms_to_next_second():
    """Delay that lands just after the next wall-clock second."""
    return 1000 - int(time.time() * 1000) % 1000 + 15


def parse_hm(s):
    hh, mm = (int(x) for x in s.split(":"))
    return dt.time(hh, mm)


def notify(title, body):
    try:
        subprocess.Popen(["notify-send", "-a", "TeamLogger Break", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def send_command(cmd, timeout=3):
    """Send a command to an already-running instance. Returns its reply or None."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(SOCK)
        s.sendall(cmd.encode() + b"\n")
        return s.recv(65536).decode().strip()
    except OSError:
        return None
    finally:
        s.close()


def write_desktop_file(path, args=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        icon = APP_ICON if os.path.exists(APP_ICON) else "alarm-symbolic"
        f.write(DESKTOP_ENTRY.format(script=APP_SCRIPT, args=args, app_id=APP_ID, icon=icon))


# GTK is imported only when the app really starts (not for --quit / hand-off).
def import_gtk():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gsk", "4.0")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango
    return Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango


def build_app_classes():
    Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango = import_gtk()

    MainWindow = tui.build_ui_classes(Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango,
                                      {"fmt12": fmt12, "fmt_range": fmt_range, "fmt_in": fmt_in})

    # ============================================================ application
    class BreakApp(Adw.Application):
        def __init__(self, hidden):
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
            self.start_hidden = hidden
            self.cfg = self.load_config()
            self.running = False
            self.busy = False
            self.events = {}       # (date, start) -> warned|started|done|missed|failed|skipped
            self.active = None     # (start_dt, end_dt)
            self.connected = None
            self.log_lines = []
            self.status = {"text": "Starting…", "label": "", "on_break": False, "running": False}
            self.win = None
            self.tray = None
            self.hide_hint_shown = False
            self.activity = ta.ActivityLog()
            self.last_day = dt.date.today()
            self.phone = tp.Phone(lambda: self.cfg["phone"],
                                  lambda cmd: GLib.idle_add(self.on_phone_command, cmd),
                                  lambda msg: GLib.idle_add(self.log, msg))
            self.warned_end = None   # break whose "x minutes left" sound already played
            self.connect("startup", self.on_startup)
            self.connect("activate", self.on_activate)

        # ---- lifecycle
        def on_startup(self, *_):
            self.css = None
            if not tui.load_fonts():
                self.log("Bundled font not loaded; using system fonts")
            sm = Adw.StyleManager.get_default()
            sm.connect("notify::dark", lambda *_: self.apply_palette())
            self.set_theme(self.cfg.get("theme", "system"), save=False)
            for name, cb in (("break-now", lambda *_: self.show_and(self.win.break_now_dialog)),
                             ("skip-today", lambda *_: self.skip_today()),
                             ("connect", lambda *_: self.show_and(self.win.confirm_connect)),
                             ("show-log", lambda *_: self.show_and(self.win.show_log)),
                             ("hide", lambda *_: self.hide_window()),
                             ("settings", lambda *_: self.show_and(self.win.open_settings)),
                             ("quit", lambda *_: self.quit_app())):
                a = Gio.SimpleAction.new(name, None)
                a.connect("activate", cb)
                self.add_action(a)
            self.set_accels_for_action("app.hide", ["<Control>w"])
            self.set_accels_for_action("app.quit", ["<Control>q"])

            self.hold()  # keep running with no window open
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            theme.add_search_path(os.path.dirname(APP_ICON))
            Gtk.Window.set_default_icon_name("teamlogger-break")
            self.win = MainWindow(self)
            self.apply_palette()
            self.win.rebuild_breaks()
            self.win.timeline.refresh()
            self.start_command_server()
            self.start_tray()
            ta.Recorder(self.activity, self.port).start()
            self.phone.start_listener()
            write_desktop_file(LAUNCHER_PATH)
            self.check_connection(auto_connect=self.start_hidden and self.cfg.get("login"))
            GLib.timeout_add_seconds(15, lambda: self.check_connection() or True)
            if self.cfg.get("autostart") or (self.start_hidden and self.cfg.get("login")):
                self.set_running(True, quiet=True)
            self.tick()

        def on_activate(self, *_):
            if self.start_hidden:
                self.start_hidden = False
                return
            self.show_window()

        def show_and(self, fn):
            self.show_window()
            fn()

        def show_window(self):
            self.win.set_visible(True)
            self.win.present()
            self.win.timeline.refresh()

        def hide_window(self):
            self.win.set_visible(False)
            if not self.hide_hint_shown:
                self.hide_hint_shown = True
                notify("TeamLogger Break is still running",
                       "It keeps working in the background. Open it from the top-bar icon or the app menu.")

        def quit_app(self):
            if self.active:
                self.end_break("Quitting")
            if self.tray and self.tray.poll() is None:
                self.tray.terminate()
            try:
                os.unlink(SOCK)
            except OSError:
                pass
            self.release()
            self.quit()

        # ---- config
        def load_config(self):
            try:
                with open(CONFIG_PATH) as f:
                    cfg = {**DEFAULT_CONFIG, **json.load(f)}
                for b in cfg["breaks"]:
                    parse_hm(b["start"]), parse_hm(b["end"])
            except Exception:
                cfg = json.loads(json.dumps(DEFAULT_CONFIG))
            if "phone" not in cfg:
                cfg["phone"] = tp.default_phone_config()  # new private topic, saved below
                self.cfg = cfg
                self.save_config()
            else:
                cfg["phone"] = {**tp.default_phone_config(), **cfg["phone"]}
            return cfg

        def save_config(self):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.cfg, f, indent=2)

        def set_cfg(self, key, value):
            self.cfg[key] = value
            self.save_config()

        # ---- theme
        def set_theme(self, theme, save=True):
            schemes = {"system": Adw.ColorScheme.DEFAULT, "light": Adw.ColorScheme.FORCE_LIGHT,
                       "dark": Adw.ColorScheme.FORCE_DARK}
            Adw.StyleManager.get_default().set_color_scheme(schemes.get(theme, Adw.ColorScheme.DEFAULT))
            if save:
                self.set_cfg("theme", theme)
            self.apply_palette()

        def toggle_theme(self):
            dark = Adw.StyleManager.get_default().get_dark()
            self.set_theme("light" if dark else "dark")
            dlg = self.win.settings_dlg if self.win else None
            if dlg:
                dlg.theme_row.set_selected(["system", "light", "dark"].index(self.cfg["theme"]))

        def apply_palette(self):
            display = Gdk.Display.get_default()
            if self.css:
                Gtk.StyleContext.remove_provider_for_display(display, self.css)
            pal = tui.PALETTES["dark" if Adw.StyleManager.get_default().get_dark() else "light"]
            self.css = Gtk.CssProvider()
            self.css.load_from_string(tui.render_css(pal))
            Gtk.StyleContext.add_provider_for_display(display, self.css,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            if self.win:
                self.win.redraw()

        def set_phone(self, key, value):
            self.cfg["phone"][key] = value
            self.save_config()

        def new_phone_topic(self):
            self.set_phone("topic", tp.new_topic())
            self.phone.start_listener()
            if self.win.settings_dlg:
                self.win.settings_dlg.setup_row.set_subtitle(f"Topic: {self.cfg['phone']['topic']}")
            return self.cfg["phone"]["topic"]

        def on_phone_command(self, cmd):
            """A button was pressed on the phone."""
            self.log(f"Phone: {cmd}")
            if cmd.startswith("extend:"):
                try:
                    mins = max(1, min(120, int(cmd.split(":", 1)[1])))
                except ValueError:
                    return False
                self.extend_break(mins)
            elif cmd == "resume":
                self.end_break("Resumed from your phone")
            elif cmd == "ack":
                self.phone.stop_alarm()
                self.win.toast("Alarm stopped from your phone")
            elif cmd == "ping":
                self.win.toast("Phone button works")
                notify("Phone connected", "The button on your phone reached this computer.")
            return False

        def extend_break(self, mins):
            if self.active:
                s, e = self.active
                e = e + dt.timedelta(minutes=mins)
                self.active = (s, e)
                self.warned_end = None
                self.phone.break_extended(s, e)
                self.log(f"Break extended by {mins} min, until {fmt12(e)}")
                notify("Break extended", f"+{mins} min — back at {fmt12(e)}")
                self.win.toast(f"Break extended to {fmt12(e)}")
            else:
                self.log(f"New {mins} min break from phone")
                self.break_now(mins)

        def set_login(self, on):
            self.set_cfg("login", on)
            if on:
                write_desktop_file(AUTOSTART_PATH, " --hidden")
                self.log("Will start in the background at login.")
            else:
                try:
                    os.unlink(AUTOSTART_PATH)
                except FileNotFoundError:
                    pass
                self.log("Won't start at login.")

        def log(self, msg):
            self.log_lines.append(f"{dt.datetime.now():%H:%M:%S}  {msg}")
            self.log_lines = self.log_lines[-500:]

        def port(self):
            return int(self.cfg.get("port", tl.DEFAULT_PORT))

        # ---- breaks list
        def breaks(self):
            return sorted((parse_hm(b["start"]), parse_hm(b["end"])) for b in self.cfg["breaks"])

        def add_break(self, s, e, quiet=False):
            if e <= s:
                return "The end time must be after the start time"
            for os_, oe in self.breaks():
                if s < oe and os_ < e:
                    return f"Overlaps with {fmt_range(os_, oe)}"
            self.cfg["breaks"].append({"start": s.strftime("%H:%M"), "end": e.strftime("%H:%M")})
            self.save_config()
            self.log(f"Added break {fmt_range(s, e)}")
            self.win.rebuild_breaks()
            self.win.timeline.refresh()
            if not quiet:
                self.win.toast(f"Saved: {fmt_range(s, e)}")
            return None

        def remove_break(self, s, e, quiet=False):
            key = (s.strftime("%H:%M"), e.strftime("%H:%M"))
            self.cfg["breaks"] = [b for b in self.cfg["breaks"] if (b["start"], b["end"]) != key]
            self.save_config()
            self.log(f"Removed break {fmt_range(s, e)}")
            self.win.rebuild_breaks()
            self.win.timeline.refresh()
            if not quiet:
                self.win.toast(f"Break removed: {fmt_range(s, e)}")

        def todays_breaks(self, day=None):
            day = day or dt.date.today()
            if day.weekday() not in self.cfg["days"]:
                return []
            return [(dt.datetime.combine(day, s), dt.datetime.combine(day, e)) for s, e in self.breaks()]

        def planned_breaks(self, day):
            return [(s.timestamp(), e.timestamp()) for s, e in self.todays_breaks(day)]

        def next_break(self, now):
            for offset in range(8):
                for s, e in self.todays_breaks(now.date() + dt.timedelta(days=offset)):
                    if s > now and self.events.get((s.date(), s.time())) != "skipped":
                        return s, e
            return None

        # ---- background plumbing
        def start_command_server(self):
            try:
                os.unlink(SOCK)
            except FileNotFoundError:
                pass
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(SOCK)
            os.chmod(SOCK, 0o600)
            srv.listen(4)

            def serve():
                while True:
                    try:
                        conn, _ = srv.accept()
                    except OSError:
                        return
                    with conn:
                        try:
                            cmd = conn.recv(1024).decode().strip()
                            if cmd == "status":
                                conn.sendall(json.dumps(self.status).encode())
                            else:
                                GLib.idle_add(self.handle_command, cmd)
                                conn.sendall(b"ok")
                        except OSError:
                            pass
            threading.Thread(target=serve, daemon=True).start()

        def handle_command(self, cmd):
            if cmd == "show":
                self.show_window()
            elif cmd == "resume":
                self.end_break("Resumed early")
            elif cmd == "quit":
                self.quit_app()
            return False

        def start_tray(self):
            try:
                self.tray = subprocess.Popen([sys.executable, TRAY_SCRIPT, SOCK],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                self.tray = None

        # ---- TeamLogger
        def check_connection(self, auto_connect=False):
            def work():
                ok = tl.debug_port_open(self.port())
                GLib.idle_add(self.set_connected, ok)
                if ok:
                    total = tl.read_today_total(self.port())
                    if total is not None:
                        self.activity.set_tl_total(dt.date.today(), total)
                if not ok and auto_connect:
                    # At login TeamLogger starts itself (its login entry includes the
                    # control port). Just wait for it — never restart it here, a restart
                    # looks like a crash and can break its screenshots.
                    for _ in range(36):
                        time.sleep(5)
                        if tl.debug_port_open(self.port()):
                            break
                    ok = tl.debug_port_open(self.port())
                    GLib.idle_add(self.set_connected, ok)
                    if ok:
                        GLib.idle_add(self.log, "TeamLogger connected.")
                    else:
                        GLib.idle_add(self.log, "TeamLogger not connected after login.")
                        notify("TeamLogger isn't connected",
                               "Open TeamLogger Break and press Connect so breaks can be clicked.")
            threading.Thread(target=work, daemon=True).start()

        def set_connected(self, ok):
            if ok != self.connected:
                self.connected = ok
                self.win.set_connected(ok)
            return False

        def connect_teamlogger(self):
            self.log("Restarting TeamLogger with control port…")
            self.win.toast("Restarting TeamLogger…")

            def work():
                try:
                    tl.launch_teamlogger(self.port())
                    msg = "TeamLogger connected"
                except SystemExit as e:
                    msg = f"Couldn't connect: {e}"
                ok = tl.debug_port_open(self.port())

                def done():
                    self.log(msg)
                    self.win.toast(msg)
                    self.set_connected(ok)
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        def run_action(self, kind, minutes=0, on_done=None):
            if self.cfg.get("dry_run"):
                self.log(f"[test mode] would click {'Take a break' if kind == 'break' else 'Resume Working'}")
                if on_done:
                    on_done(True)
                return
            self.busy = True

            def work():
                if kind == "break":
                    res = tl.do_with_retries(self.port(), lambda ws: tl.evaluate(ws, tl.js_take_break(minutes)))
                else:
                    res = tl.do_with_retries(self.port(), lambda ws: tl.evaluate(ws, tl.JS_RESUME))
                ok = bool(res and res.get("ok"))

                def finish():
                    self.busy = False
                    if ok and kind == "break":
                        extra = f" (chose '{res['option']}')" if res.get("mode") == "dropdown" else ""
                        self.log(f"Clicked 'Take a break'{extra}")
                    elif ok:
                        self.log(f"Clicked {res.get('label')}")
                    else:
                        reason = res and res.get("reason")
                        self.log(f"FAILED: {reason}")
                        notify("TeamLogger Break", f"Couldn't click the button: {reason}")
                        self.win.toast("Couldn't click TeamLogger — see Activity Log")
                    if on_done:
                        on_done(ok)
                    return False
                GLib.idle_add(finish)
            threading.Thread(target=work, daemon=True).start()

        # ---- schedule
        def set_running(self, on, quiet=False):
            self.running = on
            self.set_cfg("autostart", on)
            if on:
                now = dt.datetime.now()
                for s, _e in self.todays_breaks():
                    if s + LATE_GRACE < now:
                        self.events.setdefault((s.date(), s.time()), "missed")
                self.log("Schedule on.")
                if not quiet:
                    self.win.toast("Automatic breaks on")
            else:
                self.log("Schedule off.")
                if not quiet:
                    self.win.toast("Automatic breaks off")
            self.win.rebuild_breaks()

        def skip_today(self):
            n = 0
            for s, _e in self.todays_breaks():
                if s > dt.datetime.now():
                    self.events[(s.date(), s.time())] = "skipped"
                    n += 1
            self.log("Remaining breaks today will be skipped.")
            self.win.rebuild_breaks()
            self.win.toast(f"Skipping {n} break{'s' if n != 1 else ''} today" if n else "No more breaks today")

        def break_now(self, minutes):
            start = dt.datetime.now().replace(microsecond=0)
            self.begin_break(start, start + dt.timedelta(minutes=minutes))

        def begin_break(self, start, end):
            key = (start.date(), start.time())
            self.events[key] = "started"
            self.active = (start, end)
            mins = round((end - start).total_seconds() / 60)
            notify("Break time", f"{fmt_range(start, end)} — taking a break in TeamLogger.")
            self.warned_end = None
            self.phone.break_started(start, end)
            self.win.rebuild_breaks()

            def done(ok):
                if not ok:
                    self.events[key] = "failed"
                    self.active = None
                    self.phone.break_ended(start, end, early=True)
                    self.win.rebuild_breaks()
            self.run_action("break", mins, done)

        def end_break(self, reason="Break over"):
            if not self.active:
                return
            start, end = self.active
            self.events[(start.date(), start.time())] = "done"
            self.active = None
            early = dt.datetime.now() < end - dt.timedelta(seconds=5)
            self.phone.break_ended(start, end, early)
            if not early and self.cfg["phone"].get("laptop_sound", True):
                play_sound(ALARM_SOUND, 2)
            notify("Back to work", f"{reason}. Resuming TeamLogger.")
            self.run_action("resume")
            self.win.rebuild_breaks()

        def tick(self):
            now = dt.datetime.now().replace(microsecond=0)
            try:
                self.update_schedule(now)
                self.update_status(now)
                if self.active:
                    s, e = self.active
                    self.phone.update_live(s, e)
                    warn = int(self.cfg["phone"].get("warn_min") or 0)
                    if (warn and self.warned_end != e and e - now <= dt.timedelta(minutes=warn)
                            and (e - s) > dt.timedelta(minutes=warn, seconds=30)):
                        self.warned_end = e
                        notify(f"{warn} minutes left", f"Break ends at {fmt12(e)}")
                        if self.cfg["phone"].get("laptop_sound", True):
                            play_sound(WARN_SOUND)
                visible = self.win.get_visible()
                if now.date() != self.last_day:
                    self.last_day = now.date()
                    self.win.timeline.go_today()
                    self.win.rebuild_breaks()
                elif visible and now.second % 5 == 0:
                    self.win.timeline.refresh()
                    self.win.update_totals()
                if visible and now.second == 0:
                    self.win.rebuild_breaks()  # refresh "in 2h 10m" subtitles
                    if self.win.stack.get_visible_child_name() == "stats":
                        self.win.stats.refresh()
            finally:
                GLib.timeout_add(ms_to_next_second(), self.tick)
            return False

        def update_schedule(self, now):
            if self.busy:
                return
            if self.active:
                if now >= self.active[1]:
                    self.end_break()
                return
            if not self.running:
                return
            for s, e in self.todays_breaks():
                key = (s.date(), s.time())
                state = self.events.get(key)
                if state in ("started", "done", "missed", "skipped", "failed"):
                    continue
                if s - WARN_BEFORE <= now < s and state != "warned":
                    self.events[key] = "warned"
                    notify("Break in 2 minutes", fmt_range(s, e))
                    self.phone.reminder(s, e)
                    self.log(f"Break at {fmt12(s)} starts in 2 minutes")
                elif s <= now < e:
                    if now - s > LATE_GRACE:
                        self.events[key] = "missed"
                        self.log(f"Missed break at {fmt12(s)} (computer asleep?)")
                        self.win.rebuild_breaks()
                    else:
                        self.log(f"Break time: {fmt_range(s, e)}")
                        self.begin_break(s, e)
                    return

        def work_progress(self, now, next_start):
            """How far through the current work stretch (last break end / start of day → next break)."""
            if next_start.date() != now.date():
                return 0
            begin = None
            for s, e in self.todays_breaks():
                if e <= now and (begin is None or e > begin):
                    begin = e
            segs = [x for x in self.activity.load(now.date()) if x[2] == "active"]
            if begin is None and segs:
                begin = dt.datetime.fromtimestamp(segs[0][0])
            if begin is None or begin >= next_start:
                return 0
            return (now - begin).total_seconds() / (next_start - begin).total_seconds()

        def update_status(self, now):
            label, target = "", None
            if self.active:
                s, e = self.active
                left = (e - now).total_seconds()
                total = max(1, (e - s).total_seconds())
                ui = dict(eyebrow="ON BREAK", clock=fmt_clock(left), mode="break",
                          frac=1 - left / total, caption=f"Back at {fmt12(e)}", action="Resume Now")
                text, label, target = f"On break until {fmt12(e)}", fmt_clock(left), e.timestamp()
            else:
                nxt = self.next_break(now) if self.running else None
                if not self.running:
                    ui = dict(eyebrow="BREAKS PAUSED", clock="––:––", mode="off", frac=0,
                              caption="Turn on automatic breaks", action="Take a Break Now")
                    text = "Schedule is off"
                elif nxt:
                    s, e = nxt
                    when = "" if s.date() == now.date() else f"{s:%A} "
                    ui = dict(eyebrow="NEXT BREAK", clock=fmt_clock((s - now).total_seconds()),
                              mode="work", frac=self.work_progress(now, s),
                              caption=f"{when}{fmt_range(s, e)}", action="Take a Break Now")
                    text = f"Next break {when}{fmt_range(s, e)}"
                    label, target = fmt_clock((s - now).total_seconds()), s.timestamp()
                else:
                    ui = dict(eyebrow="NO BREAKS AHEAD", clock="––:––", mode="off", frac=0,
                              caption="Add one in Settings", action="Take a Break Now")
                    text = "No upcoming breaks"
            if self.connected is False:
                text += "  (TeamLogger not connected)"
            self.status = {"text": text, "label": label, "target": target,
                           "on_break": bool(self.active), "running": self.running,
                           "mode": ui.get("mode", "off"), "frac": round(float(ui.get("frac") or 0), 4)}
            self.win.update(ui)

    return BreakApp


def main():
    p = argparse.ArgumentParser(description="TeamLogger Break Scheduler")
    p.add_argument("--hidden", action="store_true", help="start in the background (no window)")
    p.add_argument("--quit", action="store_true", help="stop the running instance")
    args = p.parse_args()

    if args.quit:
        print("Stopped." if send_command("quit") else "Not running.")
        return
    if send_command("status") is not None:  # already running: just show it
        if not args.hidden:
            send_command("show")
        return
    if sys.stdin.isatty() and not os.environ.get("TLB_FOREGROUND"):
        subprocess.Popen([sys.executable, APP_SCRIPT] + (["--hidden"] if args.hidden else []),
                         env={**os.environ, "TLB_FOREGROUND": "1"},
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        print("TeamLogger Break is running in the background. You can close this terminal.")
        return
    tui.register_fonts_early()   # before GTK loads, so Google Sans Flex is the default face
    BreakApp = build_app_classes()
    BreakApp(hidden=args.hidden).run([sys.argv[0]])


if __name__ == "__main__":
    main()

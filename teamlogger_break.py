#!/usr/bin/env python3
"""
TeamLogger auto-break scheduler.

Clicks TeamLogger's "Take a break" button at the time(s) you choose, waits
for the break length you set, then clicks "Resume Working" / "Start Timer".

It talks to the TeamLogger desktop app (an Electron app) through Chromium's
remote-debugging port and clicks the real buttons by their text, so it does
not depend on window position, screen size, or Wayland/X11.

TeamLogger must be running with the debug port open. The script can do this
for you with --launch (it closes TeamLogger and starts it again with the port).

Examples
  # One break at 13:00 for 45 minutes, every day, (re)starting TeamLogger first:
  python3 teamlogger_break.py --at 13:00 --duration 45 --launch

  # Two breaks a day with different lengths:
  python3 teamlogger_break.py --at 11:00=15 --at 13:30=45 --launch

  # Only run once (exit after the last break today):
  python3 teamlogger_break.py --at 13:00 --duration 45 --once

  # Check that the buttons can be found, without clicking anything:
  python3 teamlogger_break.py --status

Only the Python standard library is used.
"""

import argparse
import base64
import datetime as dt
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

TEAMLOGGER_BIN = "/opt/teamlogger/teamlogger"
DEFAULT_PORT = 9333

# Preset durations offered by TeamLogger's break dropdown (when enabled by the company).
DROPDOWN_MINUTES = [1, 5, 10, 15, 20, 30, 40, 45, 50, 60, 90]


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------
# Minimal WebSocket client (enough for the Chrome DevTools Protocol)
# --------------------------------------------------------------------------
class WebSocket:
    def __init__(self, url, timeout=10):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (("?" + u.query) if u.query else "")
        req = (
            f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket handshake failed")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError("WebSocket handshake rejected: " + resp[:200].decode(errors="replace"))
        self.buf = resp.split(b"\r\n\r\n", 1)[1]

    def send(self, text):
        data = text.encode()
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("WebSocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        message = b""
        while True:
            b1, b2 = self._read(2)
            opcode = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if opcode == 0x8:
                raise ConnectionError("WebSocket closed by peer")
            if opcode in (0x9, 0xA):  # ping/pong: ignore
                continue
            message += payload
            if b1 & 0x80:
                return message.decode(errors="replace")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# TeamLogger control via DevTools
# --------------------------------------------------------------------------
def list_pages(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        return [t for t in json.load(r) if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]


def evaluate(ws_url, expression):
    ws = WebSocket(ws_url)
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
        }))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                res = msg.get("result", {})
                if "exceptionDetails" in res:
                    raise RuntimeError(res["exceptionDetails"].get("text", "JS error"))
                return res.get("result", {}).get("value")
    finally:
        ws.close()


# JavaScript run inside TeamLogger's window. Returns a JSON-able object.
JS_HELPERS = r"""
(() => {
  const visible = el => !!el && el.offsetParent !== null &&
      getComputedStyle(el).visibility !== 'hidden';
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const find = (selector, texts) => [...document.querySelectorAll(selector)]
      .find(el => visible(el) && texts.some(t => norm(el.textContent) === t || norm(el.textContent).startsWith(t)));
  window.__tlab = { visible, norm, find };
})();
"""

JS_STATUS = JS_HELPERS + r"""
(() => {
  const { find } = window.__tlab;
  return {
    canBreak:  !!find('button', ['take a break']),
    canResume: !!find('button', ['resume working', 'start timer', 'punch in']),
    inMeeting: !!find('button', ['end meeting mode']),
    title: document.title,
  };
})()
"""


def js_take_break(minutes):
    return JS_HELPERS + r"""
(async () => {
  const { find, visible, norm } = window.__tlab;
  const btn = find('button', ['take a break']);
  if (!btn) return { ok: false, reason: 'Take a break button not visible' };
  if (btn.disabled) return { ok: false, reason: 'Take a break button is disabled' };
  btn.click();
  // Some companies get a dropdown of break lengths after clicking.
  await new Promise(r => setTimeout(r, 800));
  const items = [...document.querySelectorAll('ul.ddmenu li')].filter(visible);
  if (items.length === 0) return { ok: true, mode: 'direct' };
  const want = %s;
  // Prefer "Indefinite": this app ends the break itself, so the length can be
  // extended from the phone. Fall back to the exact length if Indefinite isn't offered.
  let pick = items.find(li => norm(li.textContent) === 'indefinite')
          || items.find(li => norm(li.textContent) === want + 'm');
  if (!pick) {
    // fall back to the longest preset available; the script still resumes on schedule
    pick = items.filter(li => /^\d+m$/.test(norm(li.textContent))).pop();
  }
  if (!pick) return { ok: false, reason: 'Break dropdown opened but no option found' };
  const label = norm(pick.textContent);
  pick.click();
  return { ok: true, mode: 'dropdown', option: label };
})()
""" % json.dumps(int(minutes))


JS_RESUME = JS_HELPERS + r"""
(() => {
  const { find } = window.__tlab;
  const btn = find('button', ['resume working', 'start timer']);
  if (!btn && find('button', ['take a break']))
    return { ok: true, label: 'nothing (TeamLogger already resumed by itself)' };
  if (!btn) return { ok: false, reason: 'Resume/Start button not visible' };
  if (btn.disabled) return { ok: false, reason: 'Resume/Start button is disabled (no project/task selected?)' };
  btn.click();
  return { ok: true, label: btn.textContent.replace(/\s+/g, ' ').trim() };
})()
"""


JS_TOTAL = r"""
(() => {
  // TeamLogger shows e.g. "01 hours 55 minutes" above "current working day"
  const lab = [...document.querySelectorAll('div')]
    .find(e => e.children.length === 0 && /current working day/.test(e.textContent || ''));
  let text = lab && lab.previousElementSibling ? lab.previousElementSibling.textContent : '';
  const m = (text || '').match(/(\d+)\s*hours?\D+(\d+)\s*min/i);
  let secs = m ? (parseInt(m[1]) * 3600 + parseInt(m[2]) * 60) : null;
  try {
    const r = angular.element(document.body).injector().get('$rootScope');
    const h = parseFloat(r.activeHours || 0) + parseFloat(r.offComputerHours || 0);
    if (secs === null && h > 0) secs = Math.round(h * 3600);
  } catch (e) {}
  return secs;
})()
"""


def read_today_total(port):
    """TeamLogger's own total for the current working day, in seconds (or None)."""
    try:
        page, _ = find_main_page(port)
        if page:
            v = evaluate(page["webSocketDebuggerUrl"], JS_TOTAL)
            return int(v) if v is not None else None
    except Exception:
        pass
    return None


def find_main_page(port):
    """Return the DevTools page whose DOM contains the TeamLogger timer buttons."""
    for page in list_pages(port):
        try:
            st = evaluate(page["webSocketDebuggerUrl"], JS_STATUS)
        except Exception:
            continue
        if st and (st.get("canBreak") or st.get("canResume")):
            return page, st
    return None, None


def debug_port_open(port):
    try:
        list_pages(port)
        return True
    except Exception:
        return False


def teamlogger_pids():
    """(main_pids, all_pids) of running TeamLogger processes (matched by process name)."""
    out = subprocess.run(["pgrep", "-x", "teamlogger"], capture_output=True, text=True).stdout
    all_pids, main = [], []
    for p in out.split():
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        all_pids.append(int(p))
        if not any(a.startswith(b"--type=") for a in args):  # Electron helpers carry --type=
            main.append(int(p))
    return main, all_pids


def stop_teamlogger(timeout=15):
    """Quit TeamLogger cleanly and wait until every process is gone.

    Only the *main* process is signalled. Killing its renderer processes makes
    TeamLogger think it crashed and relaunch itself instantly (without our
    flags), which then holds the single-instance lock.
    """
    main, _ = teamlogger_pids()
    for p in main:
        try:
            os.kill(p, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not teamlogger_pids()[1]:
            return True
        time.sleep(0.3)
    for p in teamlogger_pids()[0]:  # still there: force the main process (no relaunch possible)
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(2)
    return not teamlogger_pids()[1]


def start_teamlogger(port):
    cmd = [TEAMLOGGER_BIN, f"--remote-debugging-port={port}", "--remote-allow-origins=*"]
    # Start TeamLogger as its own app ("teamlogger"), not as a child of this script.
    # GNOME decides who may take silent screenshots by that identity: if TeamLogger
    # is started from inside another app it inherits that app's identity and its
    # screenshots are refused (portal response code=2).
    if shutil.which("systemd-run"):
        unit = f"app-gnome-teamlogger-{os.getpid()}{int(time.time()) % 100000}"
        cmd = ["systemd-run", "--user", "--scope", "--quiet", "--collect", f"--unit={unit}"] + cmd
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def launch_teamlogger(port, attempts=3):
    if debug_port_open(port):
        log(f"TeamLogger debug port {port} already open.")
        return
    for attempt in range(1, attempts + 1):
        log(f"Restarting TeamLogger with the debug port enabled (attempt {attempt})...")
        stop_teamlogger()
        start_teamlogger(port)
        for _ in range(45):
            time.sleep(1)
            if debug_port_open(port):
                log("TeamLogger is up.")
                time.sleep(5)  # let the UI finish loading
                return
            # Our copy can lose the race to a self-relaunched TeamLogger (no port);
            # if that one is running and ours has exited, try again.
            if teamlogger_pids()[0] and not any(
                    b"--remote-debugging-port" in open(f"/proc/{p}/cmdline", "rb").read()
                    for p in teamlogger_pids()[0] if os.path.exists(f"/proc/{p}/cmdline")):
                log("A TeamLogger without the debug port took over; retrying.")
                break
    sys.exit("TeamLogger did not open the debug port. Is it installed at " + TEAMLOGGER_BIN + "?")


def do_with_retries(port, action, attempts=10, delay=6):
    """Run action(ws_url) against the main page, retrying while the UI is busy."""
    last = None
    for i in range(attempts):
        try:
            page, _ = find_main_page(port)
            if page is None:
                last = {"ok": False, "reason": "TeamLogger timer screen not found (is it logged in and on the timer page?)"}
            else:
                last = action(page["webSocketDebuggerUrl"])
                if last and last.get("ok"):
                    return last
        except Exception as e:  # port closed, app restarting, etc.
            last = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
        if i < attempts - 1:
            time.sleep(delay)
    return last


def take_break(port, minutes, dry_run):
    if dry_run:
        log(f"[dry run] would click 'Take a break' ({minutes} min)")
        return True
    res = do_with_retries(port, lambda ws: evaluate(ws, js_take_break(minutes)))
    if res and res.get("ok"):
        extra = f", picked '{res['option']}' from dropdown" if res.get("mode") == "dropdown" else ""
        log(f"Clicked 'Take a break'{extra}.")
        return True
    log(f"FAILED to take a break: {res and res.get('reason')}")
    return False


def resume(port, dry_run):
    if dry_run:
        log("[dry run] would click 'Resume Working'")
        return True
    res = do_with_retries(port, lambda ws: evaluate(ws, JS_RESUME))
    if res and res.get("ok"):
        log(f"Clicked '{res['label']}'.")
        return True
    log(f"FAILED to resume: {res and res.get('reason')}")
    return False


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------
def parse_breaks(at_list, default_minutes, parser):
    breaks = []
    for item in at_list:
        t, _, mins = item.partition("=")
        try:
            hh, mm = (int(x) for x in t.strip().split(":"))
            when = dt.time(hh, mm)
        except ValueError:
            parser.error(f"bad time '{t}', use HH:MM (24-hour)")
        if mins:
            minutes = float(mins)
        elif default_minutes is not None:
            minutes = default_minutes
        else:
            parser.error(f"no duration for {t}: use --duration N or --at {t}=N")
        if minutes <= 0:
            parser.error("duration must be positive")
        breaks.append((when, minutes))
    return sorted(breaks)


def sleep_until(target):
    while True:
        remaining = (target - dt.datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))  # short naps so laptop suspend doesn't cause long overshoot


def main():
    p = argparse.ArgumentParser(description="Auto take a break / resume in TeamLogger on a schedule.")
    p.add_argument("--at", action="append", default=[], metavar="HH:MM[=MIN]",
                   help="Break start time (24h). Repeatable. Optional '=MIN' sets that break's length.")
    p.add_argument("--duration", type=float, metavar="MIN", help="Default break length in minutes.")
    p.add_argument("--days", default="mon,tue,wed,thu,fri,sat,sun",
                   help="Days to run, e.g. mon,tue,wed,thu,fri (default: every day).")
    p.add_argument("--once", action="store_true", help="Exit after today's last break instead of repeating daily.")
    p.add_argument("--launch", action="store_true", help="Restart TeamLogger with the debug port if it isn't open.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Debug port (default {DEFAULT_PORT}).")
    p.add_argument("--dry-run", action="store_true", help="Log what would happen without clicking.")
    p.add_argument("--status", action="store_true", help="Show whether the buttons are found, then exit.")
    p.add_argument("--break-now", type=float, metavar="MIN",
                   help="Take a break right now for MIN minutes, resume, then exit.")
    args = p.parse_args()

    if args.launch:
        launch_teamlogger(args.port)
    elif not debug_port_open(args.port) and not args.dry_run:
        sys.exit(f"TeamLogger's debug port {args.port} is not open. Re-run with --launch "
                 f"(it restarts TeamLogger with the port enabled).")

    if args.status:
        page, st = find_main_page(args.port)
        if not page:
            sys.exit("Connected, but the TeamLogger timer screen was not found.")
        print(f"Window: {st['title']!r}")
        print(f"'Take a break' visible: {st['canBreak']}")
        print(f"'Resume Working'/'Start Timer' visible: {st['canResume']}")
        return

    if args.break_now:
        if take_break(args.port, args.break_now, args.dry_run):
            log(f"On break for {args.break_now:g} min...")
            sleep_until(dt.datetime.now() + dt.timedelta(minutes=args.break_now))
            resume(args.port, args.dry_run)
        return

    if not args.at:
        p.error("give at least one --at time (or use --status / --break-now)")
    breaks = parse_breaks(args.at, args.duration, p)
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    days = {day_names.index(d.strip()[:3].lower()) for d in args.days.split(",") if d.strip()}

    log("Schedule: " + ", ".join(f"{t:%H:%M} for {m:g} min" for t, m in breaks)
        + f" on {','.join(day_names[d] for d in sorted(days))}")

    while True:
        now = dt.datetime.now()
        upcoming = []
        for offset in range(0, 8):
            day = now.date() + dt.timedelta(days=offset)
            if day.weekday() not in days:
                continue
            for t, m in breaks:
                start = dt.datetime.combine(day, t)
                if start > now:
                    upcoming.append((start, m))
            if upcoming:
                break
        if not upcoming:
            log("No upcoming breaks.")
            return
        start, minutes = upcoming[0]
        if args.once and start.date() != now.date():
            log("No more breaks today; exiting (--once).")
            return
        log(f"Next break at {start:%a %H:%M} for {minutes:g} min.")
        sleep_until(start)

        if dt.datetime.now() - start > dt.timedelta(minutes=5):
            log("Woke up more than 5 minutes late (computer asleep?); skipping this break.")
            continue

        if take_break(args.port, minutes, args.dry_run):
            end = start + dt.timedelta(minutes=minutes)
            log(f"Will resume at {end:%H:%M}.")
            sleep_until(end)
            resume(args.port, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopped.")

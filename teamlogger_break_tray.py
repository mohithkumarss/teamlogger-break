#!/usr/bin/env python3
"""
Top-bar (tray) icon for ZenMetrics.

Started automatically by teamlogger_break_gui.py. Talks to it over a local
Unix socket: shows the current status, opens the window, or quits the app.
Exits by itself when the main app goes away.
"""

import json
import os
import socket
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402

SOCK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "teamlogger-break.sock")

LEAD = float(os.environ.get("TLB_LEAD_MS", "100")) / 1000  # see Tray.tick

# Top-bar icon: a small progress ring drawn as SVG frames (STEPS per lap).
#   work  = light blue ring filling up towards the next break, dot in the centre
#   break = amber ring filling up through the break, pause bars in the centre
#   off   = grey empty ring
STEPS = 24
ICON_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                        "teamlogger-break", "tray-icons")
COLORS = {"work": "#8CB4FF", "break": "#FFB050", "off": "#A0A0A8"}


def ring_svg(frac, mode, blink=False):
    import math
    cx = cy = 12
    r = 8.6
    col = COLORS.get(mode, COLORS["off"])
    parts = [f'<circle cx="12" cy="12" r="{r}" fill="none" stroke="#FFFFFF" stroke-opacity="0.26" '
             f'stroke-width="2.6"/>']
    if mode != "off" and frac > 0:
        if frac >= 0.999:
            parts.append(f'<circle cx="12" cy="12" r="{r}" fill="none" stroke="{col}" stroke-width="2.6"/>')
        else:
            a = -math.pi / 2 + 2 * math.pi * frac
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            large = 1 if frac > 0.5 else 0
            parts.append(f'<path d="M12 {cy - r:.2f} A{r} {r} 0 {large} 1 {x:.2f} {y:.2f}" fill="none" '
                         f'stroke="{col}" stroke-width="2.6" stroke-linecap="round"/>')
    if not blink:
        if mode == "break":
            parts.append(f'<rect x="9.2" y="8.6" width="2" height="6.8" rx="1" fill="{col}"/>'
                         f'<rect x="12.8" y="8.6" width="2" height="6.8" rx="1" fill="{col}"/>')
        elif mode == "work":
            parts.append(f'<circle cx="12" cy="12" r="2.3" fill="{col}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
            + "".join(parts) + "</svg>")


def icon_name(frac, mode, blink=False):
    """Write (once) and return the name of the frame for this state."""
    step = 0 if mode == "off" else max(0, min(STEPS, int(round(frac * STEPS))))
    name = f"tlb-{mode}-{step:02d}{'-b' if blink else ''}"
    path = os.path.join(ICON_DIR, name + ".svg")
    if not os.path.exists(path):
        os.makedirs(ICON_DIR, exist_ok=True)
        with open(path, "w") as f:
            f.write(ring_svg(step / STEPS, mode, blink))
    return name


def send(cmd):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(SOCK)
        s.sendall(cmd.encode() + b"\n")
        return s.recv(65536).decode().strip()
    finally:
        s.close()


class Tray:
    def __init__(self):
        os.makedirs(ICON_DIR, exist_ok=True)
        first = icon_name(0, "off")
        self.ind = AppIndicator.Indicator.new_with_path(
            "teamlogger-break", first, AppIndicator.IndicatorCategory.APPLICATION_STATUS, ICON_DIR)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("ZenMetrics")

        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="Starting…")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())
        for label, cmd in (("Open window", "show"), ("Resume now (end break)", "resume"),
                           ("Skip next break", "skip-next"), ("Skip today's remaining breaks", "skip-today"),
                           ("Undo skipped breaks", "unskip"), ("Quit ZenMetrics", "quit")):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _w, c=cmd: self.command(c))
            menu.append(item)
        menu.show_all()
        self.ind.set_menu(menu)
        self.failures = 0
        self.tick()

    def tick(self):
        """Push the label for the coming second slightly *before* that second starts.

        Ubuntu's AppIndicator extension batches label changes (30 ms + a D-Bus
        property read + 60 ms, at idle priority), so a label sent exactly on the
        second shows up ~0.1 s after the top-bar clock changes. Sending it LEAD
        early makes both change together. Tune with TLB_LEAD_MS if needed.
        """
        if not self.refresh(shown_at=getattr(self, "_next_edge", time.time())):
            return False
        now = time.time()
        edge = int(now) + 1
        if edge - LEAD <= now + 0.05:   # too close to this edge: aim for the next one
            edge += 1
        self._next_edge = edge
        GLib.timeout_add(max(1, int((edge - LEAD - now) * 1000)), self.tick)
        return False  # one-shot; re-armed above

    def command(self, cmd):
        try:
            send(cmd)
        except OSError:
            pass
        if cmd == "quit":
            Gtk.main_quit()
        else:
            self.refresh()

    def refresh(self, shown_at=None):
        try:
            st = json.loads(send("status"))
            self.failures = 0
        except (OSError, ValueError):
            self.failures += 1
            if self.failures >= 10:  # main app is gone
                Gtk.main_quit()
                return False
            return True
        self.status_item.set_label(st.get("text", ""))
        target = st.get("target")
        if target:  # count down from the clock here, not from when the app last updated
            # value as it should read at the moment it appears on screen
            left = max(0, int(round(target - (shown_at or time.time()))))
            h, rem = divmod(left, 3600)
            m, s = divmod(rem, 60)
            label = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        else:
            label = st.get("label", "")
        if label != getattr(self, "_last_label", None):
            self._last_label = label
            self.ind.set_label(label, "00:00:00")
        mode = st.get("mode") or ("break" if st.get("on_break") else "work" if st.get("running") else "off")
        frac = float(st.get("frac") or 0)
        left = (target - time.time()) if target else None
        if mode != getattr(self, "_mode", None):
            self._mode = mode
            self.sweep(frac, mode)          # little animation on state change
        elif not getattr(self, "_sweeping", False):
            blink = left is not None and left < 60 and int(time.time()) % 2 == 1   # last minute: blink
            self.set_icon(icon_name(frac, mode, blink))
        return True

    def set_icon(self, name):
        if name != getattr(self, "_last_icon", None):
            self._last_icon = name
            self.ind.set_icon_full(name, "ZenMetrics")

    def sweep(self, frac, mode):
        """Spin the ring from empty to its current position (~0.6 s)."""
        frames = [icon_name(frac * k / 10, mode) for k in range(11)]
        self._sweeping = True

        def step(i=[0]):
            self.set_icon(frames[i[0]])
            i[0] += 1
            if i[0] >= len(frames):
                self._sweeping = False
                return False
            return True
        GLib.timeout_add(55, step)


if __name__ == "__main__":
    Tray()
    Gtk.main()

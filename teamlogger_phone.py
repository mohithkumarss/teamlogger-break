"""
Phone notifications for the TeamLogger Break Scheduler, via ntfy (https://ntfy.sh).

Install the free "ntfy" app on your phone and subscribe to your topic (shown in
the app's Phone settings). Then, for every break:

  * "On break" notification that counts down (updated in place every minute),
  * a warning a few minutes before the break ends (optional),
  * an alarm when the break ends, repeating every minute until you stop it.

The warning and alarm are *scheduled on the ntfy server* when the break starts,
so they still arrive if the laptop loses its connection while you're out.

Buttons on the phone (+5 min, +10 min, Resume now, Stop alarm) send a message
to a second "control" topic that this app listens to.

Privacy: messages go through the ntfy server you choose (ntfy.sh by default).
They contain only break times. Anyone who knows the topic name can read them
or press the buttons, so the topic is a long random name — keep it private.
"""

import datetime
import json
import queue
import secrets
import string
import threading
import time
import urllib.error
import urllib.request

import socket

# Try IPv4 before IPv6. On networks that advertise IPv6 but don't route it,
# every request would otherwise hang ~20-45 s before falling back.
_getaddrinfo = socket.getaddrinfo


def _ipv4_first(*args, **kwargs):
    return sorted(_getaddrinfo(*args, **kwargs), key=lambda r: r[0] != socket.AF_INET)


socket.getaddrinfo = _ipv4_first

DEFAULT_SERVER = "https://ntfy.sh"
UA = "teamlogger-break/1.1"
MIN_DELAY = 12          # ntfy needs at least 10 s for scheduled delivery


def new_topic():
    alphabet = string.ascii_lowercase + string.digits
    return "tlb-" + "".join(secrets.choice(alphabet) for _ in range(14))


def default_phone_config():
    return {
        "enabled": False,
        "server": DEFAULT_SERVER,
        "topic": new_topic(),
        "warn_min": 5,          # 0 = no warning before the break ends
        "alarm": True,          # urgent priority + repeats; False = one normal notification
        "alarm_repeats": 3,     # how many times the alarm rings (one minute apart)
        "laptop_sound": True,   # also play a sound on this computer
    }


def fmt12(t):
    return t.strftime("%I:%M %p").lstrip("0")


class Phone:
    def __init__(self, get_cfg, on_command, log):
        self.get_cfg = get_cfg          # -> phone config dict
        self.on_command = on_command    # called (in a worker thread) with "extend:5" / "resume" / "ack"
        self.log = log
        self.jobs = queue.Queue()
        self.scheduled = []             # sequence ids of scheduled (not yet delivered) messages
        self.live_seq = None
        self.last_live_min = None
        self.listener_gen = 0
        threading.Thread(target=self._worker, daemon=True).start()

    # ------------------------------------------------------------ config
    @property
    def cfg(self):
        return self.get_cfg()

    def enabled(self):
        return bool(self.cfg.get("enabled") and self.cfg.get("topic"))

    def server(self):
        return (self.cfg.get("server") or DEFAULT_SERVER).rstrip("/")

    def topic(self):
        return self.cfg["topic"]

    def control_topic(self):
        return self.cfg["topic"] + "-ctl"

    # ------------------------------------------------------------ transport
    def _worker(self):
        while True:
            fn = self.jobs.get()
            try:
                fn()
            except Exception as e:  # network trouble must never break the app
                self.log(f"Phone: {type(e).__name__}: {e}")

    def _request(self, method, url, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"User-Agent": UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status

    def publish(self, seq, title, message, priority=3, tags=None, actions=None, at=None, click=None):
        """Queue a message. `at` = unix time for scheduled delivery."""
        if not self.enabled():
            return
        msg = {"topic": self.topic(), "title": title, "message": message,
               "priority": priority, "tags": tags or [], "sequence_id": seq}
        if actions:
            msg["actions"] = actions
        if click:
            msg["click"] = click
        if at is not None and at - time.time() >= MIN_DELAY:
            msg["delay"] = str(int(at))
            self.scheduled.append(seq)
        self.jobs.put(lambda: self._request("POST", self.server() + "/", msg))

    def delete(self, seq):
        """Remove a message: cancels it if scheduled, removes it from the phone if delivered."""
        if not self.enabled():
            return
        if seq in self.scheduled:
            self.scheduled.remove(seq)
        url = f"{self.server()}/{self.topic()}/{seq}"

        def go():
            try:
                self._request("DELETE", url)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
        self.jobs.put(go)

    def _button(self, label, command, clear=True):
        return {"action": "http", "label": label, "method": "POST",
                "url": f"{self.server()}/{self.control_topic()}", "body": command, "clear": clear}

    # ------------------------------------------------------------ listening for phone buttons
    def start_listener(self):
        """(Re)start listening to the control topic. Safe to call after settings change."""
        self.listener_gen += 1
        gen = self.listener_gen
        threading.Thread(target=self._listen, args=(gen,), daemon=True).start()

    def _listen(self, gen):
        since = str(int(time.time()))
        backoff = 5
        while gen == self.listener_gen:
            if not self.enabled():
                time.sleep(5)
                continue
            url = f"{self.server()}/{self.control_topic()}/json?since={since}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as r:
                    backoff = 5
                    for line in r:
                        if gen != self.listener_gen:
                            return
                        try:
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        if ev.get("event") != "message":
                            continue
                        since = ev.get("id", since)
                        cmd = (ev.get("message") or "").strip().lower()
                        if cmd:
                            self.on_command(cmd)
            except Exception:
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)

    # ------------------------------------------------------------ break lifecycle
    @staticmethod
    def _base(start):
        return f"b{start:%m%d%H%M%S}"

    def reminder(self, start, end):
        self.publish(f"{self._base(start)}-soon", "Break in 2 minutes",
                     f"{fmt12(start)} – {fmt12(end)}", priority=3, tags=["hourglass_flowing_sand"])

    def break_started(self, start, end):
        self.delete(f"{self._base(start)}-soon")
        self.live_seq = f"{self._base(start)}-live"
        self.last_live_min = None
        self.update_live(start, end, first=True)
        self._schedule_end(start, end)

    def update_live(self, start, end, first=False):
        """Refresh the countdown notification (call every second; sends only when needed)."""
        if not self.live_seq:
            return
        left = max(0, end.timestamp() - time.time())
        mins = int(-(-left // 60))  # round up
        total = (end - start).total_seconds() / 60
        step = 1 if total <= 60 else 5
        if not first and (mins == self.last_live_min or mins % step and mins > 1):
            return
        self.last_live_min = mins
        actions = [self._button("+5 min", "extend:5", clear=False),
                   self._button("+10 min", "extend:10", clear=False),
                   self._button("Resume now", "resume")]
        self.publish(self.live_seq,
                     f"On break · {mins} min left" if mins else "Break is ending",
                     f"Back to work at {fmt12(end)}",
                     priority=4 if first else 2, tags=["coffee"], actions=actions)

    def _schedule_end(self, start, end):
        cfg = self.cfg
        base = self._base(start)
        warn = int(cfg.get("warn_min") or 0)
        if warn and (end - start).total_seconds() > warn * 60 + 30:
            self.publish(f"{base}-warn", f"{warn} minutes left",
                         f"Break ends at {fmt12(end)}", priority=4, tags=["hourglass"],
                         actions=[self._button("+5 min", "extend:5")],
                         at=end.timestamp() - warn * 60)
        if cfg.get("alarm", True):
            repeats = max(1, int(cfg.get("alarm_repeats") or 1))
            for i in range(repeats):
                self.publish(f"{base}-alarm{i}", "⏰ Break over — back to work",
                             f"Your break ended at {fmt12(end)}" + (f" (reminder {i + 1}/{repeats})" if i else ""),
                             priority=5, tags=["alarm_clock"],
                             actions=[self._button("Stop alarm", "ack"), self._button("+5 min", "extend:5")],
                             at=end.timestamp() + i * 60)
        else:
            self.publish(f"{base}-alarm0", "Break over", f"Back to work — break ended at {fmt12(end)}",
                         priority=4, tags=["briefcase"], at=end.timestamp())

    def _cancel_scheduled(self):
        for seq in list(self.scheduled):
            self.delete(seq)

    def break_extended(self, start, end):
        """End time moved: cancel the old warning/alarms and schedule new ones."""
        self._cancel_scheduled()
        self._schedule_end(start, end)
        self.last_live_min = None
        self.update_live(start, end, first=False)

    def break_ended(self, start, end, early):
        if self.live_seq:
            self.delete(self.live_seq)
            self.live_seq = None
        if early:
            # back before the alarm: cancel the warning/alarms and say so once
            self._cancel_scheduled()
            self.publish(f"{self._base(start)}-back", "Back to work",
                         f"Resumed at {fmt12(datetime.datetime.now())}", priority=2, tags=["briefcase"])
        else:
            # The server delivers the first alarm right now (the warning already went out).
            # Later repeats stay scheduled until "Stop alarm" cancels them.
            self.scheduled = [s for s in self.scheduled if "-alarm" in s and not s.endswith("-alarm0")]

    def stop_alarm(self):
        """Phone 'Stop alarm' pressed: cancel the remaining repeats."""
        for seq in [s for s in self.scheduled if "-alarm" in s]:
            self.delete(seq)

    def send_test(self):
        self.publish(f"test{int(time.time())}", "TeamLogger Break is connected",
                     "Phone notifications work. You'll get a countdown and an alarm for each break.",
                     priority=3, tags=["white_check_mark"],
                     actions=[self._button("Test a button", "ping")])

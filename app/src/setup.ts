// First-run setup (plan §4): Welcome · Find TeamLogger · Permission · Notifications ·
// Your breaks · Phone (optional) · Start at login + theme. Re-run from Settings → General.
import logoUrl from "../../data/teamlogger-break.svg?url";
import { api, inTauri, type TeamLoggerStatus } from "./api.ts";
import { app } from "./app.ts";
import { breakEditor } from "./dialogs.ts";
import { clear, errorToast, h, icon, switchEl, toast } from "./dom.ts";
import { fmtRangeHM } from "./fmt.ts";
import {
  loginEnabled, notificationPermission, pickTeamLogger, playChime, requestNotifications, sendNotification, setLogin,
  type Permission,
} from "./platform.ts";

interface Step {
  title: string;
  render: () => Node[];
  next?: string; // Continue button label
  optional?: boolean; // shows Skip
  leave?: () => void | Promise<void>; // runs when moving on (stop timers, save)
}

const toMin = (hm: string) => { const [a, b] = hm.split(":").map(Number); return a * 60 + b; };

function point(iconName: string, title: string, text: string) {
  return h("div", { class: "point" }, h("span", { class: "point-icon" }, icon(iconName)),
    h("div", {}, h("div", { class: "body-strong" }, title), h("div", { class: "sub" }, text)));
}

function statusRow(ok: boolean | null, title: string, detail: string, ...actions: Node[]) {
  const badge = h("span", { class: `badge ${ok === true ? "ok" : ok === false ? "bad" : "wait"}` },
    icon(ok === true ? "check" : ok === false ? "close" : "clock"));
  return h("div", { class: "status-row" }, badge,
    // file paths stay on one line (ellipsised, full path on hover); sentences wrap
    h("div", { class: "text" }, h("div", { class: "body-strong" }, title),
      h("div", { class: /^[/~]|^[A-Z]:\\/.test(detail) ? "sub ellipsis" : "sub", title: detail }, detail)),
    ...actions);
}

/** Show setup full-window. Resolves when the user finishes. */
export function runSetup(root: HTMLElement): Promise<void> {
  return new Promise((done) => {
    let index = 0;
    let dir = 1;
    const timers: number[] = [];
    const stopTimers = () => timers.splice(0).forEach(clearInterval);

    // ------------------------------------------------------------ steps
    const steps: Step[] = [
      {
        title: "Welcome",
        next: "Get started",
        render: () => [
          h("img", { class: "setup-logo", src: logoUrl, alt: "", width: 72, height: 72 }),
          h("h1", { class: "setup-title" }, "Welcome to TeamLogger Break"),
          h("p", { class: "sub setup-lead" }, "Breaks on a schedule, for the TeamLogger desktop app."),
          h("div", { class: "points" },
            point("coffee", "Real breaks in TeamLogger", "At the times you choose it presses TeamLogger's Take a break, and Resume when the break ends — so they're recorded as breaks."),
            point("clock", "A countdown you can see", "On this screen, in the menu bar or tray, and — if you like — on your phone."),
            point("lock", "Your data stays here", "Your schedule and history are kept on this computer. Nothing is sent anywhere unless you turn on phone alerts.")),
          h("p", { class: "tiny" }, "Unofficial — not made by or affiliated with TeamLogger."),
        ],
      },
      {
        title: "Find TeamLogger",
        render: () => {
          const box = h("div", { class: "status-box" }, statusRow(null, "Looking for TeamLogger…", "One moment"));
          const refresh = async () => {
            try {
              const st = await api.teamlogger_status();
              renderFind(box, st, refresh);
            } catch (e) { errorToast(e); }
          };
          refresh();
          return [
            h("h1", { class: "setup-title" }, "Find TeamLogger"),
            h("p", { class: "sub setup-lead" }, "This app works together with the TeamLogger desktop app on this computer."),
            box,
          ];
        },
      },
      {
        title: "Permission",
        render: () => {
          const consent = h("input", { type: "checkbox", id: "consent", checked: app.cfg.control_consent });
          const live = h("div", { class: "status-box" }, statusRow(null, "Checking the connection…", ""));
          const connectBtn = h("button", { class: "btn soft", disabled: !app.cfg.control_consent,
            on: { click: async () => {
              connectBtn.disabled = true;
              connectBtn.textContent = "Connecting…";
              await app.connectNow();
              connectBtn.disabled = !consent.checked;
              connectBtn.textContent = "Connect now";
              poll();
            } } }, "Connect now");
          consent.onchange = () => {
            connectBtn.disabled = !consent.checked;
            app.update({ control_consent: consent.checked });
          };
          const poll = async () => {
            try {
              const st = await api.teamlogger_status();
              clear(live, st.connected
                ? statusRow(true, "TeamLogger is connected", `Control port ${st.port} answers on this computer`)
                : statusRow(false, "Not connected yet", st.install ? "TeamLogger needs one restart with the control port" : "TeamLogger wasn't found — you can connect later", connectBtn));
            } catch { /* keep last */ }
          };
          poll();
          timers.push(window.setInterval(poll, 2500));
          return [
            h("h1", { class: "setup-title" }, "Let this app press TeamLogger's buttons"),
            h("div", { class: "points" },
              point("refresh", "TeamLogger restarts once", "It's started again with a control port, so this app can click Take a break and Resume. Its timer pauses for a few seconds."),
              point("lock", "Only this computer can reach it", `The port listens on this computer only (127.0.0.1). Nothing on your network or the internet can use it.`),
              point("check", "Breaks are normal breaks", "TeamLogger records them exactly as if you had clicked the buttons yourself.")),
            h("label", { class: "consent", for: "consent" }, consent,
              h("span", {}, "I agree that TeamLogger Break may restart TeamLogger with a local control port and press its break buttons.")),
            live,
            h("p", { class: "tiny" }, "Your choice is saved. You can connect later and change it any time in Settings."),
          ];
        },
        leave: stopTimers,
      },
      {
        title: "Notifications",
        render: () => {
          const box = h("div", { class: "status-box" });
          const draw = (p: Permission) => clear(box,
            statusRow(p === "granted" ? true : p === "denied" ? false : null,
              p === "granted" ? "Notifications are on" : p === "denied" ? "Notifications are blocked" : "Notifications aren't on yet",
              p === "denied" ? "Turn them on for TeamLogger Break in your system's notification settings"
                : "A heads-up 2 minutes before each break, and when it ends",
              p === "granted"
                ? h("button", { class: "btn soft", on: { click: () => { sendNotification("Break in 2 minutes", "1:00 – 1:40 PM · this is a test"); toast("Test notification sent"); } } }, "Send test")
                : h("button", { class: "btn primary small", disabled: p === "denied", on: { click: async () => draw(await requestNotifications()) } }, "Allow")),
            statusRow(true, "Alarm sound", "Plays when a break ends — check your volume",
              h("button", { class: "btn soft", on: { click: playChime } }, "Play")));
          notificationPermission().then(draw).catch(() => draw("default"));
          return [
            h("h1", { class: "setup-title" }, "Notifications and sound"),
            h("p", { class: "sub setup-lead" }, "So a break never takes you by surprise, and you know when it's time to get back."),
            box,
          ];
        },
      },
      {
        title: "Your breaks",
        render: () => {
          const list = h("div", { class: "rows" });
          const days = h("div", { class: "wrap" });
          const draw = () => {
            const sorted = [...app.cfg.breaks].sort((a, b) => a.start.localeCompare(b.start));
            clear(list, ...(sorted.length
              ? sorted.map((b) => h("button", { class: "prow", on: { click: () => breakEditor(b) } },
                  h("div", { class: "text" }, h("span", { class: "body-strong" }, fmtRangeHM(b.start, b.end)),
                    h("span", { class: "sub" }, `${toMin(b.end) - toMin(b.start)} minutes`)), icon("next")))
              : [h("div", { class: "prow" }, h("div", { class: "text" }, h("span", { class: "sub" }, "No breaks yet — add one or use the suggestion")))]));
            clear(days, ..."MTWTFSS".split("").map((l, i) => {
              const on = app.cfg.days.includes(i);
              const name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][i];
              return h("button", { class: `btn preset day${on ? " on" : ""}`, title: name, "aria-label": name, "aria-pressed": String(on),
                on: { click: () => app.update({ days: on ? app.cfg.days.filter((d) => d !== i) : [...app.cfg.days, i].sort() }) } }, l);
            }));
          };
          const unsubscribe = app.onConfig(draw);
          steps[4].leave = unsubscribe;
          draw();
          const suggest = h("button", { class: "btn soft", on: { click: async () => {
            try {
              app.setConfig(await api.set_breaks(await api.suggested_breaks()));
              toast("Suggested schedule added");
            } catch (e) { errorToast(e); }
          } } }, "Use suggested: 11:30 · 10m, 1:00 · 40m, 5:00 · 10m");
          return [
            h("h1", { class: "setup-title" }, "Your breaks"),
            h("p", { class: "sub setup-lead" }, "When should TeamLogger take a break for you? You can change this any time."),
            list,
            h("div", { class: "wrap" },
              h("button", { class: "btn soft", on: { click: () => breakEditor() } }, icon("plus"), "Add break"), suggest),
            h("div", { class: "card-title", style: "margin-top:6px" }, "Repeat on"),
            days,
          ];
        },
      },
      {
        title: "Phone",
        optional: true,
        render: () => {
          const qr = h("div", { class: "qr", "aria-label": "QR code for your ntfy topic" });
          const url = h("div", { class: "tiny ellipsis topic" });
          api.phone_qr().then((l) => { qr.innerHTML = l.svg; url.textContent = l.url; }).catch(errorToast);
          return [
            h("h1", { class: "setup-title" }, "Your phone", h("span", { class: "optional" }, "optional")),
            h("p", { class: "sub setup-lead" }, "A live countdown and an alarm on your phone, with buttons for +5 min and Resume — via the free ntfy app."),
            h("div", { class: "phone" }, qr,
              h("div", { class: "phone-steps" },
                h("div", { class: "sub" }, h("b", {}, "1. "), "Install ", h("b", {}, "ntfy"), " (Play Store / App Store)."),
                h("div", { class: "sub" }, h("b", {}, "2. "), "Scan the code, or subscribe in ntfy to this topic:"),
                h("div", { class: "row" }, h("span", { class: "num-sm topic ellipsis spacer" }, app.cfg.phone.topic),
                  h("button", { class: "btn icon-round", title: "Copy topic", "aria-label": "Copy topic", on: { click: async () => {
                    try { await navigator.clipboard.writeText(app.cfg.phone.topic); toast("Topic copied"); } catch (e) { errorToast(e); }
                  } } }, icon("copy"))),
                url,
                h("div", { class: "row", style: "margin-top:4px" },
                  h("span", { class: "body-strong spacer" }, "Phone notifications"),
                  switchEl(app.cfg.phone.enabled, "Phone notifications", (on) => app.update({ phone: { enabled: on } }))),
                h("button", { class: "btn soft", on: { click: () => app.phoneTest() } }, "Send test"))),
            h("p", { class: "tiny" }, "Messages go through ntfy.sh and contain only break times. Keep the topic private — anyone who knows it could see your breaks or press the buttons."),
          ];
        },
      },
      {
        title: "Finish",
        next: "Start using TeamLogger Break",
        render: () => {
          const login = switchEl(app.cfg.login, "Start at login", async (on) => {
            try {
              const now = await setLogin(on);
              if (!inTauri) toast("Start at login works in the desktop app");
              app.update({ login: now });
            } catch (e) { errorToast(e); }
          });
          loginEnabled().then((on) => login.setAttribute("aria-checked", String(on))).catch(() => {});
          const themes: ["system" | "light" | "dark", string][] = [["system", "System"], ["light", "Light"], ["dark", "Dark"]];
          const seg = h("div", { class: "seg compact" });
          const drawSeg = () => clear(seg, ...themes.map(([k, l]) =>
            h("button", { class: app.cfg.theme === k ? "on" : "", on: { click: async () => { await app.update({ theme: k }); drawSeg(); } } }, l)));
          drawSeg();
          return [
            h("h1", { class: "setup-title" }, "Almost done"),
            h("p", { class: "sub setup-lead" }, "Two last choices. Everything here is also in Settings."),
            h("div", { class: "rows" },
              h("div", { class: "prow" }, h("div", { class: "text" }, h("span", { class: "body-strong" }, "Start at login"),
                h("span", { class: "sub" }, "So breaks happen even if you forget to open the app")), login),
              h("div", { class: "prow" }, h("div", { class: "text" }, h("span", { class: "body-strong" }, "Theme")), seg)),
          ];
        },
      },
    ];

    // ------------------------------------------------------------ shell
    const dots = h("div", { class: "dots", "aria-hidden": "true" });
    const body = h("div", { class: "step" });
    const back = h("button", { class: "btn quiet", on: { click: () => go(-1) } }, "Back");
    const skip = h("button", { class: "btn quiet", on: { click: () => go(1) } }, "Skip");
    const next = h("button", { class: "btn primary", on: { click: () => go(1) } });
    const counter = h("span", { class: "tiny" });
    const card = h("div", { class: "setup-card", role: "dialog", "aria-modal": "true", "aria-label": "Set up TeamLogger Break" },
      h("div", { class: "row" }, dots, h("span", { class: "spacer" }), counter),
      body,
      h("div", { class: "setup-nav" }, back, h("span", { class: "spacer" }), skip, next));
    const screen = h("div", { class: "setup", "data-tauri-drag-region": "" }, card);
    root.append(screen);

    async function go(delta: number) {
      await steps[index].leave?.();
      if (index + delta >= steps.length) {
        await app.update({ onboarded: true });
        screen.classList.add("leaving");
        setTimeout(() => { screen.remove(); done(); }, 260);
        return;
      }
      dir = delta;
      index = Math.max(0, index + delta);
      render();
    }

    function render() {
      const s = steps[index];
      clear(dots, ...steps.map((_, i) => h("span", { class: `d${i === index ? " on" : i < index ? " past" : ""}` })));
      counter.textContent = `${index + 1} of ${steps.length}`;
      clear(body, ...s.render());
      body.classList.remove("in-left", "in-right");
      void body.offsetWidth; // restart the slide-in
      body.classList.add(dir > 0 ? "in-right" : "in-left");
      back.style.visibility = index === 0 ? "hidden" : "visible";
      skip.hidden = !s.optional;
      next.textContent = s.next ?? "Continue";
      next.focus({ preventScroll: true });
    }

    function renderFind(box: HTMLElement, st: TeamLoggerStatus, refresh: () => void) {
      const browse = h("button", { class: "btn soft", on: { click: async () => {
        if (!inTauri) return toast("Browse works in the desktop app");
        try {
          const p = await pickTeamLogger(st.os);
          if (!p) return;
          app.setConfig(await api.set_teamlogger_path(p));
          refresh();
        } catch (e) { errorToast(e); }
      } } }, "Browse…");
      const where = st.os === "macos" ? "Applications" : st.os === "windows" ? "Program Files or your user's Programs folder" : "/opt/teamlogger";
      clear(box,
        st.install
          ? statusRow(true, st.install.how === "chosen" ? "Using the TeamLogger you chose" : "Found TeamLogger", st.install.path, browse)
          : statusRow(false, "TeamLogger wasn't found", `Looked in ${where}. If it's installed somewhere else, choose it.`, browse),
        st.install?.how === "chosen"
          ? h("button", { class: "btn quiet", style: "align-self:flex-start", on: { click: async () => { app.setConfig(await api.set_teamlogger_path(null)); refresh(); } } }, "Find it automatically instead")
          : h("button", { class: "btn quiet", style: "align-self:flex-start", on: { click: refresh } }, "Check again"),
        !st.install && h("p", { class: "tiny" }, "No TeamLogger yet? You can finish setup now and choose it later in Settings."));
      next.textContent = st.install ? "Continue" : "Continue without it";
    }

    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.target as Element).tagName !== "BUTTON" && (e.target as Element).tagName !== "INPUT") go(1);
    });
    render();
  });
}

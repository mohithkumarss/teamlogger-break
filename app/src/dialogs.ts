// Dialogs: break editor, take-a-break-now, settings, phone setup, activity log.
import { api, inTauri, type Break } from "./api.ts";
import { app } from "./app.ts";
import { clear, errorToast, h, icon, setSwitch, sheet, switchEl, toast } from "./dom.ts";
import { loginEnabled, pickTeamLogger, setLogin } from "./platform.ts";
import { fmtRangeHM, pad2 } from "./fmt.ts";

// ---------------------------------------------------------------- break editor
const PRESETS = [5, 10, 15, 20, 30, 40, 45, 60, 90];
const toMin = (hm: string) => { const [a, b] = hm.split(":").map(Number); return a * 60 + b; };
const toHM = (m: number) => `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;

export function breakEditor(old?: Break) {
  let start: number, len: number;
  if (old) {
    start = toMin(old.start);
    len = toMin(old.end) - start;
  } else {
    const last = [...app.cfg.breaks].sort((a, b) => a.start.localeCompare(b.start)).at(-1);
    start = last ? Math.min(Math.floor(toMin(last.end) / 60) + 2, 22) * 60 : 13 * 60;
    len = 15;
  }
  const s = sheet();
  const hourVal = h("div", { class: "val" });
  const minVal = h("div", { class: "val" });
  const am = h("button", { class: "btn" }, "AM");
  const pm = h("button", { class: "btn" }, "PM");
  const minutes = h("input", { class: "minutes", type: "number", min: "1", max: "240", "aria-label": "Length in minutes" });
  const summary = h("div", { class: "body-strong", style: "margin-top:6px" });
  const presetBtns = PRESETS.map((m) => h("button", { class: "btn preset", on: { click: () => { len = m; render(); } } }, `${m}m`));

  const stepper = (val: HTMLElement, label: string, delta: number) =>
    h("div", { class: "stepper" },
      h("button", { "aria-label": `${label} up`, on: { click: () => { start = (start + delta + 1440) % 1440; render(); } } }, icon("up")),
      val,
      h("button", { "aria-label": `${label} down`, on: { click: () => { start = (start - delta + 1440) % 1440; render(); } } }, icon("down")));
  am.onclick = () => { if (start >= 720) start -= 720; render(); };
  pm.onclick = () => { if (start < 720) start += 720; render(); };
  minutes.oninput = () => { const v = Math.round(Number(minutes.value)); if (v >= 1 && v <= 240) { len = v; render(false); } };

  function render(syncInput = true) {
    start -= start % 5 === 0 ? 0 : start % 5;
    hourVal.textContent = String(Math.floor(start / 60) % 12 || 12);
    minVal.textContent = pad2(start % 60);
    am.classList.toggle("on", start < 720);
    pm.classList.toggle("on", start >= 720);
    presetBtns.forEach((b, i) => b.classList.toggle("on", PRESETS[i] === len));
    if (syncInput) minutes.value = String(len);
    const end = start + len;
    summary.textContent = end >= 1440 ? "Must end before midnight" : `${fmtRangeHM(toHM(start), toHM(end))}  ·  ${len} min`;
  }

  async function save() {
    if (start + len >= 1440) return toast("A break must end before midnight");
    if (await app.saveBreak(toHM(start), toHM(start + len), old)) s.close();
  }

  s.body.append(
    h("h2", { class: "dialog-title" }, old ? "Edit break" : "New break"),
    h("div", { class: "card-title" }, "Starts at"),
    h("div", { class: "time-row" }, stepper(hourVal, "Hour", 60), h("div", { class: "stepper" }, h("div", { class: "val", style: "min-width:0" }, ":")),
      stepper(minVal, "Minute", 5), h("div", { class: "ampm" }, am, pm)),
    h("div", { class: "card-title", style: "margin-top:4px" }, "Length"),
    h("div", { class: "wrap" }, ...presetBtns),
    h("div", { class: "row" }, h("span", { class: "sub" }, "or"), minutes, h("span", { class: "sub" }, "minutes")),
    summary,
    h("div", { class: "row", style: "gap:10px;margin-top:4px" },
      h("button", { class: "btn primary", style: "flex:1", on: { click: save } }, "Save"),
      old && h("button", { class: "btn danger", on: { click: async () => { await app.removeBreak(old); s.close(); } } }, "Delete")),
  );
  render();
}

// ---------------------------------------------------------------- take a break now
export function breakNowDialog() {
  const s = sheet();
  s.body.append(
    h("h2", { class: "dialog-title" }, "Take a break"),
    h("div", { class: "sub" }, "How long would you like?"),
    h("div", { class: "wrap" }, ...[5, 10, 15, 20, 30, 45, 60].map((m) =>
      h("button", { class: "btn preset", on: { click: () => { s.close(); app.breakNow(m); } } }, `${m} min`))),
    h("div", { class: "tiny" }, "You can extend it any time — here or from your phone."),
  );
}

// ---------------------------------------------------------------- activity log
export async function showLog() {
  const s = sheet({ wide: true });
  const lines = await api.activity_log();
  s.body.append(h("h2", { class: "dialog-title" }, "Activity log"), h("pre", { class: "log" }, lines.join("\n") || "Nothing yet."));
}

// ---------------------------------------------------------------- phone setup
export function phoneSetup() {
  const s = sheet({ wide: true });
  const topic = h("span", { class: "num-sm topic spacer ellipsis" }, app.cfg.phone.topic);
  s.body.append(
    h("h2", { class: "dialog-title" }, "Your phone"),
    h("div", { class: "sub" }, "1.  Install ", h("b", {}, "ntfy"), " — free on Play Store and App Store.", h("br"),
      "2.  Tap ", h("b", {}, "+"), " and subscribe to this topic:"),
    h("div", { class: "card", style: "padding:8px 8px 8px 18px" },
      h("div", { class: "row" }, topic,
        h("button", { class: "btn icon-round", title: "Copy", "aria-label": "Copy topic", on: { click: async () => {
          try { await navigator.clipboard.writeText(app.cfg.phone.topic); toast("Topic copied"); } catch (e) { errorToast(e); }
        } } }, icon("copy")))),
    h("div", { class: "tiny" },
      "3.  Press Send test — it should appear on your phone.", h("br"), h("br"),
      "For a loud alarm on Android: in ntfy open the topic → Notification settings → Urgent priority, and allow it to override Do Not Disturb.",
      h("br"), h("br"),
      "Messages go through ntfy.sh and contain only break times. Keep the topic private — anyone who knows it could see your breaks or press the buttons."),
    h("div", { class: "row", style: "gap:10px" },
      h("button", { class: "btn primary", style: "flex:1", on: { click: () => app.phoneTest() } }, "Send test"),
      h("button", { class: "btn soft", on: { click: async () => {
        try {
          app.setConfig(await api.new_phone_topic());
          topic.textContent = app.cfg.phone.topic;
          toast("New topic — subscribe to it on your phone");
        } catch (e) { errorToast(e); }
      } } }, "New topic")),
  );
}

// ---------------------------------------------------------------- settings
function prow(title: string, subtitle: string | null, suffix?: Node | null, onClick?: () => void, disabled = false) {
  const text = h("div", { class: "text" }, h("span", { class: "body-strong" }, title), subtitle && h("span", { class: "sub" }, subtitle));
  if (onClick) return h("button", { class: "prow", on: { click: onClick } }, text, suffix ?? icon("next"));
  return h("div", { class: `prow${disabled ? " disabled" : ""}` }, text, suffix);
}

function group(title: string | null, ...rows: Node[]) {
  return h("div", { class: "group" }, title && h("div", { class: "card-title" }, title), h("div", { class: "rows" }, ...rows));
}

function select<T extends string | number>(value: T, options: [T, string][], onChange: (v: T) => void) {
  const el = h("select", { "aria-label": "Choose" }, ...options.map(([v, l]) => h("option", { value: String(v), selected: v === value }, l)));
  el.onchange = () => onChange(options[el.selectedIndex][0]);
  return el;
}

export function openSettings(initial = "schedule") {
  let unsubscribe = () => {};
  const s = sheet({ wide: true, onClose: () => { unsubscribe(); app.dataChanged(); } });
  const content = h("div", { class: "scroll", style: "display:flex;flex-direction:column;gap:18px" });
  const tabs: [string, string][] = [["schedule", "Schedule"], ["phone", "Phone & alarm"], ["general", "General"]];
  const seg = h("div", { class: "seg" });
  let current = initial;

  const pages: Record<string, () => Node[]> = {
    schedule: () => {
      const cfg = app.cfg;
      const list = [...cfg.breaks].sort((a, b) => a.start.localeCompare(b.start));
      const breaks = list.length
        ? list.map((b) => prow(fmtRangeHM(b.start, b.end), `${toMin(b.end) - toMin(b.start)} minutes`, null, () => breakEditor(b)))
        : [prow("No breaks yet", "Add one with +")];
      const days = h("div", { class: "wrap", style: "padding:12px 16px" },
        ..."MTWTFSS".split("").map((l, i) => {
          const name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][i];
          const b = h("button", { class: `btn preset${cfg.days.includes(i) ? " on" : ""}`, style: "min-width:42px;width:42px;height:42px;padding:0", title: name, "aria-label": name, "aria-pressed": String(cfg.days.includes(i)) }, l);
          b.onclick = () => app.update({ days: cfg.days.includes(i) ? cfg.days.filter((d) => d !== i) : [...cfg.days, i].sort() });
          return b;
        }));
      return [
        group(null, prow("Automatic breaks", "Take and resume breaks in TeamLogger on schedule",
          switchEl(!!app.status?.running, "Automatic breaks", (on) => app.setRunning(on)))),
        h("div", { class: "group" },
          h("div", { class: "row" }, h("div", { class: "card-title spacer", style: "padding:0 4px" }, "Breaks · tap one to change it"),
            h("button", { class: "btn icon-round", title: "Add break", "aria-label": "Add break", on: { click: () => breakEditor() } }, icon("plus"))),
          h("div", { class: "rows" }, ...breaks)),
        group("Repeat on", days),
      ];
    },
    phone: () => {
      const p = app.cfg.phone;
      return [
        h("div", { class: "sub", style: "padding:0 4px" }, "Live countdown and an alarm on your phone, via the free ntfy app."),
        group(null,
          prow("Phone notifications", "Countdown, warning and alarm on your phone", switchEl(p.enabled, "Phone notifications", (on) => app.update({ phone: { enabled: on } }))),
          prow("Set up your phone", `Topic: ${p.topic}`, null, phoneSetup)),
        group("Alarm",
          prow("Warn before the break ends", null, select(p.warn_min, [[0, "Off"], [2, "2 minutes"], [5, "5 minutes"], [10, "10 minutes"]], (v) => app.update({ phone: { warn_min: v } }))),
          prow("Alarm when the break ends", "Urgent sound that repeats until you press Stop", switchEl(p.alarm, "Alarm", (on) => app.update({ phone: { alarm: on } }))),
          prow("Rings", "One minute apart", (() => {
            const i = h("input", { type: "number", min: "1", max: "10", value: String(p.alarm_repeats), disabled: !p.alarm, "aria-label": "Rings" });
            i.onchange = () => { const v = Math.max(1, Math.min(10, Math.round(Number(i.value)))); app.update({ phone: { alarm_repeats: v } }); };
            return i;
          })(), undefined, !p.alarm),
          prow("Ring on this computer too", null, switchEl(p.laptop_sound, "Ring on this computer", (on) => app.update({ phone: { laptop_sound: on } })))),
      ];
    },
    general: () => {
      const c = app.cfg;
      const location = h("span", { class: "sub ellipsis" }, "Looking…");
      const connection = h("span", { class: "sub" }, "Checking…");
      api.teamlogger_status().then((st) => {
        location.textContent = st.install ? st.install.path : "Not found — choose it";
        location.title = location.textContent;
        connection.textContent = st.connected ? "Connected" : "Not connected — press Connect (TeamLogger restarts once)";
        browse.onclick = async () => {
          if (!inTauri) return toast("Browse works in the desktop app");
          try {
            const p = await pickTeamLogger(st.os);
            if (p) app.setConfig(await api.set_teamlogger_path(p));
          } catch (e) { errorToast(e); }
        };
      }).catch(() => (location.textContent = "Unknown"));
      const browse = h("button", { class: "btn soft", style: "min-height:34px" }, "Browse…");
      const login = switchEl(c.login, "Start at login", async (on) => {
        try {
          const now = await setLogin(on);
          if (!inTauri) toast("Start at login works in the desktop app");
          setSwitch(login, now);
          app.update({ login: now });
        } catch (e) { errorToast(e); }
      });
      loginEnabled().then((on) => setSwitch(login, on)).catch(() => {});
      return [
        group("Appearance", prow("Theme", null, select(c.theme, [["system", "Follow system"], ["light", "Light"], ["dark", "Dark"]], (v) => app.update({ theme: v })))),
        group("TeamLogger",
          h("div", { class: "prow" }, h("div", { class: "text" }, h("span", { class: "body-strong" }, "TeamLogger app"), location), browse),
          h("div", { class: "prow" }, h("div", { class: "text" }, h("span", { class: "body-strong" }, "Connection"), connection),
            h("button", { class: "btn soft", style: "min-height:34px", on: { click: () => app.connect() } }, "Connect")),
          prow("Start at login", "Opens ZenMetrics when you log in", login),
          prow("Test mode", "Log what would happen without clicking TeamLogger", switchEl(c.dry_run, "Test mode", (on) => app.update({ dry_run: on }))),
          prow("Activity log", null, null, showLog),
          prow("Run setup again", "Welcome, TeamLogger, permissions, breaks, phone", null, () => { s.close(); app.openSetup(); })),
        group("About",
          prow("Version", `0.1.0 preview · ${inTauri ? "desktop app" : "browser preview (demo data)"}`),
          prow("Typeface", "Google Sans Flex · SIL Open Font License 1.1"),
          prow("Unofficial", "Not affiliated with TeamLogger")),
      ];
    },
  };

  function render() {
    clear(seg, ...tabs.map(([k, l]) => h("button", { class: k === current ? "on" : "", on: { click: () => { current = k; render(); } } }, l)));
    const scroll = content.scrollTop;
    clear(content, ...pages[current]());
    content.scrollTop = scroll;
  }

  s.body.append(h("h2", { class: "dialog-title" }, "Settings"), h("div", { class: "tabs" }, seg), content);
  unsubscribe = app.onConfig(render);
  render();
}

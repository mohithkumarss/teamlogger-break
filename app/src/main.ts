// App shell: header (theme · Today/Stats · settings · menu), views, 1-second tick.
import fontUrl from "../../fonts/GoogleSansFlex[ROND,opsz,slnt,wdth,wght].ttf?url";
import { api, inTauri } from "./api.ts";
import { app } from "./app.ts";
import { breakEditor, breakNowDialog, openSettings, showLog } from "./dialogs.ts";
import { errorToast, h, iconButton } from "./dom.ts";
import { runSetup } from "./setup.ts";
import { StatsView } from "./stats.ts";
import { TodayView } from "./today.ts";

// Google Sans Flex is the app's typeface on every OS (SIL OFL 1.1, see fonts/OFL.txt).
// It ships inside the app, so nothing depends on fonts installed on the machine.
// The first paint waits for it (briefly) so the UI never flashes in a system font.
const fontReady = new FontFace("Google Sans Flex", `url("${fontUrl}")`, { weight: "100 1000", stretch: "25% 151%" })
  .load()
  .then((f) => void document.fonts.add(f))
  .catch((e) => console.warn("Bundled font failed to load; using system fonts", e));

// Feel like an app, not a web page.
if (inTauri && /Mac/.test(navigator.platform)) document.documentElement.classList.add("macos");
if (import.meta.env.PROD) {
  // no browser context menu (Reload / Inspect / Back) except where you type
  document.addEventListener("contextmenu", (e) => {
    if (!(e.target as Element).closest("input, textarea, select")) e.preventDefault();
  });
  // no reload, find, print, view-source or caret-browsing shortcuts
  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    const k = e.key.toLowerCase();
    if (e.key === "F5" || e.key === "F3" || e.key === "F7" || (mod && ["r", "f", "g", "p", "j", "u"].includes(k))) e.preventDefault();
  }, { capture: true });
}
// dropping a file on the window must never navigate away from the app
for (const ev of ["dragover", "drop"]) document.addEventListener(ev, (e) => e.preventDefault());

await Promise.all([app.init(), Promise.race([fontReady, new Promise((r) => setTimeout(r, 1500))])]);

const today = new TodayView();
const stats = new StatsView();
const todayView = h("div", { class: "view" }, today.el);
const statsView = h("div", { class: "view", hidden: true }, stats.el);
let current: "today" | "stats" = "today";

const navToday = h("button", { class: "on", role: "tab", on: { click: () => show("today") } }, "Today");
const navStats = h("button", { role: "tab", on: { click: () => show("stats") } }, "Stats");

function show(view: "today" | "stats") {
  current = view;
  navToday.classList.toggle("on", view === "today");
  navStats.classList.toggle("on", view === "stats");
  todayView.hidden = view !== "today";
  statsView.hidden = view !== "stats";
  if (view === "stats") stats.refresh(true);
  else today.replay();
}

// ---------------------------------------------------------------- menu
let menu: HTMLElement | null = null;
function toggleMenu() {
  if (menu) return closeMenu();
  const item = (label: string, fn: () => void) => h("button", { on: { click: () => { closeMenu(); fn(); } } }, label);
  menu = h("div", { class: "menu", role: "menu" },
    item("Take a Break Now…", () => app.openBreakNow()),
    item("Skip Today's Breaks", () => app.skipToday()),
    h("hr"),
    item("Activity Log", showLog),
    item("Settings", () => app.openSettings()),
  );
  document.body.append(menu);
  setTimeout(() => document.addEventListener("click", closeMenu, { once: true }));
}
function closeMenu() {
  menu?.remove();
  menu = null;
}

const header = h("header", { class: "header", "data-tauri-drag-region": "" },
  h("div", { class: "left" },
    iconButton("theme", "Light / dark", () => app.toggleTheme(), "btn icon-round hide-narrow"),
    !inTauri && h("span", { class: "preview-badge hide-narrow", title: "Running in a browser with demo data" }, "Browser preview")),
  h("div", { class: "seg", role: "tablist" }, navToday, navStats),
  h("div", { class: "right" },
    iconButton("gear", "Settings", () => app.openSettings()),
    iconButton("more", "More", toggleMenu)));

document.getElementById("app")!.append(header, h("main", { class: "page" }, todayView, statsView));

// ---------------------------------------------------------------- wiring
app.showDay = (day) => { show("stats"); stats.select(day); };
app.openBreakEditor = breakEditor;
app.openBreakNow = breakNowDialog;
app.openSettings = openSettings;
app.openSetup = () => runSetup(document.body).then(() => app.dataChanged());
app.onData(() => {
  today.refresh();
  if (current === "stats") stats.refresh();
});

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === ",") { e.preventDefault(); app.openSettings(); }
  if ((e.metaKey || e.ctrlKey) && e.key === "1") show("today");
  if ((e.metaKey || e.ctrlKey) && e.key === "2") show("stats");
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => app.dataChanged());

// one tick per wall-clock second; data refresh every 5 s, stats every minute
async function tick() {
  try {
    app.status = await api.status();
    today.tick(app.status);
    const s = new Date().getSeconds();
    if (!document.hidden && s % 5 === 0) await today.refresh();
    if (s % 15 === 0) checkConnection();
    if (!document.hidden && s === 0 && current === "stats") await stats.refresh();
  } catch (e) {
    console.error(e);
  } finally {
    setTimeout(tick, 1000 - (Date.now() % 1000) + 15);
  }
}

function checkConnection() {
  api.teamlogger_status().then((st) => today.setConnected(st.connected)).catch(() => {});
}

// First run: the setup screen covers the window until it's finished.
if (!app.cfg.onboarded) await runSetup(document.body);

try {
  app.status = await api.status();
  today.tick(app.status);
  await today.refresh(true);
} catch (e) {
  errorToast(e);
}
checkConnection();
tick();

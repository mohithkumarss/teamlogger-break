// Shared state and actions used by the views.
import { api, type Config, type Status, type Break } from "./api.ts";
import { errorToast, toast, confirmDialog } from "./dom.ts";
import { fmtRangeHM, plural } from "./fmt.ts";

type Listener = () => void;

class AppState {
  cfg!: Config;
  status: Status | null = null;
  private listeners: Listener[] = [];
  private cfgListeners: Listener[] = [];

  // hooks the shell fills in (avoids import cycles between views and dialogs)
  showDay: (day: string) => void = () => {};
  openBreakEditor: (b?: Break) => void = () => {};
  openBreakNow: () => void = () => {};
  openSettings: (tab?: string) => void = () => {};
  openSetup: () => void = () => {};

  async init() {
    this.cfg = await api.get_config();
    this.applyTheme();
  }

  /** Called whenever stats/timeline data may have changed. */
  onData(fn: Listener) { this.listeners.push(fn); }
  /** Called when settings change. */
  onConfig(fn: Listener): () => void {
    this.cfgListeners.push(fn);
    return () => (this.cfgListeners = this.cfgListeners.filter((f) => f !== fn));
  }

  dataChanged() { this.listeners.forEach((f) => f()); }

  setConfig(cfg: Config) {
    this.cfg = cfg;
    this.applyTheme();
    this.cfgListeners.forEach((f) => f());
    this.dataChanged();
  }

  async update(patch: Parameters<typeof api.update_config>[0]) {
    try {
      this.setConfig(await api.update_config(patch));
    } catch (e) {
      errorToast(e);
    }
  }

  applyTheme() {
    const t = this.cfg.theme;
    if (t === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
  }

  isDark() {
    const t = this.cfg.theme;
    return t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  }

  toggleTheme() {
    return this.update({ theme: this.isDark() ? "light" : "dark" });
  }

  async setRunning(on: boolean) {
    try {
      this.status = await api.set_running(on);
      this.cfg.autostart = on;
      toast(on ? "Automatic breaks on" : "Automatic breaks off");
      this.dataChanged();
    } catch (e) {
      errorToast(e);
    }
  }

  async skipToday() {
    const n = await api.skip_today();
    toast(n ? `Skipping ${plural(n, "break")} today` : "No more breaks today");
    this.status = await api.status();
    this.dataChanged();
  }

  async saveBreak(start: string, end: string, replace?: Break): Promise<boolean> {
    try {
      this.setConfig(await api.add_break(start, end, replace));
      toast(`Saved: ${fmtRangeHM(start, end)}`);
      return true;
    } catch (e) {
      errorToast(e);
      return false;
    }
  }

  async removeBreak(b: Break) {
    try {
      this.setConfig(await api.remove_break(b.start, b.end));
      toast(`Break removed: ${fmtRangeHM(b.start, b.end)}`);
    } catch (e) {
      errorToast(e);
    }
  }

  /** Actions that need TeamLogger control — the Rust core explains they're not ready. */
  async notYet(action: string) {
    try {
      await api.not_yet(action);
    } catch (e) {
      errorToast(e);
    }
  }

  async connect() {
    const ok = await confirmDialog(
      "Connect TeamLogger?",
      "TeamLogger restarts once so this app can press its buttons. Its timer pauses for a few seconds.",
      "Connect",
    );
    if (ok) await this.notYet("Connect TeamLogger");
  }
}

export const app = new AppState();

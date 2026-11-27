// OS services used by setup and settings: notifications, file picker, start at
// login, and a test sound. Tauri plugins in the desktop app; browser stand-ins
// (or nothing) in the browser preview.
import { inTauri } from "./api.ts";

export type Permission = "granted" | "denied" | "default";

export async function notificationPermission(): Promise<Permission> {
  if (inTauri) {
    const n = await import("@tauri-apps/plugin-notification");
    return (await n.isPermissionGranted()) ? "granted" : "default";
  }
  return "Notification" in window ? Notification.permission : "denied";
}

export async function requestNotifications(): Promise<Permission> {
  if (inTauri) {
    const n = await import("@tauri-apps/plugin-notification");
    return (await n.requestPermission()) as Permission;
  }
  return "Notification" in window ? Notification.requestPermission() : "denied";
}

export async function sendNotification(title: string, body: string) {
  if (inTauri) {
    const n = await import("@tauri-apps/plugin-notification");
    n.sendNotification({ title, body });
  } else if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body });
  }
}

/** Let the user point at TeamLogger. Returns the chosen path, or null. */
export async function pickTeamLogger(os: string): Promise<string | null> {
  if (!inTauri) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const picked = await open({
    title: "Choose TeamLogger",
    multiple: false,
    directory: false,
    defaultPath: os === "macos" ? "/Applications" : undefined,
    filters: os === "macos" ? [{ name: "Applications", extensions: ["app"] }]
      : os === "windows" ? [{ name: "Programs", extensions: ["exe"] }] : undefined,
  });
  return typeof picked === "string" ? picked : null;
}

export async function loginEnabled(): Promise<boolean> {
  if (!inTauri) return false;
  const a = await import("@tauri-apps/plugin-autostart");
  return a.isEnabled();
}

export async function setLogin(on: boolean): Promise<boolean> {
  if (!inTauri) return false;
  const a = await import("@tauri-apps/plugin-autostart");
  await (on ? a.enable() : a.disable());
  return a.isEnabled();
}

/** The alarm chime, synthesised (no sound files to ship): three soft bell tones. */
export function playChime() {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return;
  const ctx = new Ctx();
  [659.25, 830.61, 987.77].forEach((freq, i) => {
    const t = ctx.currentTime + i * 0.22;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.25, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 1.2);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 1.25);
  });
  setTimeout(() => ctx.close(), 2200);
}

// Writes ~10 weeks of demo data to ./dev-data for `npm run tauri:demo`.
// Same file formats as the real app (config.json, activity-YYYY-MM-DD.json,
// teamlogger-totals.json). Never touches your real settings or timeline.
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { demoDay, demoTotal, DEMO_BREAKS, DEMO_DAYS } from "../src/demo.ts";

const dir = join(import.meta.dirname, "..", "dev-data");
mkdirSync(dir, { recursive: true });

const now = new Date();
const totals: Record<string, number> = {};
const key = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

for (let i = 0; i < 70; i++) {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
  const segs = demoDay(day, now);
  if (!segs.length) continue;
  writeFileSync(join(dir, `activity-${key(day)}.json`), JSON.stringify(segs));
  const t = demoTotal(segs);
  if (i > 0 && t) totals[key(day)] = t;
}
writeFileSync(join(dir, "teamlogger-totals.json"), JSON.stringify(totals));

const cfg = join(dir, "config.json");
if (!existsSync(cfg)) {
  writeFileSync(
    cfg,
    JSON.stringify(
      {
        breaks: DEMO_BREAKS, days: DEMO_DAYS, port: 9333, dry_run: true, autostart: true,
        login: false, theme: "system",
        phone: { enabled: false, server: "https://ntfy.sh", topic: "tlb-demo0000000000", warn_min: 5,
                 alarm: true, alarm_repeats: 3, laptop_sound: true },
      },
      null, 2,
    ),
  );
}
console.log(`Demo data written to ${dir}`);

//! Menu-bar / top-bar / tray presence (port of teamlogger_break_tray.py).
//!
//! A small progress ring (work: towards the next break, break: through the
//! break) and the live countdown next to it:
//!   macOS    menu-bar item: template ring + countdown title (adapts to light/dark menu bar)
//!   Linux    top-bar indicator: coloured ring + countdown label (AppIndicator), like the GTK app
//!   Windows  tray icon: coloured ring; the countdown is in the tooltip (tray icons can't show text)
//! The menu: status line, Open, Automatic breaks, Skip next break, Skip today,
//! Undo skip, Quit.

use chrono::Local;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::image::Image;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager};

use crate::AppState;

/// Ring frames per lap (same as the Linux indicator).
const STEPS: f64 = 24.0;
const SIZE: u32 = 44; // px; shown at 22 pt on macOS (retina)

pub static QUITTING: AtomicBool = AtomicBool::new(false);

/// Draw the ring: `frac` 0…1 filled, `mode` "work" | "break" | "off".
/// `template` = macOS menu-bar style (black + alpha only; the system tints it).
pub fn ring(frac: f64, mode: &str, template: bool, blink: bool) -> Vec<u8> {
    let (w, hgt) = (SIZE as f64, SIZE as f64);
    let (cx, cy) = (w / 2.0, hgt / 2.0);
    let r = w * 0.36;
    let stroke = w * 0.11;
    let col: [f64; 3] = if template {
        [0.0, 0.0, 0.0]
    } else {
        match mode {
            "work" => [140.0, 180.0, 255.0],
            "break" => [255.0, 176.0, 80.0],
            _ => [160.0, 160.0, 168.0],
        }
    };
    let track: ([f64; 3], f64) = if template { ([0.0; 3], 0.30) } else { ([150.0, 150.0, 158.0], 0.45) };
    let frac = if mode == "off" { 0.0 } else { frac.clamp(0.0, 1.0) };
    let mut px = vec![0u8; (SIZE * SIZE * 4) as usize];
    let cover = |v: f64| v.clamp(0.0, 1.0);
    for y in 0..SIZE {
        for x in 0..SIZE {
            let (fx, fy) = (x as f64 + 0.5 - cx, y as f64 + 0.5 - cy);
            let d = (fx * fx + fy * fy).sqrt();
            // ring band, anti-aliased by distance
            let band = cover(stroke / 2.0 + 0.5 - (d - r).abs());
            // clockwise angle from 12 o'clock, 0…1
            let a = (fx.atan2(-fy) / std::f64::consts::TAU).rem_euclid(1.0);
            let on_arc = frac >= 0.999 || (frac > 0.0 && a <= frac);
            let mut alpha_fg = if on_arc { band } else { 0.0 };
            let alpha_track = if on_arc { 0.0 } else { band * track.1 };
            // centre glyph: dot while working, pause bars on a break
            if !blink {
                let glyph = match mode {
                    "work" => cover(w * 0.09 + 0.5 - d),
                    "break" => {
                        let bar = |x0: f64| {
                            cover(fx - x0 + 0.5).min(cover(x0 + w * 0.08 - fx + 0.5)) * cover(w * 0.14 - fy.abs() + 0.5)
                        };
                        bar(-w * 0.11).max(bar(w * 0.03))
                    }
                    _ => 0.0,
                };
                alpha_fg = alpha_fg.max(glyph);
            }
            let (rgb, a_total) = if alpha_fg > 0.0 { (col, alpha_fg + alpha_track * (1.0 - alpha_fg)) } else { (track.0, alpha_track) };
            let i = ((y * SIZE + x) * 4) as usize;
            px[i] = rgb[0] as u8;
            px[i + 1] = rgb[1] as u8;
            px[i + 2] = rgb[2] as u8;
            px[i + 3] = (a_total * 255.0).round() as u8;
        }
    }
    px
}

fn fmt_clock(secs: f64) -> String {
    let s = secs.max(0.0).round() as i64;
    let (h, m, s) = (s / 3600, (s % 3600) / 60, s % 60);
    if h > 0 { format!("{h}:{m:02}:{s:02}") } else { format!("{m:02}:{s:02}") }
}

pub fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

pub fn setup(app: &AppHandle) -> tauri::Result<()> {
    let state = app.state::<AppState>();
    let running = state.sched.lock().unwrap().running;
    let status_item = MenuItem::with_id(app, "status", "Starting…", false, None::<&str>)?;
    let open = MenuItem::with_id(app, "open", "Open ZenMetrics", true, None::<&str>)?;
    let auto = CheckMenuItem::with_id(app, "auto", "Automatic breaks", true, running, None::<&str>)?;
    let skip_next = MenuItem::with_id(app, "skip_next", "Skip next break", true, None::<&str>)?;
    let skip = MenuItem::with_id(app, "skip", "Skip today's remaining breaks", true, None::<&str>)?;
    let unskip = MenuItem::with_id(app, "unskip", "Undo skipped breaks", false, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit ZenMetrics", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[&status_item, &PredefinedMenuItem::separator(app)?, &open, &auto, &PredefinedMenuItem::separator(app)?,
          &skip_next, &skip, &unskip, &PredefinedMenuItem::separator(app)?, &quit],
    )?;
    let template = cfg!(target_os = "macos");
    let tray = TrayIconBuilder::with_id("main")
        .icon(Image::new_owned(ring(0.0, "off", template, false), SIZE, SIZE))
        .icon_as_template(template)
        .tooltip("ZenMetrics")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, ev| {
            let state = app.state::<AppState>();
            match ev.id().as_ref() {
                "open" => show_main(app),
                "auto" => {
                    let on = !state.sched.lock().unwrap().running;
                    if let Err(e) = crate::commands::apply_running(&state, on) {
                        state.add_log(format!("Couldn't switch automatic breaks: {e}"));
                    }
                }
                "skip_next" => {
                    crate::commands::skip_next_break(&state);
                }
                "unskip" => {
                    crate::commands::undo_skips(&state);
                }
                "skip" => {
                    let cfg = state.cfg.lock().unwrap().clone();
                    state.sched.lock().unwrap().skip_today(&cfg, Local::now().naive_local());
                    state.add_log("Remaining breaks today will be skipped.");
                }
                "quit" => {
                    QUITTING.store(true, Ordering::SeqCst);
                    app.exit(0);
                }
                _ => {}
            }
        })
        .build(app)?;

    state.add_log("Tray countdown ready");
    // Update once per wall-clock second, from the core's own schedule status.
    let app = app.clone();
    std::thread::spawn(move || {
        let mut last_icon = String::new();
        let mut last_title = String::new();
        let mut last_text = String::new();
        let mut last_running = None;
        let mut last_next = String::new();
        loop {
            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
            std::thread::sleep(Duration::from_millis(1000 - now.subsec_millis() as u64 + 5));
            let state = app.state::<AppState>();
            let st = {
                let cfg = state.cfg.lock().unwrap();
                state.sched.lock().unwrap().status(&cfg, &state.log, Local::now().naive_local())
            };
            let now_s = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
            let left = st.target.map(|t| t - now_s);
            let title = left.map(fmt_clock).unwrap_or_default();
            let blink = left.is_some_and(|l| l < 60.0) && (now_s as i64) % 2 == 1;
            let step = (st.frac * STEPS).round() / STEPS;
            let key = format!("{}{step}{blink}", st.mode);
            if key != last_icon {
                last_icon = key;
                let _ = tray.set_icon(Some(Image::new_owned(ring(step, st.mode, template, blink), SIZE, SIZE)));
                let _ = tray.set_icon_as_template(template);
            }
            if title != last_title {
                // macOS menu bar + Linux top bar show it next to the ring; Windows ignores it
                let _ = tray.set_title(if title.is_empty() { None } else { Some(title.as_str()) });
                last_title = title.clone();
            }
            let text = if title.is_empty() { st.text.clone() } else { format!("{} · {title}", st.text) };
            if text != last_text {
                let _ = tray.set_tooltip(Some(&text));
                let _ = status_item.set_text(&st.text);
                last_text = text;
            }
            if last_running != Some(st.running) {
                let _ = auto.set_checked(st.running);
                last_running = Some(st.running);
            }
            let free = st.running && st.active.is_none();
            let next_label = match st.next {
                Some((s, _)) if st.can_skip => format!("Skip the {} break", crate::store::fmt12(
                    chrono::DateTime::from_timestamp(s as i64, 0).map(|d| d.with_timezone(&Local).time()).unwrap_or_default())),
                _ => "Skip next break".into(),
            };
            if next_label != last_next {
                let _ = skip_next.set_text(&next_label);
                last_next = next_label;
            }
            let _ = skip_next.set_enabled(free && st.can_skip);
            let _ = skip.set_enabled(free && st.upcoming_today > 1);
            let _ = unskip.set_enabled(free && st.skipped_today > 0);
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn alpha(px: &[u8], x: u32, y: u32) -> u8 {
        px[((y * SIZE + x) * 4 + 3) as usize]
    }

    #[test]
    fn ring_fills_clockwise_from_the_top() {
        let quarter = ring(0.25, "work", true, false);
        let (c, r) = (SIZE / 2, (SIZE as f64 * 0.36) as u32);
        assert!(alpha(&quarter, c + 3, c - r) > 200, "just right of 12 o'clock is filled");
        assert!(alpha(&quarter, c + r, c + 3) < 120, "just below 3 o'clock is track only");
        assert!(alpha(&quarter, c - r, c) < 120, "9 o'clock is track only");
        assert!(alpha(&quarter, c, c) > 200, "work dot in the centre");
        let off = ring(0.7, "off", true, false);
        assert!(alpha(&off, c, c) == 0 && alpha(&off, c + r, c) < 120, "off: empty ring, no glyph");
    }

    #[test]
    fn clock_format_matches_the_linux_tray() {
        assert_eq!(fmt_clock(3.0 * 3600.0 +9.0 * 60.0 + 24.0), "3:09:24");
        assert_eq!(fmt_clock(9.0 * 60.0 + 5.0), "09:05");
        assert_eq!(fmt_clock(-4.0), "00:00");
    }
}

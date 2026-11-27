//! TeamLogger Break — cross-platform core (Tauri v2).
//!
//! Milestones 1–2 and the first-run setup (6) of docs/CROSS_PLATFORM_PLAN.md:
//! the app shell, settings store, activity timeline, statistics and setup. TeamLogger control (DevTools),
//! the scheduler loop, tray, notifications and phone come next.

mod activity;
mod commands;
mod schedule;
mod store;
mod teamlogger;
mod tray;

use std::sync::Mutex;
use tauri::Manager;

pub struct AppState {
    pub paths: store::Paths,
    pub cfg: Mutex<store::Config>,
    pub log: activity::ActivityLog,
    pub sched: Mutex<schedule::Scheduler>,
    pub log_lines: Mutex<Vec<String>>,
    /// Set once the web UI has made its first call.
    pub ui_seen: std::sync::atomic::AtomicBool,
}

impl AppState {
    pub fn new(paths: store::Paths) -> Self {
        let cfg = store::load_config(&paths.config_file);
        let mut sched = schedule::Scheduler::new(false);
        if cfg.autostart {
            sched.set_running(&cfg, true, chrono::Local::now().naive_local());
        }
        let state = AppState {
            log: activity::ActivityLog::new(paths.data_dir.clone()),
            cfg: Mutex::new(cfg),
            sched: Mutex::new(sched),
            log_lines: Mutex::new(Vec::new()),
            ui_seen: Default::default(),
            paths,
        };
        state.add_log(format!("Settings: {}", state.paths.config_file.display()));
        state.add_log(format!("Timeline: {}", state.paths.data_dir.display()));
        state
    }

    pub fn add_log(&self, msg: impl AsRef<str>) {
        let line = format!("{}  {}", chrono::Local::now().format("%H:%M:%S"), msg.as_ref());
        #[cfg(debug_assertions)]
        eprintln!("{line}");
        let mut lines = self.log_lines.lock().unwrap();
        lines.push(line);
        let excess = lines.len().saturating_sub(500);
        lines.drain(..excess);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = AppState::new(store::Paths::resolve());
    tauri::Builder::default()
        // a second launch just shows the running window
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| tray::show_main(app)))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, None))
        .manage(state)
        // the countdown in the menu bar / top bar / tray
        .setup(|app| {
            tray::setup(app.handle())?;
            Ok(())
        })
        // closing the window keeps the app (and the schedule) running, like the Linux app
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" && !tray::QUITTING.load(std::sync::atomic::Ordering::SeqCst) {
                    api.prevent_close();
                    let _ = window.hide();
                    hint_still_running(window.app_handle());
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_config,
            commands::update_config,
            commands::add_break,
            commands::remove_break,
            commands::new_phone_topic,
            commands::status,
            commands::set_running,
            commands::skip_today,
            commands::dashboard,
            commands::period,
            commands::day_detail,
            commands::activity_log,
            commands::not_yet,
            commands::teamlogger_status,
            commands::set_teamlogger_path,
            commands::set_breaks,
            commands::suggested_breaks,
            commands::phone_qr,
        ])
        .build(tauri::generate_context!())
        .expect("error while starting TeamLogger Break")
        .run(|_app, _event| {
            // macOS: clicking the Dock icon brings the hidden window back
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen { .. } = _event {
                tray::show_main(_app);
            }
        });
}

/// The first time the window is closed, say where the app went (once per run).
fn hint_still_running(app: &tauri::AppHandle) {
    use tauri_plugin_notification::NotificationExt;
    static SHOWN: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    if SHOWN.swap(true, std::sync::atomic::Ordering::SeqCst) {
        return;
    }
    let place = if cfg!(target_os = "macos") { "menu bar" } else if cfg!(target_os = "windows") { "system tray" } else { "top bar" };
    let _ = app
        .notification()
        .builder()
        .title("TeamLogger Break is still running")
        .body(format!("Your breaks keep running. Open it again from the {place}."))
        .show();
}

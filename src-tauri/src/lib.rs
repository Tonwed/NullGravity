use std::sync::Mutex;
use log::info;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct SidecarState(Mutex<Option<CommandChild>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! Welcome to NullGravity.", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            info!("NullGravity starting backend sidecar...");

            match app.shell().sidecar("nullgravity-core") {
                Ok(sidecar) => {
                    match sidecar.spawn() {
                        Ok((_rx, child)) => {
                            info!("Backend sidecar started successfully.");
                            // 把 child 存起来，防止被 drop 导致进程被 kill，
                            // 同时在退出时可以拿到它来主动 kill
                            *app.state::<SidecarState>().0.lock().unwrap() = Some(child);
                        }
                        Err(e) => {
                            info!("Failed to spawn backend sidecar: {}", e);
                            eprintln!("Failed to spawn backend sidecar: {}", e);
                        }
                    }
                }
                Err(e) => {
                    info!("Failed to find backend sidecar: {:?}", e);
                    eprintln!("Failed to find backend sidecar: {:?}", e);
                }
            }

            info!("NullGravity v0.1.0 started.");
            Ok(())
        })
        .on_window_event(|window, event| {
            // 主窗口关闭时，kill 掉后端进程，防止残留
            if let tauri::WindowEvent::Destroyed = event {
                let app = window.app_handle();
                let child = app
                    .state::<SidecarState>()
                    .0
                    .lock()
                    .ok()
                    .and_then(|mut g| g.take());
                if let Some(child) = child {
                    let _ = child.kill();
                    info!("Backend sidecar killed on window close.");
                }
            }
        })
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running NullGravity");
}

use std::sync::Mutex;
use log::info;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct SidecarState(Mutex<Option<CommandChild>>);

fn kill_sidecar(app: &tauri::AppHandle) {
    let child = app
        .state::<SidecarState>()
        .0
        .lock()
        .ok()
        .and_then(|mut g| g.take());
    if let Some(child) = child {
        let _ = child.kill();
        info!("Backend sidecar killed.");
    }
}

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
                            *app.state::<SidecarState>().0.lock().unwrap() = Some(child);
                        }
                        Err(e) => {
                            eprintln!("Failed to spawn backend sidecar: {}", e);
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Failed to find backend sidecar: {:?}", e);
                }
            }

            info!("NullGravity v0.1.0 started.");
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                kill_sidecar(window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![greet])
        .build(tauri::generate_context!())
        .expect("error while building NullGravity")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                kill_sidecar(app);
            }
        });
}

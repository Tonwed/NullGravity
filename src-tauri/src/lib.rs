use log::info;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! Welcome to NullGravity.", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            info!("NullGravity starting backend sidecar...");
            
            use tauri_plugin_shell::ShellExt;
            match app.shell().sidecar("backend") {
                Ok(sidecar) => {
                    match sidecar.spawn() {
                        Ok(mut _child) => {
                            info!("Backend sidecar started successfully.");
                        },
                        Err(e) => {
                            info!("Failed to spawn backend sidecar: {}", e);
                            eprintln!("Failed to spawn backend sidecar: {}", e);
                        }
                    }
                },
                Err(e) => {
                    info!("Failed to find backend sidecar: {:?}", e);
                    eprintln!("Failed to find backend sidecar: {:?}", e);
                }
            }

            info!("NullGravity v0.1.0 started.");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running NullGravity");
}

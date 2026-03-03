use std::net::TcpListener;
use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri::utils::config::WindowEffectsConfig;
use tauri::utils::WindowEffect;

struct SidecarPid(Mutex<Option<u32>>);

/// 找一个系统可用的空闲端口
fn find_free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("Failed to bind to find free port")
        .local_addr()
        .unwrap()
        .port()
}

/// 非阻塞 kill，不弹黑窗口
fn kill_by_pid_nowait(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = std::process::Command::new("kill")
            .args(["-9", &pid.to_string()])
            .spawn();
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! Welcome to NullGravity.", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port = find_free_port();
    eprintln!("[NullGravity] Using backend port: {}", port);

    let init_script = format!("window.__BACKEND_PORT__ = {};", port);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarPid(Mutex::new(None)))
        .setup(move |app| {
            // 手动创建窗口，注入端口初始化脚本，恢复 Mica 效果
            tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::App("index.html".into()),
            )
            .title("NullGravity")
            .inner_size(1280.0, 800.0)
            .min_inner_size(900.0, 600.0)
            .center()
            .transparent(true)
            .decorations(true)
            .effects(WindowEffectsConfig {
                effects: vec![WindowEffect::Mica],
                state: None,
                radius: None,
                color: None,
            })
            .initialization_script(&init_script)
            .build()
            .expect("Failed to create main window");

            let handle = app.handle().clone();

            // 通过环境变量把端口传给 sidecar
            match app.shell().sidecar("nullgravity-core") {
                Ok(sidecar) => {
                    match sidecar
                        .env("NULLGRAVITY_PORT", port.to_string())
                        .spawn()
                    {
                        Ok((mut rx, child)) => {
                            let pid = child.pid();
                            *handle.state::<SidecarPid>().0.lock().unwrap() = Some(pid);
                            eprintln!("[NullGravity] Backend sidecar started, PID={}, PORT={}", pid, port);

                            Box::leak(Box::new(child));

                            tauri::async_runtime::spawn(async move {
                                while let Some(event) = rx.recv().await {
                                    match event {
                                        CommandEvent::Stdout(line) => {
                                            eprintln!("[core] {}", String::from_utf8_lossy(&line));
                                        }
                                        CommandEvent::Stderr(line) => {
                                            eprintln!("[core:err] {}", String::from_utf8_lossy(&line));
                                        }
                                        CommandEvent::Terminated(status) => {
                                            eprintln!("[core] terminated: {:?}", status);
                                            break;
                                        }
                                        _ => {}
                                    }
                                }
                            });
                        }
                        Err(e) => {
                            eprintln!("[NullGravity] Failed to spawn sidecar: {}", e);
                        }
                    }
                }
                Err(e) => {
                    eprintln!("[NullGravity] Failed to find sidecar: {:?}", e);
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let app = window.app_handle();
                if let Ok(mut guard) = app.state::<SidecarPid>().0.lock() {
                    if let Some(pid) = guard.take() {
                        eprintln!("[NullGravity] Killing sidecar PID={}", pid);
                        kill_by_pid_nowait(pid);
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![greet])
        .build(tauri::generate_context!())
        .expect("error while building NullGravity")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Ok(mut guard) = app.state::<SidecarPid>().0.lock() {
                    if let Some(pid) = guard.take() {
                        eprintln!("[NullGravity] Exit: Killing sidecar PID={}", pid);
                        kill_by_pid_nowait(pid);
                    }
                }
            }
        });
}

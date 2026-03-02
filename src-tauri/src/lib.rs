use std::sync::{Arc, Mutex};
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

// 只存 PID，用系统级 kill，不依赖 CommandChild::kill()
struct SidecarPid(Mutex<Option<u32>>);

fn kill_by_pid(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string()])
            .output();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = std::process::Command::new("kill")
            .args(["-9", &pid.to_string()])
            .output();
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
        .manage(SidecarPid(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();

            match app.shell().sidecar("nullgravity-core") {
                Ok(sidecar) => {
                    match sidecar.spawn() {
                        Ok((mut rx, child)) => {
                            // 存 PID
                            let pid = child.pid();
                            *handle.state::<SidecarPid>().0.lock().unwrap() = Some(pid);
                            eprintln!("[NullGravity] Backend sidecar started, PID={}", pid);

                            // child 必须保持存活，存入 app state
                            // 用 Box::leak 让它永远存活直到进程退出
                            // （我们通过 PID kill 来结束它，不依赖 drop）
                            Box::leak(Box::new(child));

                            // 持续消费 rx，防止 channel 阻塞导致 sidecar 挂起
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
                        kill_by_pid(pid);
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
                        kill_by_pid(pid);
                    }
                }
            }
        });
}

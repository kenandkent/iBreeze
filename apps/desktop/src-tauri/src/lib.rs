pub mod rpc_client;

use rpc_client::RpcClient;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::Duration;

const SOCKET_PATH: &str = "/tmp/acos.sock";

static SIDECAR_CHILD: OnceLock<Arc<Mutex<Option<Child>>>> = OnceLock::new();

fn get_sidecar_child() -> &'static Arc<Mutex<Option<Child>>> {
    SIDECAR_CHILD.get_or_init(|| Arc::new(Mutex::new(None)))
}

fn find_sidecar_dir() -> Option<PathBuf> {
    let dev_path = PathBuf::from("/Users/ken/workspace/ibreeze/sidecar");
    if dev_path.join("acos/app.py").exists() {
        return Some(dev_path);
    }
    None
}

fn kill_process_tree(pid: u32) {
    eprintln!("[iBreeze] Killing process tree for pid={}", pid);
    let _ = Command::new("pkill")
        .args(["-9", "-P", &pid.to_string()])
        .output();
    unsafe {
        libc::kill(pid as i32, libc::SIGKILL);
    }
}

fn kill_sidecar() {
    eprintln!("[iBreeze] Cleaning up sidecar...");
            if let Ok(mut guard) = get_sidecar_child().lock() {
        if let Some(mut child) = guard.take() {
            let pid = child.id();
            eprintln!("[iBreeze] Sidecar pid={}", pid);
            kill_process_tree(pid);
            let _ = child.wait();
            eprintln!("[iBreeze] Sidecar process killed");
        }
    }
    let _ = std::fs::remove_file(SOCKET_PATH);
    eprintln!("[iBreeze] Sidecar cleanup done");
}

fn start_sidecar() {
    eprintln!("[iBreeze] Starting sidecar...");

    let socket = PathBuf::from(SOCKET_PATH);
    if socket.exists() {
        eprintln!("[iBreeze] Socket exists, checking health...");
        let client = RpcClient::new(SOCKET_PATH);
        if let Ok(rt) = tokio::runtime::Runtime::new() {
            if rt.block_on(client.call("sys.health", serde_json::json!({}))).is_ok() {
                eprintln!("[iBreeze] Sidecar already running");
                return;
            }
        }
        eprintln!("[iBreeze] Dead sidecar, cleaning socket");
        let _ = std::fs::remove_file(SOCKET_PATH);
    }

    let sidecar_dir = match find_sidecar_dir() {
        Some(d) => d,
        None => {
            eprintln!("[iBreeze] Sidecar directory not found");
            return;
        }
    };

    let app_pid = std::process::id();

    // Finder 启动时 PATH 不完整，使用完整路径和显式 PATH
    let uv_path = std::env::var("UV_PATH")
        .unwrap_or_else(|_| "/opt/homebrew/bin/uv".to_string());

    let mut cmd = Command::new(&uv_path);
    cmd.arg("run")
        .arg("python")
        .arg("-m")
        .arg("acos.app")
        .current_dir(&sidecar_dir)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .env("IBREEZE_APP_PID", app_pid.to_string())
        .env("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin");

    match cmd.spawn() {
        Ok(child) => {
            eprintln!("[iBreeze] Sidecar spawned, pid={}, app_pid={}", child.id(), app_pid);

    if let Ok(mut guard) = get_sidecar_child().lock() {
                *guard = Some(child);
            }

            for _ in 0..100 {
                if socket.exists() {
                    thread::sleep(Duration::from_millis(200));
                    eprintln!("[iBreeze] Sidecar ready");
                    return;
                }
                thread::sleep(Duration::from_millis(100));
            }
            eprintln!("[iBreeze] Sidecar socket timeout");
        }
        Err(e) => {
            eprintln!("[iBreeze] Failed to start sidecar: {}", e);
        }
    }
}

#[tauri::command]
async fn sys_health() -> Result<serde_json::Value, String> {
    let client = RpcClient::new(SOCKET_PATH);
    client.call("sys.health", serde_json::json!({})).await
}

#[tauri::command]
async fn sys_rpc_call(method: String, params: String) -> Result<serde_json::Value, String> {
    let client = RpcClient::new(SOCKET_PATH);
    let params_value: serde_json::Value = serde_json::from_str(&params)
        .map_err(|e| format!("Invalid params JSON: {}", e))?;
    client.call(&method, params_value).await
}

pub fn run() {
    eprintln!("[iBreeze] Application starting...");

    start_sidecar();

    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![sys_health, sys_rpc_call])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            kill_sidecar();
        }
    });
}

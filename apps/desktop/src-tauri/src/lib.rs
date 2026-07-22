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
    // 1. 环境变量覆盖（开发/调试用）
    if let Ok(env_dir) = std::env::var("IBREEZE_SIDECAR_DIR") {
        let p = PathBuf::from(&env_dir);
        if p.join("acos/app.py").exists() {
            eprintln!("[iBreeze] Sidecar from env: {}", p.display());
            return Some(p);
        }
    }

    // 2. 相对于可执行文件向上查找（打包后 .app/Contents/MacOS/ → 回溯到项目根）
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            // 从 exe 所在目录向上最多找 6 层
            let mut cursor = exe_dir.to_path_buf();
            for _ in 0..6 {
                let candidate = cursor.join("sidecar/acos/app.py");
                if candidate.exists() {
                    eprintln!("[iBreeze] Sidecar found relative to exe: {}", cursor.join("sidecar").display());
                    return Some(cursor.join("sidecar"));
                }
                if !cursor.pop() {
                    break;
                }
            }
        }
    }

    // 3. 开发环境：从 CARGO_MANIFEST_DIR 向上找（cargo tauri dev 时 CARGO_MANIFEST_DIR = src-tauri/）
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let manifest_dir = PathBuf::from(&manifest);
        // src-tauri/ → apps/desktop/ → 项目根/sidecar
        if let Some(workspace) = manifest_dir.parent().and_then(|d| d.parent()) {
            let candidate = workspace.join("sidecar/acos/app.py");
            if candidate.exists() {
                eprintln!("[iBreeze] Sidecar found via CARGO_MANIFEST_DIR: {}", workspace.join("sidecar").display());
                return Some(workspace.join("sidecar"));
            }
        }
    }

    // 4. 绝对路径 fallback（原始开发路径，CI/本地开发）
    let dev_path = PathBuf::from("/Users/ken/workspace/ibreeze/sidecar");
    if dev_path.join("acos/app.py").exists() {
        eprintln!("[iBreeze] Sidecar found at dev path: {}", dev_path.display());
        return Some(dev_path);
    }

    // 5. HOME 相对路径
    if let Ok(home) = std::env::var("HOME") {
        let home_path = PathBuf::from(&home).join("workspace/ibreeze/sidecar");
        if home_path.join("acos/app.py").exists() {
            eprintln!("[iBreeze] Sidecar found at HOME path: {}", home_path.display());
            return Some(home_path);
        }
    }

    eprintln!("[iBreeze] Sidecar directory not found in any search path");
    None
}

fn find_uv() -> Option<PathBuf> {
    // 1. 环境变量
    if let Ok(uv) = std::env::var("UV_PATH") {
        let p = PathBuf::from(&uv);
        if p.exists() {
            return Some(p);
        }
    }

    // 2. 常见安装路径
    let candidates = [
        "/opt/homebrew/bin/uv",
        "/usr/local/bin/uv",
        "/usr/bin/uv",
    ];
    for c in &candidates {
        if PathBuf::from(c).exists() {
            return Some(PathBuf::from(c));
        }
    }

    // 3. which 查找
    if let Ok(output) = Command::new("which").arg("uv").output() {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path.is_empty() {
                return Some(PathBuf::from(path));
            }
        }
    }

    None
}

fn kill_process_tree(pid: u32) {
    eprintln!("[iBreeze] Killing process tree for pid={}", pid);
    let _ = Command::new("pkill")
        .args(["-9", "-P", &pid.to_string()])
        .output();
    let _ = Command::new("kill")
        .args(["-9", &pid.to_string()])
        .output();
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
            eprintln!("[iBreeze] CANNOT START: Sidecar directory not found");
            eprintln!("[iBreeze] Set IBREEZE_SIDECAR_DIR env var or run from project root");
            return;
        }
    };

    let uv_path = match find_uv() {
        Some(p) => p,
        None => {
            eprintln!("[iBreeze] CANNOT START: uv not found");
            eprintln!("[iBreeze] Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh");
            return;
        }
    };

    let app_pid = std::process::id();

    let mut cmd = Command::new(&uv_path);
    cmd.arg("run")
        .arg("python")
        .arg("-m")
        .arg("acos.app")
        .current_dir(&sidecar_dir)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .env("IBREEZE_APP_PID", app_pid.to_string())
        .env("ACOS_ADMIN_API_BASE", "http://127.0.0.1:50080")
        .env("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin");

    match cmd.spawn() {
        Ok(child) => {
            eprintln!("[iBreeze] Sidecar spawned, pid={}, app_pid={}", child.id(), app_pid);

            if let Ok(mut guard) = get_sidecar_child().lock() {
                *guard = Some(child);
            }

            // 等待 socket 就绪，最多 15 秒
            for i in 0..150 {
                if socket.exists() {
                    // socket 文件存在后，再等 500ms 让 server 完全就绪
                    thread::sleep(Duration::from_millis(500));
                    // 用实际 health check 验证
                    let client = RpcClient::new(SOCKET_PATH);
                    if let Ok(rt) = tokio::runtime::Runtime::new() {
                        if rt.block_on(client.call("sys.health", serde_json::json!({}))).is_ok() {
                            eprintln!("[iBreeze] Sidecar ready ({}ms)", i * 100 + 500);
                            return;
                        }
                    }
                }
                thread::sleep(Duration::from_millis(100));
            }
            eprintln!("[iBreeze] Sidecar socket timeout after 15s");
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

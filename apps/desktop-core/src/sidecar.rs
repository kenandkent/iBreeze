use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::{Duration, Instant};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use rand::RngCore;
use serde_json::Value;
use tokio::io::AsyncWriteExt;
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tokio::time::sleep;
use tracing::{error, info, warn};
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::error::AppError;
use crate::ipc::dispatcher::ReverseMethodTable;
use crate::rpc::protocol::PROTOCOL_VERSION;
use crate::rpc::sidecar::SidecarClient;

pub const HEALTH_INTERVAL: Duration = Duration::from_secs(5);
pub const HEALTH_TIMEOUT: Duration = Duration::from_secs(3);
pub const MAX_LOST_HEARTBEATS: u32 = 3;
pub const RESTART_WINDOW: Duration = Duration::from_secs(60);
pub const MAX_RESTARTS: u32 = 3;
pub const SHUTDOWN_GRACE_PERIOD: Duration = Duration::from_secs(10);
pub const SIGTERM_TIMEOUT: Duration = Duration::from_secs(5);
pub const SOCKET_WAIT_ATTEMPTS: u32 = 100;
pub const SOCKET_WAIT_INTERVAL: Duration = Duration::from_millis(100);

struct RunningSidecar {
    child: Child,
    client: Arc<SidecarClient>,
    socket_path: PathBuf,
}

pub struct SidecarProfile<'a> {
    pub backend_origin: &'a str,
    pub app_user_id: Uuid,
    pub masked_identifier: &'a str,
    pub device_id: Uuid,
    pub mode: &'a str,
}

#[derive(Default)]
pub struct RestartTracker {
    timestamps: Vec<Instant>,
}

impl RestartTracker {
    pub fn new() -> Self {
        Self {
            timestamps: Vec::new(),
        }
    }

    pub fn is_throttled(&mut self) -> bool {
        let now = Instant::now();
        self.timestamps
            .retain(|t| now.duration_since(*t) < RESTART_WINDOW);
        self.timestamps.len() >= MAX_RESTARTS as usize
    }

    pub fn record_restart(&mut self) {
        self.timestamps.push(Instant::now());
    }
}

pub struct SidecarSupervisor {
    running: Mutex<Option<RunningSidecar>>,
    restart_tracker: Mutex<RestartTracker>,
    reverse_table: Arc<ReverseMethodTable>,
}

impl SidecarSupervisor {
    pub fn new(reverse_table: Arc<ReverseMethodTable>) -> Self {
        Self {
            running: Mutex::new(None),
            restart_tracker: Mutex::new(RestartTracker::new()),
            reverse_table,
        }
    }

    pub async fn start(
        &self,
        executable: &Path,
        runtime_root: &Path,
        profile_root: &Path,
        app_version: &str,
        profile: SidecarProfile<'_>,
    ) -> Result<Arc<SidecarClient>, AppError> {
        let mut guard = self.running.lock().await;
        if guard.is_some() {
            warn!("sidecar.process.already_running");
            return Err(AppError::Validation(
                "A Sidecar profile is already open".to_owned(),
            ));
        }

        {
            let mut tracker = self.restart_tracker.lock().await;
            if tracker.is_throttled() {
                error!("sidecar.process.restart_throttled");
                return Err(AppError::Sidecar(
                    "Sidecar entered diagnostics: too many consecutive restarts".to_owned(),
                ));
            }
        }

        info!(
            backend_origin = %profile.backend_origin,
            mode = %profile.mode,
            "sidecar.process.starting",
        );
        let launch_id = Uuid::new_v4();
        let launch_dir = runtime_root.join(launch_id.to_string());
        std::fs::create_dir_all(&launch_dir)
            .map_err(|error| AppError::Storage(error.to_string()))?;
        set_directory_permissions(&launch_dir)?;
        let socket_path = launch_dir.join("sidecar.sock");
        let mut token_bytes = Zeroizing::new(vec![0_u8; 32]);
        rand::thread_rng().fill_bytes(&mut token_bytes);
        let mut child = Command::new(executable)
            .arg("--socket")
            .arg(&socket_path)
            .arg("--profile")
            .arg(profile_root)
            .arg("--app-version")
            .arg(app_version)
            .arg("--protocol-version")
            .arg(PROTOCOL_VERSION.to_string())
            .arg("--backend-origin")
            .arg(profile.backend_origin)
            .arg("--app-user-id")
            .arg(profile.app_user_id.to_string())
            .arg("--masked-identifier")
            .arg(profile.masked_identifier)
            .arg("--device-id")
            .arg(profile.device_id.to_string())
            .arg("--profile-mode")
            .arg(profile.mode)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .map_err(|error| AppError::Sidecar(format!("start Sidecar: {error}")))?;
        let pid = child.id();
        info!(pid = pid, "sidecar.process.spawned");
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| AppError::Sidecar("Sidecar stdin is unavailable".to_owned()))?;
        stdin
            .write_all(BASE64.encode(&*token_bytes).as_bytes())
            .await
            .map_err(|error| AppError::Sidecar(format!("write startup token: {error}")))?;
        stdin
            .write_all(b"\n")
            .await
            .map_err(|error| AppError::Sidecar(format!("finish startup token: {error}")))?;
        stdin
            .shutdown()
            .await
            .map_err(|error| AppError::Sidecar(format!("close startup channel: {error}")))?;

        wait_for_socket(&mut child, &socket_path).await?;
        let client = Arc::new(SidecarClient::new(&socket_path, self.reverse_table.clone()));
        if let Err(error) = client
            .connect_and_handshake(token_bytes, app_version, launch_id)
            .await
        {
            error!(error = %error, "sidecar.process.handshake_failed");
            let _ = child.kill().await;
            let _ = std::fs::remove_dir_all(&launch_dir);
            return Err(error);
        }
        info!("sidecar.process.started");
        self.restart_tracker.lock().await.record_restart();
        *guard = Some(RunningSidecar {
            child,
            client: Arc::clone(&client),
            socket_path,
        });
        Ok(client)
    }

    pub async fn client(&self) -> Result<Arc<SidecarClient>, AppError> {
        self.running
            .lock()
            .await
            .as_ref()
            .map(|running| Arc::clone(&running.client))
            .ok_or_else(|| AppError::Sidecar("No Profile is open".to_owned()))
    }

    pub async fn stop(&self) -> Result<bool, AppError> {
        let mut running = match self.running.lock().await.take() {
            Some(running) => running,
            None => return Ok(false),
        };
        info!("sidecar.process.stopping");
        let _ = running
            .client
            .call::<Value>(
                "system.shutdown",
                serde_json::json!({}),
                Some(Uuid::new_v4()),
            )
            .await;
        if tokio::time::timeout(SHUTDOWN_GRACE_PERIOD, running.child.wait())
            .await
            .is_err()
        {
            warn!("sidecar.process.kill_timeout");
            #[cfg(unix)]
            {
                if let Some(pid) = running.child.id() {
                    let _ = send_signal(
                        nix::unistd::Pid::from_raw(pid as i32),
                        nix::sys::signal::SIGTERM,
                    );
                }
                let _ = tokio::time::timeout(SIGTERM_TIMEOUT, running.child.wait()).await;
            }
            running
                .child
                .kill()
                .await
                .map_err(|error| AppError::Sidecar(format!("kill Sidecar: {error}")))?;
            let _ = running.child.wait().await;
        }
        running.client.disconnect().await;
        if let Some(launch_dir) = running.socket_path.parent() {
            let _ = std::fs::remove_dir_all(launch_dir);
        }
        info!("sidecar.process.stopped");
        Ok(true)
    }

    pub async fn check_health(&self) -> Result<(), AppError> {
        let client = self.client().await?;
        tokio::time::timeout(
            HEALTH_TIMEOUT,
            client.call::<Value>("system.health", serde_json::json!({}), None),
        )
        .await
        .map_err(|_| AppError::Sidecar("Sidecar health check timed out".to_owned()))?
        .map(|_: Value| ())
    }

    pub async fn is_throttled(&self) -> bool {
        self.restart_tracker.lock().await.is_throttled()
    }

    pub async fn record_restart(&self) {
        self.restart_tracker.lock().await.record_restart();
    }

    pub async fn is_running(&self) -> bool {
        self.running.lock().await.is_some()
    }

    pub async fn restart_count(&self) -> usize {
        self.restart_tracker.lock().await.timestamps.len()
    }
}

impl Default for SidecarSupervisor {
    fn default() -> Self {
        Self::new(Arc::new(ReverseMethodTable::new()))
    }
}

async fn wait_for_socket(child: &mut Child, socket_path: &Path) -> Result<(), AppError> {
    for _ in 0..SOCKET_WAIT_ATTEMPTS {
        if socket_path.exists() {
            return Ok(());
        }
        if let Some(status) = child
            .try_wait()
            .map_err(|error| AppError::Sidecar(error.to_string()))?
        {
            return Err(AppError::Sidecar(format!(
                "Sidecar exited before handshake: {status}"
            )));
        }
        sleep(SOCKET_WAIT_INTERVAL).await;
    }
    let _ = child.kill().await;
    Err(AppError::Sidecar(
        "Sidecar did not create its UDS endpoint in time".to_owned(),
    ))
}

#[cfg(unix)]
fn set_directory_permissions(path: &Path) -> Result<(), AppError> {
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
        .map_err(|error| AppError::Storage(error.to_string()))
}

#[cfg(not(unix))]
fn set_directory_permissions(_: &Path) -> Result<(), AppError> {
    Ok(())
}

#[cfg(unix)]
fn send_signal(pid: nix::unistd::Pid, signal: nix::sys::signal::Signal) -> Result<(), AppError> {
    nix::sys::signal::kill(pid, signal)
        .map_err(|error| AppError::Sidecar(format!("signal {signal:?}: {error}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_supervisor() -> SidecarSupervisor {
        SidecarSupervisor::new(Arc::new(ReverseMethodTable::new()))
    }

    #[tokio::test]
    async fn supervisor_starts_closed() {
        let supervisor = test_supervisor();
        assert!(!supervisor.is_running().await);
        assert!(!supervisor.stop().await.expect("stop empty supervisor"));
    }

    #[tokio::test]
    async fn restart_tracker_throttles_after_max() {
        let mut tracker = RestartTracker::new();
        for _ in 0..MAX_RESTARTS {
            assert!(!tracker.is_throttled());
            tracker.record_restart();
        }
        assert!(tracker.is_throttled());
    }

    #[tokio::test]
    async fn start_rejects_when_throttled() {
        let supervisor = test_supervisor();
        for _ in 0..MAX_RESTARTS {
            supervisor.record_restart().await;
        }
        let temp = tempfile::tempdir().expect("temp dir");
        let result = supervisor
            .start(
                Path::new("/nonexistent/sidecar"),
                temp.path(),
                temp.path(),
                "0.1.0",
                SidecarProfile {
                    backend_origin: "https://example.com:443",
                    app_user_id: Uuid::new_v4(),
                    masked_identifier: "u***@example.com",
                    device_id: Uuid::new_v4(),
                    mode: "online",
                },
            )
            .await;
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("diagnostics"));
    }
}

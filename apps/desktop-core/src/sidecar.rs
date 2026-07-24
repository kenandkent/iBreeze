//! Sidecar process supervision. Secrets are delivered once through stdin.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use rand::RngCore;
use tokio::io::AsyncWriteExt;
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tokio::time::{sleep, timeout};
use uuid::Uuid;
use zeroize::Zeroizing;

use crate::error::AppError;
use crate::rpc::protocol::PROTOCOL_VERSION;
use crate::rpc::sidecar::SidecarClient;

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

pub struct SidecarSupervisor {
    running: Mutex<Option<RunningSidecar>>,
}

impl SidecarSupervisor {
    pub fn new() -> Self {
        Self {
            running: Mutex::new(None),
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
            return Err(AppError::Validation(
                "A Sidecar profile is already open".to_owned(),
            ));
        }
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
        let client = Arc::new(SidecarClient::new(&socket_path));
        if let Err(error) = client
            .connect_and_handshake(token_bytes, app_version, launch_id)
            .await
        {
            let _ = child.kill().await;
            let _ = std::fs::remove_dir_all(&launch_dir);
            return Err(error);
        }
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
        let _ = running
            .client
            .call::<serde_json::Value>(
                "system.shutdown",
                serde_json::json!({}),
                Some(Uuid::new_v4()),
            )
            .await;
        if timeout(Duration::from_secs(5), running.child.wait())
            .await
            .is_err()
        {
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
        Ok(true)
    }

    pub async fn is_running(&self) -> bool {
        self.running.lock().await.is_some()
    }
}

impl Default for SidecarSupervisor {
    fn default() -> Self {
        Self::new()
    }
}

async fn wait_for_socket(child: &mut Child, socket_path: &Path) -> Result<(), AppError> {
    for _ in 0..100 {
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
        sleep(Duration::from_millis(100)).await;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn supervisor_starts_closed() {
        let supervisor = SidecarSupervisor::new();
        assert!(!supervisor.is_running().await);
        assert!(!supervisor.stop().await.expect("stop empty supervisor"));
    }
}

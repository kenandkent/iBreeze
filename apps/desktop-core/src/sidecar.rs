/// Sidecar process manager
use std::process::{Command, Child, Stdio};
use std::sync::Mutex;

pub struct SidecarProcess {
    child: Mutex<Option<Child>>,
    port: u16,
}

impl SidecarProcess {
    pub fn new(port: u16) -> Self {
        Self {
            child: Mutex::new(None),
            port,
        }
    }

    pub fn start(&self, sidecar_path: &str) -> Result<(), String> {
        let mut child = Command::new(sidecar_path)
            .arg("--port")
            .arg(self.port.to_string())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to start sidecar: {e}"))?;

        let mut lock = self.child.lock().map_err(|e| e.to_string())?;
        *lock = Some(child);
        Ok(())
    }

    pub fn stop(&self) -> Result<(), String> {
        let mut lock = self.child.lock().map_err(|e| e.to_string())?;
        if let Some(ref mut child) = *lock {
            child.kill().map_err(|e| format!("Failed to stop sidecar: {e}"))?;
        }
        *lock = None;
        Ok(())
    }

    pub fn is_running(&self) -> bool {
        self.child.lock().map(|lock| lock.is_some()).unwrap_or(false)
    }

    pub fn port(&self) -> u16 {
        self.port
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sidecar_process_new() {
        let process = SidecarProcess::new(51890);
        assert_eq!(process.port(), 51890);
        assert!(!process.is_running());
    }

    #[test]
    fn test_sidecar_stop_without_start() {
        let process = SidecarProcess::new(51890);
        assert!(process.stop().is_ok());
    }
}

//! macOS Seatbelt profile generation for Agent processes.
//!
//! The profile is generated from canonical paths and a Rust-owned Egress
//! lease.  The Sidecar never supplies SBPL or an environment map.  A profile
//! is written with mode 0600, consumed by `/usr/bin/sandbox-exec` at spawn
//! time, and removed immediately after the child is created.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use chrono::Utc;
use uuid::Uuid;

use crate::error::AppError;
use crate::process::RunPurpose;

const SANDBOX_EXEC: &str = "/usr/bin/sandbox-exec";

// Agent CLIs are allowed to invoke only this fixed, reviewable helper set in
// addition to the executable declared by the signed catalog.  The paths are
// intentionally literals: a PATH lookup or a symlink-resolved helper would
// let a workspace file become an executable capability.
const FIXED_HELPERS: &[&str] = &[
    "/bin/sh",
    "/bin/bash",
    "/usr/bin/env",
    "/usr/bin/git",
    "/usr/bin/node",
    "/usr/local/bin/node",
    "/usr/bin/python3",
    "/usr/bin/which",
];

pub struct SeatbeltInvocation {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub profile_path: Option<PathBuf>,
}

#[allow(clippy::too_many_arguments)]
pub fn build_invocation(
    executable: &Path,
    argv: &[String],
    workspace: &Path,
    runtime_root: &Path,
    runtime_tmp: &Path,
    agent_home: &Path,
    proxy_port: u16,
    purpose: &RunPurpose,
) -> Result<SeatbeltInvocation, AppError> {
    if proxy_port < 1024 {
        return Err(AppError::Security("EGRESS_PROXY_PORT_INVALID".to_owned()));
    }
    let profile = write_profile(
        executable,
        workspace,
        runtime_root,
        runtime_tmp,
        agent_home,
        proxy_port,
        purpose,
    )?;

    #[cfg(target_os = "macos")]
    {
        if !Path::new(SANDBOX_EXEC).is_file() {
            let _ = fs::remove_file(&profile);
            return Err(AppError::Security("SEATBELT_UNAVAILABLE".to_owned()));
        }
        let mut args = vec![
            "-f".to_owned(),
            profile.to_string_lossy().into_owned(),
            "--".to_owned(),
        ];
        args.extend(argv.iter().cloned());
        Ok(SeatbeltInvocation {
            program: PathBuf::from(SANDBOX_EXEC),
            args,
            profile_path: Some(profile),
        })
    }

    #[cfg(not(target_os = "macos"))]
    {
        let _ = fs::remove_file(profile);
        let _ = (executable, argv);
        Err(AppError::Security("SEATBELT_UNAVAILABLE".to_owned()))
    }
}

fn write_profile(
    executable: &Path,
    workspace: &Path,
    runtime_root: &Path,
    runtime_tmp: &Path,
    agent_home: &Path,
    proxy_port: u16,
    purpose: &RunPurpose,
) -> Result<PathBuf, AppError> {
    let user_home = dirs::home_dir()
        .ok_or_else(|| AppError::Security("SEATBELT_HOME_UNAVAILABLE".to_owned()))?;
    let executable = canonical_path(executable, false)?;
    let workspace = canonical_path(workspace, true)?;
    let runtime_root = canonical_path(runtime_root, true)?;
    let runtime_tmp = canonical_path(runtime_tmp, true)?;
    let agent_home = canonical_path(agent_home, true)?;
    let user_home = canonical_path(&user_home, true)?;

    let mut profile = String::from(
        "(version 1)\n\
(deny default)\n\
(allow process-fork)\n\
(allow process-info*)\n\
(allow sysctl-read)\n\
(allow mach-lookup)\n\
(deny mach-lookup (global-name \"com.apple.securityd\"))\n\
(deny mach-lookup (global-name \"com.apple.secd\"))\n\
(deny mach-lookup (global-name \"com.apple.SecurityServer\"))\n\
(allow file-read*)\n",
    );
    for path in sensitive_paths(&user_home) {
        profile.push_str(&format!("(deny file-read* {})\n", sbpl_subpath(&path)?));
    }
    profile.push_str(&format!(
        "(allow process-exec {})\n",
        sbpl_literal(&executable)?
    ));
    for helper in FIXED_HELPERS {
        profile.push_str(&format!("(allow process-exec (literal \"{}\"))\n", helper));
    }
    profile.push_str(&format!(
        "(allow file-read* {})\n",
        sbpl_subpath(&runtime_tmp)?
    ));
    profile.push_str(&format!(
        "(allow file-write* {})\n",
        sbpl_subpath(&runtime_tmp)?
    ));
    profile.push_str(&format!(
        "(allow file-read* {})\n",
        sbpl_subpath(&runtime_root)?
    ));
    profile.push_str(&format!(
        "(allow file-write* {})\n",
        sbpl_subpath(&runtime_root)?
    ));
    profile.push_str(&format!(
        "(allow file-read* {})\n",
        sbpl_subpath(&agent_home)?
    ));
    profile.push_str(&format!(
        "(allow file-write* {})\n",
        sbpl_subpath(&agent_home)?
    ));
    profile.push_str(&format!(
        "(allow file-read* {})\n",
        sbpl_subpath(&workspace)?
    ));
    if purpose_allows_workspace_write(purpose) {
        profile.push_str(&format!(
            "(allow file-write* {})\n",
            sbpl_subpath(&workspace)?
        ));
    }
    profile.push_str(&format!(
        "(allow network-outbound (remote tcp \"localhost:{}\"))\n(deny network-inbound)\n",
        proxy_port
    ));

    let file_name = format!(
        "seatbelt-{}-{}.sb",
        Utc::now().timestamp_nanos_opt().unwrap_or_default(),
        Uuid::new_v4()
    );
    let path = runtime_tmp.join(file_name);
    let mut options = OpenOptions::new();
    options.create_new(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&path)
        .map_err(|_| AppError::Security("SEATBELT_PROFILE_WRITE_FAILED".to_owned()))?;
    if file.write_all(profile.as_bytes()).is_err() || file.sync_all().is_err() {
        let _ = fs::remove_file(&path);
        return Err(AppError::Security(
            "SEATBELT_PROFILE_WRITE_FAILED".to_owned(),
        ));
    }
    Ok(path)
}

fn canonical_path(path: &Path, directory: bool) -> Result<PathBuf, AppError> {
    let canonical = fs::canonicalize(path)
        .map_err(|_| AppError::Security("SEATBELT_PATH_INVALID".to_owned()))?;
    if directory && !canonical.is_dir() {
        return Err(AppError::Security("SEATBELT_PATH_INVALID".to_owned()));
    }
    if canonical.to_string_lossy().contains('\n') || canonical.to_string_lossy().contains('\r') {
        return Err(AppError::Security("SEATBELT_PATH_INVALID".to_owned()));
    }
    Ok(canonical)
}

fn sbpl_escape(path: &Path) -> Result<String, AppError> {
    let value = path.to_string_lossy();
    if value.contains('\0') || value.contains('\n') || value.contains('\r') {
        return Err(AppError::Security("SEATBELT_PATH_INVALID".to_owned()));
    }
    Ok(value.replace('\\', "\\\\").replace('"', "\\\""))
}

fn sbpl_subpath(path: &Path) -> Result<String, AppError> {
    Ok(format!("(subpath \"{}\")", sbpl_escape(path)?))
}

fn sbpl_literal(path: &Path) -> Result<String, AppError> {
    Ok(format!("(literal \"{}\")", sbpl_escape(path)?))
}

fn sensitive_paths(home: &Path) -> Vec<PathBuf> {
    [
        ".ssh",
        ".gnupg",
        ".aws",
        ".azure",
        ".kube",
        ".docker",
        ".config/gcloud",
        "Library/Keychains",
    ]
    .into_iter()
    .map(|relative| home.join(relative))
    .collect()
}

fn purpose_allows_workspace_write(purpose: &RunPurpose) -> bool {
    matches!(
        purpose,
        RunPurpose::TaskExecution
            | RunPurpose::Verification
            | RunPurpose::Repair
            | RunPurpose::Merge
    )
}

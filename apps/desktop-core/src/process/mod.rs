//! Rust-owned agent process supervision.
//!
//! The Sidecar sends a fixed, auditable execution snapshot over the
//! authenticated reverse-RPC channel.  This module is the only production
//! boundary that starts an Agent CLI: it validates the snapshot, creates the
//! process group, installs the per-run egress lease, captures output and
//! reaps the child before reporting a terminal state.

use std::collections::{BTreeSet, HashMap};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Weak};
use std::time::Duration;

use chrono::{DateTime, Utc};
use semver::Version;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::io::{AsyncRead, AsyncReadExt};
use tokio::process::Command;
use tokio::sync::{Mutex, RwLock};
use uuid::Uuid;

use crate::broker::domain_policy::NormalizedDomain;
use crate::broker::egress::EgressBroker;
use crate::error::AppError;
use crate::rpc::sidecar::SidecarClient;
use crate::security::grant_store::GrantStore;

mod seatbelt;

const MAX_OUTPUT_BYTES: usize = 16 * 1024 * 1024;
const MAX_STDIN_BYTES: usize = 4 * 1024 * 1024;
const MAX_VERSION_PROBE_OUTPUT_BYTES: usize = 64 * 1024;
const VERSION_PROBE_TIMEOUT: Duration = Duration::from_secs(5);
const TERMINATE_GRACE: Duration = Duration::from_secs(5);

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StartProcessRequest {
    pub run_id: Uuid,
    pub workspace_grant_id: Uuid,
    pub execution_snapshot_sha256: String,
    pub agent_release_id: Uuid,
    pub agent_type: AgentType,
    pub executable_realpath: PathBuf,
    pub argv: Vec<String>,
    pub cwd_realpath: PathBuf,
    pub stdin_base64: Option<String>,
    pub locale: String,
    pub purpose: RunPurpose,
    pub workspace_policy_sha256: String,
    pub network_policy_sha256: String,
    pub deadline_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentType {
    CodexCli,
    ClaudeCode,
    Opencode,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RunPurpose {
    TaskExecution,
    Review,
    Repair,
    Verification,
    Merge,
    CompanyPlan,
    Summary,
    InteractiveTurn,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProcessRequest {
    pub process_id: Uuid,
    pub run_id: Uuid,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CancelProcessRequest {
    pub process_id: Uuid,
    pub run_id: Uuid,
    pub reason: String,
}

#[derive(Debug, Clone)]
struct OutputBuffer {
    bytes: Vec<u8>,
    truncated: bool,
    last_sequence: Arc<Mutex<u64>>,
}

impl OutputBuffer {
    fn new(last_sequence: Arc<Mutex<u64>>) -> Self {
        Self {
            bytes: Vec::new(),
            truncated: false,
            last_sequence,
        }
    }

    async fn append(&mut self, chunk: &[u8]) -> Result<u64, AppError> {
        let remaining = MAX_OUTPUT_BYTES.saturating_sub(self.bytes.len());
        if chunk.len() > remaining {
            // Preserve the bounded prefix so the terminal status accurately
            // reports a truncated stream while the caller receives the
            // fail-closed output-limit error.
            self.bytes.extend_from_slice(&chunk[..remaining]);
            self.truncated = true;
            return Err(AppError::Sidecar(
                "RUNTIME_OUTPUT_LIMIT_EXCEEDED".to_owned(),
            ));
        }
        self.bytes.extend_from_slice(chunk);
        let mut sequence = self.last_sequence.lock().await;
        *sequence = sequence.saturating_add(1);
        Ok(*sequence)
    }
}

#[derive(Debug, Clone)]
struct ProcessState {
    exit_code: Option<i32>,
    signal: Option<i32>,
    started_at: DateTime<Utc>,
    completed_at: Option<DateTime<Utc>>,
    cancellation_requested: bool,
    timed_out: bool,
    termination_reason: Option<&'static str>,
}

struct ProcessRecord {
    process_id: Uuid,
    run_id: Uuid,
    pid: u32,
    pgid: u32,
    state: Arc<Mutex<ProcessState>>,
    stdout: Arc<Mutex<OutputBuffer>>,
    stderr: Arc<Mutex<OutputBuffer>>,
    last_sequence: Arc<Mutex<u64>>,
    egress_lease_id: Uuid,
    runtime_root: PathBuf,
}

#[derive(Clone)]
pub struct ProcessSupervisor {
    records: Arc<Mutex<HashMap<Uuid, Arc<ProcessRecord>>>>,
    run_index: Arc<Mutex<HashMap<Uuid, Uuid>>>,
    egress_broker: Arc<EgressBroker>,
    notification_client: Arc<RwLock<Option<Weak<SidecarClient>>>>,
    profile_root: Arc<RwLock<Option<PathBuf>>>,
    network_policies: Arc<RwLock<HashMap<String, BTreeSet<NormalizedDomain>>>>,
    agent_releases: Arc<RwLock<HashMap<Uuid, AgentReleasePolicy>>>,
    grant_store: Arc<GrantStore>,
}

#[derive(Debug, Clone)]
pub struct AgentReleasePolicy {
    pub agent_type: AgentType,
    pub version_ranges: Vec<AgentVersionRangePolicy>,
    pub adapter_contract_version: u32,
}

#[derive(Debug, Clone)]
pub struct AgentVersionRangePolicy {
    pub min_version: Version,
    pub max_version_exclusive: Version,
    pub executable_names: BTreeSet<String>,
    pub supported_platforms: BTreeSet<String>,
    pub probe_argv: Vec<String>,
    pub adapter_contract_version: u32,
}

impl AgentReleasePolicy {
    pub fn fallback(agent_type: AgentType) -> Self {
        let executable = match agent_type {
            AgentType::CodexCli => "codex",
            AgentType::ClaudeCode => "claude",
            AgentType::Opencode => "opencode",
        };
        Self {
            agent_type,
            version_ranges: vec![AgentVersionRangePolicy {
                min_version: Version::new(0, 0, 0),
                max_version_exclusive: Version::new(1_000_000, 0, 0),
                executable_names: BTreeSet::from([executable.to_owned()]),
                supported_platforms: BTreeSet::from([std::env::consts::OS.to_owned()]),
                probe_argv: vec![executable.to_owned(), "--version".to_owned()],
                adapter_contract_version: 1,
            }],
            adapter_contract_version: 1,
        }
    }
}

impl ProcessSupervisor {
    pub fn new(egress_broker: Arc<EgressBroker>) -> Self {
        Self::with_grant_store(egress_broker, Arc::new(GrantStore::new()))
    }

    pub fn with_grant_store(
        egress_broker: Arc<EgressBroker>,
        grant_store: Arc<GrantStore>,
    ) -> Self {
        Self {
            records: Arc::new(Mutex::new(HashMap::new())),
            run_index: Arc::new(Mutex::new(HashMap::new())),
            egress_broker,
            notification_client: Arc::new(RwLock::new(None)),
            profile_root: Arc::new(RwLock::new(None)),
            network_policies: Arc::new(RwLock::new(HashMap::new())),
            agent_releases: Arc::new(RwLock::new(HashMap::new())),
            grant_store,
        }
    }

    pub async fn bind_client(&self, client: Option<Arc<SidecarClient>>) {
        *self.notification_client.write().await = client.map(|value| Arc::downgrade(&value));
    }

    /// Bind the authenticated profile's private runtime root. Agent state
    /// and scratch files must never be placed in the workspace, where they
    /// could become user artifacts or be included in an Agent diff.
    pub async fn bind_profile_root(&self, root: Option<PathBuf>) -> Result<(), AppError> {
        let canonical = match root {
            Some(root) => {
                let path = std::fs::canonicalize(&root)
                    .map_err(|_| AppError::Security("PROFILE_RUNTIME_ROOT_INVALID".to_owned()))?;
                if !path.is_dir() {
                    return Err(AppError::Security(
                        "PROFILE_RUNTIME_ROOT_INVALID".to_owned(),
                    ));
                }
                Some(path)
            }
            None => None,
        };
        *self.profile_root.write().await = canonical;
        Ok(())
    }

    pub async fn bind_network_policy(
        &self,
        policy_sha256: String,
        allowed_domains: BTreeSet<NormalizedDomain>,
    ) {
        self.network_policies
            .write()
            .await
            .insert(policy_sha256, allowed_domains);
    }

    pub async fn clear_network_policies(&self) {
        self.network_policies.write().await.clear();
    }

    pub async fn bind_agent_release(&self, release_id: Uuid, agent_type: AgentType) {
        self.bind_agent_release_policy(release_id, AgentReleasePolicy::fallback(agent_type))
            .await;
    }

    pub async fn bind_agent_release_policy(&self, release_id: Uuid, policy: AgentReleasePolicy) {
        self.agent_releases.write().await.insert(release_id, policy);
    }

    pub async fn clear_agent_releases(&self) {
        self.agent_releases.write().await.clear();
    }

    /// Remove all per-profile process state after the authenticated profile
    /// is closed.  Keeping completed records across a profile switch would
    /// allow a later profile to query stale run IDs and retain output in
    /// memory longer than the profile's lifetime.
    pub async fn reset(&self) {
        self.cancel_all("PROFILE_CLOSED").await;
        self.records.lock().await.clear();
        self.run_index.lock().await.clear();
        *self.profile_root.write().await = None;
        self.clear_network_policies().await;
        self.clear_agent_releases().await;
    }

    /// Fail closed when the authenticated Sidecar stream disappears.  The
    /// Rust supervisor is the owner of process groups and egress leases, so
    /// it cannot rely on Python receiving a final cancellation command.
    pub async fn cancel_all(&self, _reason: &str) -> usize {
        let records: Vec<Arc<ProcessRecord>> =
            self.records.lock().await.values().cloned().collect();
        let mut active = 0usize;
        for record in &records {
            let mut state = record.state.lock().await;
            if state.completed_at.is_none() {
                state.cancellation_requested = true;
                state.termination_reason = Some("cancelled");
                active += 1;
                let _ = send_group_signal(record.pgid, Signal::Int);
            }
        }
        for _ in 0..50 {
            if records.iter().all(|record| {
                record
                    .state
                    .try_lock()
                    .is_ok_and(|state| state.completed_at.is_some())
            }) {
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        for record in &records {
            if record.state.lock().await.completed_at.is_none() {
                let _ = send_group_signal(record.pgid, Signal::Term);
            }
        }
        for _ in 0..50 {
            if records.iter().all(|record| {
                record
                    .state
                    .try_lock()
                    .is_ok_and(|state| state.completed_at.is_some())
            }) {
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        for record in &records {
            if record.state.lock().await.completed_at.is_none() {
                let _ = send_group_signal(record.pgid, Signal::Kill);
            }
        }
        let run_ids = records
            .iter()
            .map(|record| record.run_id)
            .collect::<Vec<_>>();
        let _ = self.egress_broker.cancel_session(&run_ids).await;
        active
    }

    async fn emit(&self, method: &str, params: Value) -> Result<(), AppError> {
        let client = self
            .notification_client
            .read()
            .await
            .as_ref()
            .and_then(Weak::upgrade);
        let Some(client) = client else { return Ok(()) };
        tokio::time::timeout(Duration::from_secs(5), client.notify(method, params))
            .await
            .map_err(|_| AppError::Sidecar("IPC_BACKPRESSURE".to_owned()))??;
        Ok(())
    }

    pub async fn start(&self, request: StartProcessRequest) -> Result<Value, AppError> {
        let workspace = validate_request(&request)?;
        let granted_workspace = self
            .grant_store
            .resolve_workspace_grant(request.workspace_grant_id)
            .await
            .map_err(|_| AppError::Security("WORKSPACE_GRANT_REQUIRED".to_owned()))?;
        if workspace != granted_workspace {
            return Err(AppError::Security("WORKSPACE_GRANT_MISMATCH".to_owned()));
        }
        let stdin_bytes = decode_stdin(request.stdin_base64.as_deref())?;
        let profile_root = self
            .profile_root
            .read()
            .await
            .clone()
            .ok_or_else(|| AppError::Auth("PROFILE_NOT_OPEN".to_owned()))?;
        let run_root = profile_root
            .join("runtime-input")
            .join(request.run_id.to_string());
        let runtime_tmp = run_root.join("tmp");
        let agent_home = profile_root.join("agent-state");
        let user_home = dirs::home_dir()
            .and_then(|path| std::fs::canonicalize(path).ok())
            .ok_or_else(|| AppError::Security("SEATBELT_HOME_UNAVAILABLE".to_owned()))?;
        if self.run_index.lock().await.contains_key(&request.run_id) {
            return Err(AppError::Validation("PROCESS_ALREADY_EXISTS".to_owned()));
        }

        let allowed_domains = self
            .network_policies
            .read()
            .await
            .get(&request.network_policy_sha256)
            .cloned()
            .ok_or_else(|| {
                AppError::Security("EXECUTION_NETWORK_POLICY_NOT_REGISTERED".to_owned())
            })?;
        let registered_agent = self
            .agent_releases
            .read()
            .await
            .get(&request.agent_release_id)
            .cloned()
            .ok_or_else(|| AppError::Security("AGENT_RELEASE_NOT_REGISTERED".to_owned()))?;
        if registered_agent.agent_type != request.agent_type {
            return Err(AppError::Security("AGENT_RELEASE_TYPE_MISMATCH".to_owned()));
        }
        if registered_agent.adapter_contract_version != 1 {
            return Err(AppError::Security(
                "AGENT_ADAPTER_CONTRACT_UNSUPPORTED".to_owned(),
            ));
        }
        if !registered_agent
            .version_ranges
            .iter()
            .any(|range| platform_matches(&range.supported_platforms))
        {
            return Err(AppError::Security("AGENT_PLATFORM_UNSUPPORTED".to_owned()));
        }
        let executable_name = request
            .executable_realpath
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        let version_policy = registered_agent
            .version_ranges
            .iter()
            .find(|range| {
                platform_matches(&range.supported_platforms)
                    && range.executable_names.contains(&executable_name)
            })
            .cloned()
            .ok_or_else(|| AppError::Security("AGENT_EXECUTABLE_NOT_ALLOWED".to_owned()))?;
        if version_policy.probe_argv.is_empty()
            || version_policy.adapter_contract_version == 0
            || version_policy.min_version >= version_policy.max_version_exclusive
        {
            return Err(AppError::Security(
                "AGENT_RELEASE_POLICY_INVALID".to_owned(),
            ));
        }
        validate_agent_argv(&request.argv)?;

        // Create private per-run state only after all catalog and request
        // validation has succeeded.  Early validation failures must not leave
        // attacker-controlled or stale runtime directories behind.
        if let Err(error) = prepare_runtime_dirs(&run_root, &runtime_tmp, &agent_home) {
            cleanup_run_root(&run_root);
            return Err(error);
        }
        // A lease exists for every CLI process, including an explicit empty
        // allowlist.  The proxy variables are therefore always present and
        // an accidental direct network connection is impossible.
        let lease = match self
            .egress_broker
            .create_lease(request.run_id, allowed_domains)
            .await
        {
            Ok(lease) => lease,
            Err(error) => {
                cleanup_run_root(&run_root);
                return Err(error);
            }
        };

        if let Err(error) = verify_agent_version(
            &version_policy,
            &request.executable_realpath,
            &workspace,
            &run_root,
            &runtime_tmp,
            &agent_home,
            &user_home,
            lease.port,
            &request.locale,
        )
        .await
        {
            let _ = self.egress_broker.revoke_lease_by_id(lease.lease_id).await;
            cleanup_run_root(&run_root);
            return Err(error);
        }

        let invocation = match seatbelt::build_invocation(
            &request.executable_realpath,
            &request.argv,
            &workspace,
            &run_root,
            &runtime_tmp,
            &agent_home,
            lease.port,
            &request.purpose,
        ) {
            Ok(invocation) => invocation,
            Err(error) => {
                let _ = self.egress_broker.revoke_lease_by_id(lease.lease_id).await;
                cleanup_run_root(&run_root);
                return Err(error);
            }
        };
        let mut command = build_command(
            &invocation.program,
            &invocation.args,
            &workspace,
            &runtime_tmp,
            &agent_home,
            &user_home,
            &request.locale,
            lease.proxy_url().as_str(),
        );
        configure_process_group(&mut command);
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                if let Some(profile) = invocation.profile_path {
                    let _ = std::fs::remove_file(profile);
                }
                let _ = self.egress_broker.revoke_lease_by_id(lease.lease_id).await;
                cleanup_run_root(&run_root);
                return Err(AppError::Sidecar(format!("PROCESS_START_FAILED: {error}")));
            }
        };
        if let Some(profile) = invocation.profile_path {
            let _ = std::fs::remove_file(profile);
        }
        let pid = match child.id() {
            Some(pid) => pid,
            None => {
                let _ = child.start_kill();
                let _ = child.wait().await;
                let _ = self.egress_broker.revoke_lease_by_id(lease.lease_id).await;
                cleanup_run_root(&run_root);
                return Err(AppError::Sidecar("PROCESS_PID_UNAVAILABLE".to_owned()));
            }
        };
        let pgid = pid;
        if let Some(bytes) = stdin_bytes.as_deref() {
            if let Some(stdin) = child.stdin.as_mut() {
                use tokio::io::AsyncWriteExt;
                let remaining = request
                    .deadline_at
                    .signed_duration_since(Utc::now())
                    .to_std()
                    .unwrap_or_default();
                let write_result = tokio::time::timeout(remaining, stdin.write_all(bytes)).await;
                if let Err(error) = match write_result {
                    Ok(result) => result,
                    Err(_) => Err(std::io::Error::new(
                        std::io::ErrorKind::TimedOut,
                        "PROCESS_STDIN_DEADLINE_EXCEEDED",
                    )),
                } {
                    let _ = child.kill().await;
                    let _ = child.wait().await;
                    let _ = self.egress_broker.revoke_lease_by_id(lease.lease_id).await;
                    cleanup_run_root(&run_root);
                    return Err(AppError::Sidecar(error.to_string()));
                }
            }
        }
        drop(child.stdin.take());

        let process_id = Uuid::new_v4();
        let stdout_stream = child.stdout.take();
        let stderr_stream = child.stderr.take();
        let last_sequence = Arc::new(Mutex::new(0_u64));
        let stdout = Arc::new(Mutex::new(OutputBuffer::new(last_sequence.clone())));
        let stderr = Arc::new(Mutex::new(OutputBuffer::new(last_sequence.clone())));
        let output_emit_lock = Arc::new(Mutex::new(()));
        let started_at = Utc::now();
        let state = Arc::new(Mutex::new(ProcessState {
            exit_code: None,
            signal: None,
            started_at,
            completed_at: None,
            cancellation_requested: false,
            timed_out: false,
            termination_reason: None,
        }));
        let child_ref = Arc::new(Mutex::new(Some(child)));
        let record = Arc::new(ProcessRecord {
            process_id,
            run_id: request.run_id,
            pid,
            pgid,
            state: state.clone(),
            stdout: stdout.clone(),
            stderr: stderr.clone(),
            last_sequence: last_sequence.clone(),
            egress_lease_id: lease.lease_id,
            runtime_root: run_root.clone(),
        });

        {
            let mut runs = self.run_index.lock().await;
            if runs.contains_key(&request.run_id) {
                drop(runs);
                let _ = send_group_signal(pgid, Signal::Kill);
                if let Some(mut child) = child_ref.lock().await.take() {
                    let _ = child.kill().await;
                    let _ = child.wait().await;
                }
                let _ = self.egress_broker.revoke_lease_by_id(lease.lease_id).await;
                return Err(AppError::Validation("PROCESS_ALREADY_EXISTS".to_owned()));
            }
            self.records.lock().await.insert(process_id, record.clone());
            runs.insert(request.run_id, process_id);
        }

        let output_context = OutputContext {
            supervisor: self.clone(),
            process_id,
            run_id: request.run_id,
            pgid,
            output_emit_lock,
        };
        let stdout_task = tokio::spawn(read_output(
            stdout_stream,
            stdout.clone(),
            output_context.clone(),
            "stdout",
        ));
        let stderr_task = tokio::spawn(read_output(
            stderr_stream,
            stderr.clone(),
            output_context,
            "stderr",
        ));
        let _ = self
            .emit(
                "runtime.process.registered",
                json!({
                    "process_id": process_id,
                    "run_id": request.run_id,
                    "pid": pid,
                    "pgid": pgid,
                    "start_time": started_at.to_rfc3339(),
                    "egress_lease_id": lease.lease_id,
                    "state": "running",
                }),
            )
            .await;
        let state_for_wait = state.clone();
        let child_for_wait = child_ref.clone();
        let supervisor = self.clone();
        tokio::spawn(async move {
            let mut owned_child = child_for_wait.lock().await.take();
            let result = match owned_child.as_mut() {
                Some(child) => child.wait().await.ok(),
                None => None,
            };
            let _ = stdout_task.await;
            let _ = stderr_task.await;
            let mut state = state_for_wait.lock().await;
            state.completed_at = Some(Utc::now());
            if let Some(status) = result {
                state.exit_code = status.code();
                #[cfg(unix)]
                {
                    use std::os::unix::process::ExitStatusExt;
                    state.signal = status.signal();
                }
            }
            let ended_at = state.completed_at;
            let exit_code = state.exit_code;
            let signal = state.signal;
            let timed_out = state.timed_out;
            let termination_reason = state.termination_reason;
            drop(state);
            let stdout = record.stdout.lock().await.clone();
            let stderr = record.stderr.lock().await.clone();
            let last_sequence = *record.last_sequence.lock().await;
            let sha256 = |value: &[u8]| {
                use sha2::{Digest, Sha256};
                Sha256::digest(value)
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>()
            };
            let _ = supervisor
                .emit(
                    "runtime.process.exited",
                    json!({
                        "process_id": record.process_id,
                        "run_id": record.run_id,
                        "exit_code": exit_code,
                        "signal": signal,
                        "status": if timed_out { "timed_out" } else if termination_reason == Some("cancelled") { "cancelled" } else { "exited" },
                        "timed_out": timed_out,
                        "last_sequence": last_sequence,
                        "stdout_sha256": sha256(&stdout.bytes),
                        "stderr_sha256": sha256(&stderr.bytes),
                        "ended_at": ended_at.map(|value| value.to_rfc3339()),
                    }),
                )
                .await;
            let _ = supervisor
                .egress_broker
                .revoke_lease_by_id(record.egress_lease_id)
                .await;
            supervisor.run_index.lock().await.remove(&record.run_id);
            let _ = std::fs::remove_dir_all(&record.runtime_root);
        });

        let timeout_state = state.clone();
        let timeout_pgid = pgid;
        let deadline = request.deadline_at;
        tokio::spawn(async move {
            let wait = deadline.signed_duration_since(Utc::now());
            let duration = wait.to_std().unwrap_or_default();
            tokio::time::sleep(duration).await;
            let should_cancel = {
                let mut state = timeout_state.lock().await;
                if state.completed_at.is_none() {
                    state.cancellation_requested = true;
                    state.timed_out = true;
                    state.termination_reason = Some("timed_out");
                    true
                } else {
                    false
                }
            };
            if should_cancel {
                let _ = send_group_signal(timeout_pgid, Signal::Int);
                tokio::time::sleep(TERMINATE_GRACE).await;
                if timeout_state.lock().await.completed_at.is_none() {
                    let _ = send_group_signal(timeout_pgid, Signal::Term);
                    tokio::time::sleep(TERMINATE_GRACE).await;
                }
                if timeout_state.lock().await.completed_at.is_none() {
                    let _ = send_group_signal(timeout_pgid, Signal::Kill);
                }
            }
        });

        Ok(json!({
            "process_id": process_id,
            "run_id": request.run_id,
            "pid": pid,
            "pgid": pgid,
            "start_time": started_at.to_rfc3339(),
            "egress_lease_id": lease.lease_id,
            "state": "running",
        }))
    }

    pub async fn cancel(&self, request: CancelProcessRequest) -> Result<Value, AppError> {
        if request.reason.trim().is_empty() || request.reason.chars().count() > 500 {
            return Err(AppError::Validation(
                "PROCESS_CANCEL_REASON_INVALID".to_owned(),
            ));
        }
        let record = self.record(request.process_id, request.run_id).await?;
        {
            let mut state = record.state.lock().await;
            if state.completed_at.is_none() {
                state.cancellation_requested = true;
                state.termination_reason = Some("cancelled");
            }
        }
        let _ = send_group_signal(record.pgid, Signal::Int);
        for _ in 0..50 {
            if record.state.lock().await.completed_at.is_some() {
                return self.status(request.process_id, request.run_id).await;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        let _ = send_group_signal(record.pgid, Signal::Term);
        for _ in 0..50 {
            if record.state.lock().await.completed_at.is_some() {
                return self.status(request.process_id, request.run_id).await;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        let _ = send_group_signal(record.pgid, Signal::Kill);
        for _ in 0..50 {
            if record.state.lock().await.completed_at.is_some() {
                return self.status(request.process_id, request.run_id).await;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        Err(AppError::Sidecar("PROCESS_CANCEL_TIMEOUT".to_owned()))
    }

    pub async fn status(&self, process_id: Uuid, run_id: Uuid) -> Result<Value, AppError> {
        let record = self.record(process_id, run_id).await?;
        let state = record.state.lock().await.clone();
        let stdout = record.stdout.lock().await.clone();
        let stderr = record.stderr.lock().await.clone();
        let last_sequence = *record.last_sequence.lock().await;
        let terminal = state.completed_at.is_some();
        let status = if terminal {
            if state.timed_out {
                "timed_out"
            } else if state.termination_reason == Some("cancelled") {
                "cancelled"
            } else {
                "exited"
            }
        } else {
            "running"
        };
        let hash = |value: &[u8]| {
            use sha2::{Digest, Sha256};
            Sha256::digest(value)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>()
        };
        Ok(json!({
            "process_id": record.process_id,
            "run_id": record.run_id,
            "state": if terminal { "exited" } else { "running" },
            "status": status,
            "timed_out": state.timed_out,
            "cancellation_requested": state.cancellation_requested,
            "pid": record.pid,
            "pgid": record.pgid,
            "start_time": state.started_at.to_rfc3339(),
            "exit_code": state.exit_code,
            "signal": state.signal,
            "last_sequence": last_sequence,
            "ended_at": state.completed_at.map(|value| value.to_rfc3339()),
            // These fields are retained for the Sidecar's terminal report.
            // The fixed protocol fields above remain authoritative.
            "stdout": String::from_utf8_lossy(&stdout.bytes),
            "stderr": String::from_utf8_lossy(&stderr.bytes),
            "stdout_sha256": hash(&stdout.bytes),
            "stderr_sha256": hash(&stderr.bytes),
            "output_truncated": stdout.truncated || stderr.truncated,
        }))
    }

    async fn record(&self, process_id: Uuid, run_id: Uuid) -> Result<Arc<ProcessRecord>, AppError> {
        let record = self
            .records
            .lock()
            .await
            .get(&process_id)
            .cloned()
            .ok_or_else(|| AppError::NotFound("RESOURCE_NOT_FOUND".to_owned()))?;
        if record.run_id != run_id {
            return Err(AppError::NotFound("RESOURCE_NOT_FOUND".to_owned()));
        }
        Ok(record)
    }
}

fn validate_request(request: &StartProcessRequest) -> Result<PathBuf, AppError> {
    if request.argv.is_empty() || request.argv.iter().any(|part| part.is_empty()) {
        return Err(AppError::Validation("PROCESS_ARGV_INVALID".to_owned()));
    }
    if request.argv.len() > 128 || request.argv.iter().any(|part| part.len() > 32 * 1024) {
        return Err(AppError::Validation("PROCESS_ARGV_TOO_LARGE".to_owned()));
    }
    for value in [
        &request.execution_snapshot_sha256,
        &request.workspace_policy_sha256,
        &request.network_policy_sha256,
    ] {
        if value.len() != 64
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        {
            return Err(AppError::Validation(
                "PROCESS_POLICY_HASH_INVALID".to_owned(),
            ));
        }
    }
    if request.locale.trim().is_empty()
        || request.locale.contains('\n')
        || request.locale.contains('\r')
    {
        return Err(AppError::Validation("PROCESS_LOCALE_INVALID".to_owned()));
    }
    if request.deadline_at <= Utc::now() {
        return Err(AppError::Validation("PROCESS_DEADLINE_EXPIRED".to_owned()));
    }
    if !request.executable_realpath.is_absolute() || !request.cwd_realpath.is_absolute() {
        return Err(AppError::Validation("PROCESS_PATH_NOT_ABSOLUTE".to_owned()));
    }
    let executable = std::fs::canonicalize(&request.executable_realpath)
        .map_err(|_| AppError::Validation("AGENT_EXECUTABLE_NOT_FOUND".to_owned()))?;
    if !executable.is_file()
        || executable != request.executable_realpath
        || request.argv[0] != request.executable_realpath.to_string_lossy()
    {
        return Err(AppError::Validation(
            "PROCESS_EXECUTABLE_MISMATCH".to_owned(),
        ));
    }
    let workspace = std::fs::canonicalize(&request.cwd_realpath)
        .map_err(|_| AppError::Validation("WORKSPACE_ACCESS_DENIED".to_owned()))?;
    if !workspace.is_dir() || workspace != request.cwd_realpath {
        return Err(AppError::Validation("WORKSPACE_ACCESS_DENIED".to_owned()));
    }
    Ok(workspace)
}

fn decode_stdin(encoded: Option<&str>) -> Result<Option<Vec<u8>>, AppError> {
    let Some(encoded) = encoded else {
        return Ok(None);
    };
    use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
    let bytes = BASE64
        .decode(encoded)
        .map_err(|_| AppError::Validation("PROCESS_STDIN_INVALID_BASE64".to_owned()))?;
    if bytes.len() > MAX_STDIN_BYTES {
        return Err(AppError::Validation("PROCESS_STDIN_TOO_LARGE".to_owned()));
    }
    Ok(Some(bytes))
}

#[allow(clippy::too_many_arguments)]
fn build_command(
    executable: &Path,
    argv: &[String],
    workspace: &Path,
    runtime_tmp: &Path,
    agent_home: &Path,
    user_home: &Path,
    locale: &str,
    proxy_url: &str,
) -> Command {
    let mut command = Command::new(executable);
    command
        // `argv` is already the exact argument vector for the selected
        // program.  For macOS this is the `sandbox-exec` vector (`-f`,
        // profile, `--`, executable, ...); dropping its first element would
        // silently remove `-f` and start the child outside the intended
        // Seatbelt profile.
        .args(argv)
        .current_dir(workspace)
        .env_clear()
        .env("PATH", "/usr/local/bin:/usr/bin:/bin")
        .env("LANG", locale)
        .env("LC_ALL", locale)
        .env("TERM", "dumb")
        .env("TMPDIR", runtime_tmp)
        .env("HOME", user_home)
        .env("CODEX_HOME", agent_home.join("codex"))
        .env("CLAUDE_CONFIG_DIR", agent_home.join("claude"))
        .env("XDG_CONFIG_HOME", agent_home.join("opencode/config"))
        .env("XDG_DATA_HOME", agent_home.join("opencode/data"))
        .env("XDG_CACHE_HOME", agent_home.join("opencode/cache"))
        .env("HTTP_PROXY", proxy_url)
        .env("HTTPS_PROXY", proxy_url)
        .env("ALL_PROXY", proxy_url)
        .env("NO_PROXY", "")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    command
}

#[allow(clippy::too_many_arguments)]
async fn verify_agent_version(
    policy: &AgentVersionRangePolicy,
    executable: &Path,
    workspace: &Path,
    runtime_root: &Path,
    runtime_tmp: &Path,
    agent_home: &Path,
    user_home: &Path,
    proxy_port: u16,
    locale: &str,
) -> Result<Version, AppError> {
    let mut probe_argv = policy.probe_argv.clone();
    if probe_argv.is_empty() || probe_argv.iter().any(|part| part.is_empty()) {
        return Err(AppError::Security("AGENT_VERSION_PROBE_INVALID".to_owned()));
    }
    // The signed catalog identifies the executable by name.  The resolved
    // canonical path supplied in the start request is the only executable
    // allowed to run; never execute the catalog's argv[0] as a PATH lookup.
    probe_argv[0] = executable.to_string_lossy().into_owned();
    validate_agent_argv(&probe_argv)?;
    let invocation = seatbelt::build_invocation(
        executable,
        &probe_argv,
        workspace,
        runtime_root,
        runtime_tmp,
        agent_home,
        proxy_port,
        &RunPurpose::Verification,
    )?;
    let mut command = build_command(
        &invocation.program,
        &invocation.args,
        workspace,
        runtime_tmp,
        agent_home,
        user_home,
        locale,
        &format!("http://127.0.0.1:{proxy_port}"),
    );
    configure_process_group(&mut command);
    let mut child = command
        .spawn()
        .map_err(|_| AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()))?;
    if let Some(profile) = invocation.profile_path {
        let _ = std::fs::remove_file(profile);
    }
    let pgid = match child.id() {
        Some(pid) => pid,
        None => {
            let _ = child.start_kill();
            let _ = child.wait().await;
            return Err(AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()));
        }
    };
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let stdout_task = tokio::spawn(read_bounded_output(stdout));
    let stderr_task = tokio::spawn(read_bounded_output(stderr));
    let status = match tokio::time::timeout(VERSION_PROBE_TIMEOUT, child.wait()).await {
        Ok(Ok(status)) => status,
        Ok(Err(_)) => {
            let _ = stdout_task.await;
            let _ = stderr_task.await;
            return Err(AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()));
        }
        Err(_) => {
            let _ = send_group_signal(pgid, Signal::Int);
            tokio::time::sleep(Duration::from_millis(100)).await;
            let _ = send_group_signal(pgid, Signal::Term);
            tokio::time::sleep(Duration::from_millis(100)).await;
            let _ = send_group_signal(pgid, Signal::Kill);
            let _ = child.wait().await;
            let _ = stdout_task.await;
            let _ = stderr_task.await;
            return Err(AppError::Security("AGENT_VERSION_PROBE_TIMEOUT".to_owned()));
        }
    };
    let stdout = stdout_task
        .await
        .map_err(|_| AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()))??;
    let stderr = stderr_task
        .await
        .map_err(|_| AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()))??;
    if !status.success() {
        return Err(AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()));
    }
    let mut output = stdout;
    output.extend_from_slice(&stderr);
    let version = extract_semver(&output)
        .ok_or_else(|| AppError::Security("AGENT_VERSION_UNPARSEABLE".to_owned()))?;
    if version < policy.min_version || version >= policy.max_version_exclusive {
        return Err(AppError::Security("AGENT_VERSION_UNSUPPORTED".to_owned()));
    }
    Ok(version)
}

async fn read_bounded_output<R: AsyncRead + Unpin + Send + 'static>(
    stream: Option<R>,
) -> Result<Vec<u8>, AppError> {
    let Some(stream) = stream else {
        return Ok(Vec::new());
    };
    let mut reader =
        tokio::io::BufReader::new(stream).take((MAX_VERSION_PROBE_OUTPUT_BYTES + 1) as u64);
    let mut bytes = Vec::new();
    reader
        .read_to_end(&mut bytes)
        .await
        .map_err(|_| AppError::Security("AGENT_VERSION_PROBE_FAILED".to_owned()))?;
    if bytes.len() > MAX_VERSION_PROBE_OUTPUT_BYTES {
        return Err(AppError::Security(
            "AGENT_VERSION_PROBE_OUTPUT_TOO_LARGE".to_owned(),
        ));
    }
    Ok(bytes)
}

fn extract_semver(output: &[u8]) -> Option<Version> {
    let text = String::from_utf8_lossy(output);
    text.split(|character: char| {
        !(character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '+'))
    })
    .filter_map(|token| token.trim_start_matches(['v', 'V']).parse::<Version>().ok())
    .next()
}

fn validate_agent_argv(argv: &[String]) -> Result<(), AppError> {
    const FORBIDDEN: &[&str] = &[
        "--share",
        "--attach",
        "--listen",
        "--server",
        "--http-server",
    ];
    if argv.iter().skip(1).any(|argument| {
        FORBIDDEN.iter().any(|flag| {
            argument == flag
                || argument
                    .strip_prefix(flag)
                    .is_some_and(|suffix| suffix.starts_with('='))
        })
    }) {
        return Err(AppError::Security("AGENT_ARGV_NETWORK_ESCAPE".to_owned()));
    }
    Ok(())
}

/// Catalog releases use an OS/architecture platform identifier so a signed
/// range cannot accidentally enable an ARM-only executable on x86 (or vice
/// versa).  Keep the bare OS aliases for development catalogs and older
/// signed releases, while matching the concrete identifier first.
fn platform_matches(supported: &BTreeSet<String>) -> bool {
    platform_aliases()
        .iter()
        .any(|alias| supported.contains(*alias))
}

fn platform_aliases() -> Vec<&'static str> {
    let os = std::env::consts::OS;
    let arch = std::env::consts::ARCH;
    match (os, arch) {
        ("macos", "aarch64") => vec!["macos_arm64", "macos_aarch64", "macos", "darwin"],
        ("macos", "x86_64") => vec!["macos_x86_64", "macos_amd64", "macos", "darwin"],
        ("linux", "aarch64") => vec!["linux_arm64", "linux_aarch64", "linux", "unix"],
        ("linux", "x86_64") => vec!["linux_x86_64", "linux_amd64", "linux", "unix"],
        ("windows", "x86_64") => vec!["windows_x86_64", "windows_amd64", "windows"],
        ("windows", "aarch64") => vec!["windows_arm64", "windows_aarch64", "windows"],
        _ => vec![os],
    }
}

#[derive(Clone)]
struct OutputContext {
    supervisor: ProcessSupervisor,
    process_id: Uuid,
    run_id: Uuid,
    pgid: u32,
    output_emit_lock: Arc<Mutex<()>>,
}

async fn read_output<R: AsyncRead + Unpin>(
    stream: Option<R>,
    buffer: Arc<Mutex<OutputBuffer>>,
    context: OutputContext,
    stream_name: &'static str,
) {
    let Some(mut stream) = stream.map(tokio::io::BufReader::new) else {
        return;
    };
    let mut chunk = [0_u8; 8192];
    loop {
        match stream.read(&mut chunk).await {
            Ok(0) | Err(_) => break,
            Ok(size) => {
                // Sequence allocation and the corresponding notification
                // must be one critical section.  stdout/stderr readers are
                // concurrent and Sidecar rejects gaps or out-of-order frames.
                let _emit_guard = context.output_emit_lock.lock().await;
                let chunk_bytes = &chunk[..size];
                let sequence = match buffer.lock().await.append(chunk_bytes).await {
                    Ok(sequence) => sequence,
                    Err(_) => {
                        let _ = send_group_signal(context.pgid, Signal::Kill);
                        break;
                    }
                };
                let encoded = {
                    use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
                    BASE64.encode(chunk_bytes)
                };
                if context
                    .supervisor
                    .emit(
                        "runtime.process.output",
                        serde_json::json!({
                            "process_id": context.process_id,
                            "run_id": context.run_id,
                            "sequence": sequence,
                            "stream": stream_name,
                            "chunk_base64": encoded,
                            "observed_at": Utc::now().to_rfc3339(),
                        }),
                    )
                    .await
                    .is_err()
                {
                    let _ = send_group_signal(context.pgid, Signal::Kill);
                    break;
                }
            }
        }
    }
}

#[derive(Clone, Copy)]
enum Signal {
    Int,
    Term,
    Kill,
}

fn send_group_signal(pgid: u32, signal: Signal) -> Result<(), AppError> {
    #[cfg(unix)]
    {
        use nix::sys::signal::{killpg, Signal as NixSignal};
        use nix::unistd::Pid;
        let value = match signal {
            Signal::Int => NixSignal::SIGINT,
            Signal::Term => NixSignal::SIGTERM,
            Signal::Kill => NixSignal::SIGKILL,
        };
        killpg(Pid::from_raw(pgid as i32), value)
            .map_err(|error| AppError::Sidecar(format!("PROCESS_SIGNAL_FAILED: {error}")))?;
    }
    #[cfg(not(unix))]
    let _ = (pgid, signal);
    Ok(())
}

fn configure_process_group(command: &mut Command) {
    #[cfg(unix)]
    {
        use nix::unistd::{setpgid, Pid};
        use std::os::unix::process::CommandExt;
        // SAFETY: pre_exec only calls async-signal-safe setpgid.
        unsafe {
            command.as_std_mut().pre_exec(|| {
                setpgid(Pid::from_raw(0), Pid::from_raw(0)).map_err(std::io::Error::other)
            });
        }
    }
}

fn set_private_directory(path: &Path) -> Result<(), AppError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))
            .map_err(|error| AppError::Storage(error.to_string()))?;
    }
    Ok(())
}

fn prepare_runtime_dirs(
    run_root: &Path,
    runtime_tmp: &Path,
    agent_home: &Path,
) -> Result<(), AppError> {
    std::fs::create_dir_all(runtime_tmp)
        .map_err(|_| AppError::Validation("WORKSPACE_ACCESS_DENIED".to_owned()))?;
    std::fs::create_dir_all(agent_home)
        .map_err(|_| AppError::Validation("WORKSPACE_ACCESS_DENIED".to_owned()))?;
    set_private_directory(run_root)?;
    set_private_directory(runtime_tmp)?;
    set_private_directory(agent_home)?;
    for relative in [
        "codex",
        "claude",
        "opencode/config",
        "opencode/data",
        "opencode/cache",
    ] {
        let directory = agent_home.join(relative);
        std::fs::create_dir_all(&directory)
            .map_err(|_| AppError::Validation("WORKSPACE_ACCESS_DENIED".to_owned()))?;
        set_private_directory(&directory)?;
    }
    Ok(())
}

fn cleanup_run_root(path: &Path) {
    let _ = std::fs::remove_dir_all(path);
}

#[cfg(test)]
mod tests {
    use super::{extract_semver, platform_matches, validate_agent_argv};
    use semver::Version;
    use std::collections::BTreeSet;

    #[test]
    fn extracts_version_from_common_cli_output() {
        assert_eq!(
            extract_semver(b"codex-cli 0.42.1 (commit abc)"),
            Some(Version::new(0, 42, 1))
        );
        assert_eq!(
            extract_semver(b"version: v1.2.3\n"),
            Some(Version::new(1, 2, 3))
        );
        assert_eq!(extract_semver(b"development build"), None);
    }

    #[test]
    fn rejects_probe_arguments_that_enable_listeners() {
        let args = vec!["codex".to_owned(), "--listen=0.0.0.0:9000".to_owned()];
        assert!(validate_agent_argv(&args).is_err());
    }

    #[test]
    fn accepts_catalog_platform_aliases_for_current_target() {
        let supported = BTreeSet::from([
            std::env::consts::OS.to_owned(),
            format!("{}_{}", std::env::consts::OS, std::env::consts::ARCH),
        ]);
        assert!(platform_matches(&supported));
    }

    #[test]
    fn rejects_platform_for_another_operating_system() {
        let supported = BTreeSet::from(["definitely-not-this-platform".to_owned()]);
        assert!(!platform_matches(&supported));
    }
}

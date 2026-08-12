// DO NOT EDIT MANUALLY
// Generated from packages/rpc-schema/registry.v1.json
//
// 120 total methods (50 read, 70 write)
// 49 sidecar reads, 63 sidecar writes

/// Returns `true` when the method is a read (idempotent, safe to retry without idempotency key).
/// Returns `None` when the method is not in the registry.
pub fn method_is_read(method: &str) -> Option<bool> {
    if method_matches(method, READ_METHODS) {
        Some(true)
    } else if method_matches(method, WRITE_METHODS) {
        Some(false)
    } else {
        None
    }
}

/// Returns `Some(false)` for Rust-core reads, `Some(true)` for Rust-core writes,
/// and `None` for methods owned by another process or unknown methods.
pub fn rust_core_method_kind(method: &str) -> Option<bool> {
    if method_matches(method, RUST_CORE_READ_METHODS) {
        Some(false)
    } else if method_matches(method, RUST_CORE_WRITE_METHODS) {
        Some(true)
    } else {
        None
    }
}

/// Returns `true` when the method is a write (requires idempotency key).
/// Returns `None` when the method is not in the registry.
pub fn method_is_write(method: &str) -> Option<bool> {
    if method_matches(method, WRITE_METHODS) {
        Some(true)
    } else if method_matches(method, READ_METHODS) {
        Some(false)
    } else {
        None
    }
}

/// Returns `Some(false)` for sidecar-owned reads, `Some(true)` for sidecar-owned writes,
/// `None` for methods not owned by the sidecar (rust_core, unknown, etc.).
pub fn sidecar_method_kind(method: &str) -> Option<bool> {
    if method_matches(method, SIDECAR_READ_METHODS) {
        Some(false)
    } else if method_matches(method, SIDECAR_WRITE_METHODS) {
        Some(true)
    } else {
        None
    }
}

const READ_METHODS: &[&str] = &[
    "approval.listPending",
    "artifact.get",
    "artifact.getSnapshot",
    "artifact.list",
    "auth.listOfflineProfiles",
    "backup.get",
    "backup.list",
    "catalog.get",
    "catalog.getActiveRelease",
    "catalog.list",
    "catalog.listAgents",
    "catalog.listModels",
    "catalog.listSkills",
    "company.get",
    "company.list",
    "conversation.getCompany",
    "conversation.getDepartment",
    "conversation.list",
    "conversation.listMessages",
    "department.get",
    "department.list",
    "departmentTask.get",
    "departmentTask.getReport",
    "departmentTask.list",
    "employee.get",
    "employee.list",
    "employeeTask.get",
    "employeeTask.list",
    "knowledge.get",
    "knowledge.list",
    "knowledge.search",
    "profile.get",
    "profile.list",
    "review.get",
    "review.list",
    "review.listIssues",
    "run.get",
    "run.list",
    "run.listEvents",
    "runtime.getStatus",
    "runtime.listAvailableModels",
    "runtime.probeAgent",
    "runtime.probeProvider",
    "settings.get",
    "task.get",
    "task.getEvidence",
    "task.getGraph",
    "task.list",
    "workspace.get",
    "workspace.list",
];

const WRITE_METHODS: &[&str] = &[
    "approval.resolve",
    "artifact.create",
    "auth.changePassword",
    "auth.closeProfile",
    "auth.login",
    "auth.logout",
    "auth.openProfile",
    "auth.register",
    "backend.validateOrigin",
    "backup.create",
    "backup.restore",
    "catalog.installSkill",
    "catalog.removeSkill",
    "catalog.sync",
    "catalog.verifyCache",
    "company.archive",
    "company.create",
    "company.update",
    "conversation.archive",
    "conversation.create",
    "conversation.submitUserMessage",
    "department.archive",
    "department.create",
    "department.responsibility.create",
    "department.responsibility.delete",
    "department.responsibility.update",
    "department.setLeader",
    "department.update",
    "departmentTask.checkResources",
    "departmentTask.replaceEmployee",
    "employee.archive",
    "employee.create",
    "employee.transfer",
    "employee.updateBaseProfile",
    "employee.updateDisplayName",
    "employee.updateStatus",
    "employee.updateWorkRole",
    "event.replay",
    "event.subscribe",
    "knowledge.import",
    "knowledge.remove",
    "profile.bindSkill",
    "profile.createDraft",
    "profile.publish",
    "profile.retire",
    "profile.retireVersion",
    "profile.unbindSkill",
    "profile.updateDraft",
    "profile.validate",
    "report.generateDepartment",
    "report.generateFinal",
    "review.assign",
    "review.rerun",
    "review.resolveIssue",
    "review.submit",
    "run.cancel",
    "run.resume",
    "runtime.run",
    "runtime.stop",
    "settings.update",
    "task.cancel",
    "task.confirmPlan",
    "task.pause",
    "task.rejectPlan",
    "task.requestPlanRevision",
    "task.resume",
    "task.supersede",
    "workspace.abandon",
    "workspace.apply",
    "workspace.cleanupTask",
];

const SIDECAR_READ_METHODS: &[&str] = &[
    "approval.listPending",
    "artifact.get",
    "artifact.getSnapshot",
    "artifact.list",
    "backup.get",
    "backup.list",
    "catalog.get",
    "catalog.getActiveRelease",
    "catalog.list",
    "catalog.listAgents",
    "catalog.listModels",
    "catalog.listSkills",
    "company.get",
    "company.list",
    "conversation.getCompany",
    "conversation.getDepartment",
    "conversation.list",
    "conversation.listMessages",
    "department.get",
    "department.list",
    "departmentTask.get",
    "departmentTask.getReport",
    "departmentTask.list",
    "employee.get",
    "employee.list",
    "employeeTask.get",
    "employeeTask.list",
    "knowledge.get",
    "knowledge.list",
    "knowledge.search",
    "profile.get",
    "profile.list",
    "review.get",
    "review.list",
    "review.listIssues",
    "run.get",
    "run.list",
    "run.listEvents",
    "runtime.getStatus",
    "runtime.listAvailableModels",
    "runtime.probeAgent",
    "runtime.probeProvider",
    "settings.get",
    "task.get",
    "task.getEvidence",
    "task.getGraph",
    "task.list",
    "workspace.get",
    "workspace.list",
];

const SIDECAR_WRITE_METHODS: &[&str] = &[
    "approval.resolve",
    "artifact.create",
    "backup.create",
    "backup.restore",
    "catalog.installSkill",
    "catalog.removeSkill",
    "catalog.sync",
    "catalog.verifyCache",
    "company.archive",
    "company.create",
    "company.update",
    "conversation.archive",
    "conversation.create",
    "conversation.submitUserMessage",
    "department.archive",
    "department.create",
    "department.responsibility.create",
    "department.responsibility.delete",
    "department.responsibility.update",
    "department.setLeader",
    "department.update",
    "departmentTask.checkResources",
    "departmentTask.replaceEmployee",
    "employee.archive",
    "employee.create",
    "employee.transfer",
    "employee.updateBaseProfile",
    "employee.updateDisplayName",
    "employee.updateStatus",
    "employee.updateWorkRole",
    "event.replay",
    "event.subscribe",
    "knowledge.import",
    "knowledge.remove",
    "profile.bindSkill",
    "profile.createDraft",
    "profile.publish",
    "profile.retire",
    "profile.retireVersion",
    "profile.unbindSkill",
    "profile.updateDraft",
    "profile.validate",
    "report.generateDepartment",
    "report.generateFinal",
    "review.assign",
    "review.rerun",
    "review.resolveIssue",
    "review.submit",
    "run.cancel",
    "run.resume",
    "runtime.run",
    "runtime.stop",
    "settings.update",
    "task.cancel",
    "task.confirmPlan",
    "task.pause",
    "task.rejectPlan",
    "task.requestPlanRevision",
    "task.resume",
    "task.supersede",
    "workspace.abandon",
    "workspace.apply",
    "workspace.cleanupTask",
];

const RUST_CORE_READ_METHODS: &[&str] = &["auth.listOfflineProfiles"];

const RUST_CORE_WRITE_METHODS: &[&str] = &[
    "auth.changePassword",
    "auth.closeProfile",
    "auth.login",
    "auth.logout",
    "auth.openProfile",
    "auth.register",
    "backend.validateOrigin",
];

fn method_matches(method: &str, table: &[&str]) -> bool {
    table.binary_search(&method).is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_method_kinds_known() {
        assert!(method_is_read("company.list").unwrap());
        assert!(!method_is_read("company.create").unwrap());
        assert!(method_is_write("company.create").unwrap());
        assert!(!method_is_write("company.list").unwrap());
    }

    #[test]
    fn test_method_kinds_unknown() {
        assert!(method_is_read("nonexistent.method").is_none());
        assert!(method_is_write("nonexistent.method").is_none());
    }

    #[test]
    fn test_sidecar_method_kind_known() {
        assert!(!sidecar_method_kind("company.list").expect("sidecar read"));
        assert!(sidecar_method_kind("company.create").expect("sidecar write"));
    }

    #[test]
    fn test_sidecar_method_kind_rejects_rust_core() {
        assert!(sidecar_method_kind("auth.login").is_none());
        assert!(sidecar_method_kind("backend.validateOrigin").is_none());
    }

    #[test]
    fn test_rust_core_method_kind_known() {
        assert!(!rust_core_method_kind("auth.listOfflineProfiles").expect("rust core read"));
        assert!(rust_core_method_kind("auth.login").expect("rust core write"));
        assert!(rust_core_method_kind("backend.validateOrigin").expect("rust core write"));
    }

    #[test]
    fn test_sidecar_method_kind_unknown() {
        assert!(sidecar_method_kind("nonexistent.method").is_none());
    }
}

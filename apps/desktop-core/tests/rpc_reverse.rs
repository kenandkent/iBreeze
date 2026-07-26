use serde_json::json;
use uuid::Uuid;

/// CT-010: Sidecar → Rust credential.http.* method validation
#[test]
fn reverse_method_allowlist_coverage() {
    let allowed = ibreeze_desktop_core::rpc::reverse::ALLOWED_REVERSE_METHODS;
    assert!(
        allowed.contains(&"credential.http.start"),
        "credential.http.start must be allowed"
    );
    assert!(
        allowed.contains(&"credential.http.cancel"),
        "credential.http.cancel must be allowed"
    );
    assert!(
        allowed.contains(&"credential.probe"),
        "credential.probe must be allowed"
    );
    assert!(
        allowed.contains(&"host.externalWrite.execute"),
        "host.externalWrite.execute must be allowed"
    );

    let notifications = ibreeze_desktop_core::rpc::reverse::ALLOWED_REVERSE_NOTIFICATIONS;
    assert!(
        notifications.contains(&"runtime.processRegistered"),
        "runtime.processRegistered must be a notification"
    );
    assert!(
        notifications.contains(&"runtime.processExited"),
        "runtime.processExited must be a notification"
    );
}

/// CT-011: host.externalWrite.execute request/response contract
#[test]
fn external_write_request_roundtrip() {
    let request = ibreeze_desktop_core::rpc::reverse::ExternalWriteRequest {
        approval_id: Uuid::new_v4(),
        run_id: Uuid::new_v4(),
        operation: ibreeze_desktop_core::rpc::reverse::ExternalWriteOperation::CreateFile,
        target_realpath: "/Users/test/workspace/output.txt".to_owned(),
        expected_old_sha256: None,
        source_relative_path: Some("staging/output.txt".to_owned()),
        source_sha256: Some("abc123".to_owned()),
        source_size: Some(1024),
        expires_at: "2026-12-31T23:59:59Z".to_owned(),
    };

    let json = serde_json::to_value(&request).expect("serialize");
    assert_eq!(json["operation"], "create_file");
    assert!(json.get("expected_old_sha256").unwrap().is_null());
    assert!(json.get("source_relative_path").unwrap().is_string());

    let deserialized: ibreeze_desktop_core::rpc::reverse::ExternalWriteRequest =
        serde_json::from_value(json).expect("deserialize");
    assert_eq!(deserialized.approval_id, request.approval_id);
    assert_eq!(deserialized.operation, request.operation);
}

#[test]
fn external_write_response_has_all_fields() {
    let response = ibreeze_desktop_core::rpc::reverse::ExternalWriteResponse {
        approval_id: Uuid::new_v4(),
        run_id: Uuid::new_v4(),
        operation: ibreeze_desktop_core::rpc::reverse::ExternalWriteOperation::ReplaceFile,
        target_realpath: "/Users/test/workspace/output.txt".to_owned(),
        result_state_sha256: "state-hash".to_owned(),
        completed_at: "2026-12-31T23:59:59Z".to_owned(),
        receipt_sha256: "receipt-hash".to_owned(),
    };

    let json = serde_json::to_value(&response).expect("serialize");
    assert_eq!(json.as_object().expect("object").len(), 7);
    assert_eq!(json["operation"], "replace_file");
}

/// CT-012: runtime.processRegistered/Exited notification schema
#[test]
fn process_event_schema() {
    let event = ibreeze_desktop_core::rpc::reverse::ProcessEvent {
        pid: 12345,
        pgid: 12345,
        start_time: "2026-07-26T10:00:00Z".to_owned(),
        executable: "/usr/local/bin/ibreeze-sidecar".to_owned(),
        parent_pid: 1000,
    };

    let json = serde_json::to_value(&event).expect("serialize");
    assert_eq!(json["pid"], 12345);
    assert_eq!(json["pgid"], 12345);
    assert!(json.get("start_time").unwrap().is_string());
    assert_eq!(json["parent_pid"], 1000);

    let deserialized: ibreeze_desktop_core::rpc::reverse::ProcessEvent =
        serde_json::from_value(json).expect("deserialize");
    assert_eq!(deserialized.pid, 12345);
    assert_eq!(deserialized.executable, "/usr/local/bin/ibreeze-sidecar");
}

/// Verify that unknown fields are rejected in reverse RPC requests
#[test]
fn reverse_request_rejects_unknown_fields() {
    let with_extra = json!({
        "approval_id": Uuid::new_v4().to_string(),
        "run_id": Uuid::new_v4().to_string(),
        "operation": "create_file",
        "target_realpath": "/tmp/test.txt",
        "expected_old_sha256": null,
        "source_relative_path": null,
        "source_sha256": null,
        "source_size": null,
        "expires_at": "2026-12-31T23:59:59Z",
        "extra_field": "should be rejected"
    });
    assert!(
        serde_json::from_value::<ibreeze_desktop_core::rpc::reverse::ExternalWriteRequest>(
            with_extra
        )
        .is_err()
    );
}

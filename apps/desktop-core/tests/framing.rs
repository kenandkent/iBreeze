use ibreeze_desktop_core::rpc::protocol::MAX_FRAME_BYTES;

/// Frame protocol: 4-byte big-endian u32 length + UTF-8 JSON body.
/// - Single object only (no top-level arrays, no batch)
/// - Max 16 MiB per frame
/// - Zero-length frame is invalid
#[test]
fn max_frame_size_is_16_mib() {
    assert_eq!(MAX_FRAME_BYTES, 16 * 1024 * 1024);
}

/// Verify that the frame size calculation for a typical request
/// stays well within limits.
#[test]
fn typical_request_is_within_frame_limit() {
    let request = serde_json::json!({
        "jsonrpc": "2.0",
        "id": "core:550e8400-e29b-41d4-a716-446655440000",
        "method": "system.health",
        "params": {},
        "meta": {
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "ipc_session_id": "550e8400-e29b-41d4-a716-446655440000",
            "window_session_id": "550e8400-e29b-41d4-a716-446655440000",
            "idempotency_key": null
        }
    });
    let payload = serde_json::to_vec(&request).expect("serialize request");
    assert!(payload.len() < MAX_FRAME_BYTES);
    assert!(!payload.is_empty());
}

/// Verify that the frame header (4 bytes big-endian) can represent
/// sizes up to MAX_FRAME_BYTES.
#[test]
fn frame_header_covers_max_size() {
    let bytes = (MAX_FRAME_BYTES as u32).to_be_bytes();
    assert_eq!(bytes.len(), 4);
    let decoded = u32::from_be_bytes(bytes) as usize;
    assert_eq!(decoded, MAX_FRAME_BYTES);
}

/// Verify that JSON-RPC request has the right structure with meta.
#[test]
fn rpc_request_includes_meta() {
    let request = serde_json::json!({
        "jsonrpc": "2.0",
        "id": "core:test-id",
        "method": "company.list",
        "params": {"filter": {}},
        "meta": {
            "trace_id": "00000000-0000-4000-8000-000000000001",
            "ipc_session_id": "00000000-0000-4000-8000-000000000002",
            "window_session_id": "00000000-0000-4000-8000-000000000003",
            "idempotency_key": null
        }
    });
    assert_eq!(request["jsonrpc"], "2.0");
    assert!(request["id"].as_str().unwrap().starts_with("core:"));
    assert!(request["meta"].is_object());
}

/// Verify that the protocol constants are reasonable.
#[test]
fn protocol_constants_are_valid() {
    assert_eq!(ibreeze_desktop_core::rpc::protocol::JSON_RPC_VERSION, "2.0");
    assert_eq!(ibreeze_desktop_core::rpc::protocol::PROTOCOL_VERSION, 1);
}

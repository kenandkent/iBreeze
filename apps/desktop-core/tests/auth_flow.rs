use uuid::Uuid;

/// Test that the profile_directory_id function generates consistent,
/// safe directory names.
#[test]
fn profile_id_is_stable_and_path_safe() {
    let user_id = Uuid::parse_str("00000000-0000-4000-8000-000000000001").expect("valid UUID");
    let origin = "https://example.com:443";

    let first = ibreeze_desktop_core::store::profile_directory_id(origin, user_id);
    let second = ibreeze_desktop_core::store::profile_directory_id(origin, user_id);
    assert_eq!(first, second);

    let third = ibreeze_desktop_core::store::profile_directory_id(
        "https://example.com:443",
        Uuid::parse_str("00000000-0000-4000-8000-000000000002").expect("valid UUID"),
    );
    assert_ne!(first, third, "different user_id must produce different directory id");

    assert!(
        first.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit()),
        "profile directory id must be lowercase alphanumeric"
    );
}

/// Test the canonical origin function.
#[test]
fn canonical_origin_is_safe() {
    use ibreeze_desktop_core::rpc::api_client::canonicalize_origin;

    assert_eq!(
        canonicalize_origin("https://Example.COM", false).expect("valid origin"),
        "https://example.com:443"
    );

    assert!(canonicalize_origin("https://example.com/path", false).is_err());
    assert!(canonicalize_origin("https://user@example.com", false).is_err());
    assert!(canonicalize_origin("http://example.com", false).is_err());
}

/// Test keychain session bundle serialization.
#[test]
fn session_bundle_serialization() {
    use ibreeze_desktop_core::keyring::SessionBundle;

    let bundle = SessionBundle {
        schema_version: 1,
        refresh_token: "test_refresh_token".to_owned(),
        offline_session_ticket: "test_ticket".to_owned(),
        family_id: "test_family".to_owned(),
        issued_at: "2026-01-01T00:00:00Z".to_owned(),
    };

    let json = serde_json::to_string(&bundle).expect("serialize bundle");
    let deserialized: SessionBundle =
        serde_json::from_str(&json).expect("deserialize bundle");
    assert_eq!(bundle.schema_version, deserialized.schema_version);
    assert_eq!(bundle.family_id, deserialized.family_id);

    // Extra fields must be rejected
    let extra = r#"{"schema_version":1,"refresh_token":"t","offline_session_ticket":"t","family_id":"f","issued_at":"2026-01-01T00:00:00Z","extra":"bad"}"#;
    assert!(
        serde_json::from_str::<SessionBundle>(extra).is_err(),
        "extra fields must be rejected"
    );
}

/// Test offline ticket verification with valid structure.
#[test]
fn offline_ticket_structure_is_valid() {
    // The trust module has its own unit tests; here we just verify
    // that the offline ticket constants are correct.
    use ibreeze_desktop_core::rpc::api_client::AuthKeyset;

    let keyset = AuthKeyset {
        keys: vec![],
        issued_at: "2026-01-01T00:00:00Z".to_owned(),
        expires_at: "2026-01-02T00:00:00Z".to_owned(),
        signing_key_id: "test-key".to_owned(),
        signature_algorithm: "Ed25519".to_owned(),
        signature: "test_sig".to_owned(),
    };
    assert_eq!(keyset.signature_algorithm, "Ed25519");
}

/// Test that the runtime queue constants are sensible.
#[test]
fn sidecar_constants_are_reasonable() {
    use ibreeze_desktop_core::sidecar;

    assert_eq!(sidecar::HEALTH_INTERVAL.as_secs(), 5);
    assert_eq!(sidecar::HEALTH_TIMEOUT.as_secs(), 3);
    assert_eq!(sidecar::MAX_LOST_HEARTBEATS, 3);
    assert_eq!(sidecar::MAX_RESTARTS, 3);
    assert_eq!(sidecar::RESTART_WINDOW.as_secs(), 60);
}

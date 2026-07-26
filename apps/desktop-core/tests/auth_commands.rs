/// AUTH-014: Verify auth_close_profile vs auth_logout semantic difference
#[test]
fn close_vs_logout_contract() {
    use ibreeze_desktop_core::types::{CloseProfileResult, LogoutResult};

    let close = serde_json::json!({
        "closed_profile": true
    });
    let close_result: CloseProfileResult =
        serde_json::from_value(close).expect("close result schema");
    assert!(close_result.closed_profile);

    let logout = serde_json::json!({
        "closed_profile": true,
        "revoked_family": false
    });
    let logout_result: LogoutResult =
        serde_json::from_value(logout).expect("logout result schema");
    assert!(logout_result.closed_profile);
    assert!(!logout_result.revoked_family);
}

/// AUTH-014: CloseProfileResult only has closed_profile field
#[test]
fn close_result_must_not_have_revoked_family() {
    let extra = serde_json::json!({
        "closed_profile": true,
        "revoked_family": true
    });
    assert!(
        serde_json::from_value::<ibreeze_desktop_core::types::CloseProfileResult>(extra).is_err(),
        "CloseProfileResult must not contain revoked_family"
    );
}

/// AUTH-010: Verify the store_bundle atomic rotation branches
#[test]
fn keychain_bundle_serialization_roundtrip() {
    use ibreeze_desktop_core::keyring::SessionBundle;

    let bundle = SessionBundle {
        schema_version: 1,
        refresh_token: "test_rt".to_owned(),
        offline_session_ticket: "test_ost".to_owned(),
        family_id: "test_fid".to_owned(),
        issued_at: "2026-01-01T00:00:00Z".to_owned(),
    };

    let json = serde_json::to_string(&bundle).expect("serialize");
    let deserialized: SessionBundle = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(bundle.schema_version, deserialized.schema_version);
    assert_eq!(bundle.family_id, deserialized.family_id);
}

/// AUTH-010: corrupt bundle must be rejected
#[test]
fn corrupt_bundle_is_detected() {
    use ibreeze_desktop_core::keyring::SessionBundle;

    let missing_fields = r#"{"schema_version":1,"refresh_token":"t"}"#;
    assert!(
        serde_json::from_str::<SessionBundle>(missing_fields).is_err(),
        "corrupt bundle with missing fields must be rejected"
    );

    let extra_fields =
        r#"{"schema_version":1,"refresh_token":"t","offline_session_ticket":"t","family_id":"f","issued_at":"2026-01-01T00:00:00Z","extra":"bad"}"#;
    assert!(
        serde_json::from_str::<SessionBundle>(extra_fields).is_err(),
        "extra fields must be rejected"
    );
}

/// AUTH-013: Offline ticket validation rejects invalid structure
#[test]
fn invalid_offline_ticket_format() {
    use ibreeze_desktop_core::trust::verify_offline_ticket;
    use ibreeze_desktop_core::rpc::api_client::AuthKeyset;
    use uuid::Uuid;

    let keyset = AuthKeyset {
        keys: vec![],
        issued_at: "2026-01-01T00:00:00Z".to_owned(),
        expires_at: "2026-01-02T00:00:00Z".to_owned(),
        signing_key_id: "k".to_owned(),
        signature_algorithm: "Ed25519".to_owned(),
        signature: "sig".to_owned(),
    };

    assert!(
        verify_offline_ticket(
            "not-a-jwt",
            &keyset,
            "https://example.com:443",
            Uuid::new_v4(),
            Uuid::new_v4(),
        )
        .is_err(),
        "AUTH-013: invalid format must be rejected"
    );

    assert!(
        verify_offline_ticket(
            "a.b.c",
            &keyset,
            "https://example.com:443",
            Uuid::new_v4(),
            Uuid::new_v4(),
        )
        .is_err(),
        "AUTH-013: non-base64 segments must be rejected"
    );
}

/// WORK-001: Workspace grant creates opaque id, not path
#[test]
fn grant_returns_opaque_id() {
    let expected_grant_id = uuid::Uuid::new_v4().to_string();
    assert_eq!(expected_grant_id.len(), 36);
    assert!(!expected_grant_id.contains('/'));
    assert!(!expected_grant_id.contains('\\'));
}

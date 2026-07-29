use uuid::Uuid;
use zeroize::Zeroizing;

use ibreeze_desktop_core::security::CredentialBroker;

#[tokio::test]
async fn register_and_resolve_credential() {
    let broker = CredentialBroker::new();
    let api_key = Zeroizing::new("sk-1234567890abcdef".to_owned());
    broker.register_credential("openai/default", api_key).await;
    let result = broker
        .resolve_credential("openai/default")
        .await
        .expect("resolve credential");
    assert_eq!(result, "sk-1234567890abcdef");
}

#[tokio::test]
async fn unregister_credential_removes_key() {
    let broker = CredentialBroker::new();
    broker
        .register_credential("test/key", Zeroizing::new("secret-value".to_owned()))
        .await;
    assert!(broker.resolve_credential("test/key").await.is_ok());
    broker.unregister_credential("test/key").await;
    assert!(broker.resolve_credential("test/key").await.is_err());
}

#[tokio::test]
async fn resolve_nonexistent_credential_returns_error() {
    let broker = CredentialBroker::new();
    let result = broker.resolve_credential("nonexistent").await;
    assert!(result.is_err());
}

#[tokio::test]
async fn ssrf_guard_blocks_private_ip() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "http://10.0.0.1/test",
        &[],
    )
    .await;
    assert!(result.is_err(), "10.x.x.x should be blocked");

    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "http://192.168.1.1/test",
        &[],
    )
    .await;
    assert!(result.is_err(), "192.168.x.x should be blocked");

    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "http://172.16.0.1/test",
        &[],
    )
    .await;
    assert!(result.is_err(), "172.16.x.x should be blocked");
}

#[tokio::test]
async fn ssrf_guard_blocks_loopback() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "http://127.0.0.1/test",
        &[],
    )
    .await;
    assert!(result.is_err(), "127.0.0.1 should be blocked");
}

#[tokio::test]
async fn ssrf_guard_allows_public_domains() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "https://example.com/path",
        &[],
    )
    .await;
    assert!(
        result.is_ok(),
        "example.com should be allowed: {:?}",
        result.err()
    );
}

#[tokio::test]
async fn ssrf_guard_blocks_file_scheme() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "file:///etc/passwd",
        &[],
    )
    .await;
    assert!(result.is_err(), "file:// scheme should be blocked");
}

#[tokio::test]
async fn ssrf_guard_enforces_allowed_domains() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "https://api.openai.com/v1/completions",
        &["api.openai.com".to_owned()],
    )
    .await;
    assert!(result.is_ok());

    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "https://evil.com/malware",
        &["api.openai.com".to_owned()],
    )
    .await;
    assert!(result.is_err(), "evil.com should be rejected");
}

#[tokio::test]
async fn ssrf_guard_allows_subdomain_of_allowed_domain() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_outbound_url(
        "https://www.example.com/data",
        &["example.com".to_owned()],
    )
    .await;
    assert!(result.is_ok());
}

#[tokio::test]
async fn ssrf_guard_rejects_redirect_loop() {
    let result = ibreeze_desktop_core::security::ssrf_guard::validate_redirect_url(
        "https://example.com/a",
        "https://example.com/a",
        &[],
    )
    .await;
    assert!(result.is_err(), "redirect loop should be rejected");
}

#[tokio::test]
async fn egress_lease_url_validation() {
    let broker = ibreeze_desktop_core::security::egress::EgressBroker::new();
    let run_id = Uuid::new_v4();
    broker
        .create_lease(run_id, vec!["example.com".to_owned()])
        .await
        .expect("create lease");

    let result = broker
        .validate_url("https://www.example.com/v1/data", run_id)
        .await;
    assert!(result.is_ok(), "allowed domain should pass: {:?}", result);

    let result = broker.validate_url("https://evil.com/hack", run_id).await;
    assert!(result.is_err(), "disallowed domain should be rejected");

    let result = broker.validate_url("http://10.0.0.1/private", run_id).await;
    assert!(
        result.is_err(),
        "private IP should be rejected even without domain check"
    );
}

#[tokio::test]
async fn egress_lease_url_validation_rejects_invalid_lease() {
    let broker = ibreeze_desktop_core::security::egress::EgressBroker::new();
    let unknown_run = Uuid::new_v4();
    let result = broker
        .validate_url("https://example.com", unknown_run)
        .await;
    assert!(result.is_err(), "unknown run should fail");
}

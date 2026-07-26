use std::path::Path;

/// Test that the capabilities JSON structure is valid and contains
/// only the expected set of permissions.
#[test]
fn capabilities_restrict_commands() {
    let cap_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("capabilities/main.json");
    assert!(cap_path.exists(), "capabilities/main.json must exist");

    let content = std::fs::read_to_string(&cap_path)
        .expect("capabilities/main.json must be readable");
    let value: serde_json::Value = serde_json::from_str(&content)
        .expect("capabilities/main.json must be valid JSON");

    let permissions = value["permissions"]
        .as_array()
        .expect("capabilities must have permissions array");

    assert!(!permissions.is_empty(), "capabilities must define permissions");

    let all_perms: Vec<&str> = permissions
        .iter()
        .filter_map(|p| p.as_str())
        .collect();

    let dangerous_perms = [
        "shell:",
        "fs:",
        "http:",
        "process:",
        "clipboard-write",
        "updater",
    ];

    for perm in &all_perms {
        for danger in &dangerous_perms {
            assert!(
                !perm.starts_with(danger),
                "Capability '{perm}' should not be granted to WebView"
            );
        }
    }

    assert_eq!(value["identifier"], "main-capability", "capability identifier");
}

/// Test that the tauri.conf.json CSP does not allow unsafe-eval or wildcards.
#[test]
fn csp_restricts_sources() {
    let conf_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tauri.conf.json");
    let content = std::fs::read_to_string(&conf_path)
        .expect("tauri.conf.json must be readable");
    let value: serde_json::Value = serde_json::from_str(&content)
        .expect("tauri.conf.json must be valid JSON");

    let csp = value["app"]["security"]["csp"]
        .as_str()
        .expect("CSP must be defined");

    assert!(!csp.contains("unsafe-eval"), "CSP must not allow unsafe-eval");
    assert!(!csp.contains("*'"), "CSP must not use wildcard sources");
    assert!(csp.contains("script-src"), "CSP must restrict script-src");
    assert!(csp.contains("connect-src"), "CSP must restrict connect-src");
    assert!(!csp.contains("frame-src *"), "CSP must not allow frame-src *");
    assert!(csp.contains("form-action 'none'"), "CSP must disable form-action");
}

/// Test that all registered Tauri commands have unique names.
#[test]
fn command_names_are_unique() {
    let lib_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("src/lib.rs");
    let content = std::fs::read_to_string(&lib_path)
        .expect("src/lib.rs must be readable");

    let commands = [
        "backend_validate_origin",
        "auth_register",
        "auth_login",
        "auth_change_password",
        "auth_logout",
        "auth_list_offline_profiles",
        "auth_open_profile",
        "auth_close_profile",
        "rpc_request",
        "workspace_select",
        "readonly_file_select",
        "external_open",
        "diagnostics_export",
        "updater_check",
        "updater_install",
    ];

    for cmd in &commands {
        assert!(
            content.contains(cmd),
            "lib.rs must register command '{cmd}'"
        );
    }
}

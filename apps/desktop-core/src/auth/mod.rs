//! Backend authentication client, token refresh, and login state machine.
//!
//! This module will contain:
//! - backend_client.rs — reqwest-based hardened Backend REST client
//! - refresh.rs      — Token refresh with rotation
//! - login.rs        — Login state machine
//! - local_rpc.rs    — Rust-native methods that don't enter UDS
//! - catalog_client.rs — Catalog download and manifest verification
//!
//! # Security
//! - Access Token only in Rust memory, zeroized on request completion
//! - Refresh/Offline bundle only in Keychain, never in WebView, DB or logs
//! - Error responses mapped by Problem Details code, not by message text

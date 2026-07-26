//! UDS framing, authenticated JSON-RPC 2.0 client, handshake, and router.
//!
//! This module will contain:
//! - framing.rs   — 4-byte big-endian length-prefixed frames, 16 MiB limit
//! - client.rs    — Unix Domain Socket client with connection management
//! - handshake.rs — HMAC startup-token proof verification
//! - router.rs    — Method ownership dispatch (rust_core / sidecar / supervisor_only)
//! - reverse/     — Sidecar-to-Rust reverse RPC handlers
//!
//! # Frame protocol
//! - 4 bytes big-endian u32 length prefix
//! - UTF-8 JSON-RPC 2.0 body, single object only
//! - No batch requests, no top-level arrays
//! - Max 16 MiB per frame

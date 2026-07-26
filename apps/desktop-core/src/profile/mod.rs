//! Profile discovery, directory layout, and metadata management.
//!
//! This module will contain:
//! - origin.rs   — Canonical origin normalization
//! - metadata.rs — ProfileMeta atomic read/write
//! - layout.rs   — Directory layout verification and creation
//! - open.rs     — Profile open sequence (online + offline)
//!
//! `profile_directory_id = lowercase-base32(SHA-256(canonical_origin || 0x00 || app_user_id))`
//! - Never truncated
//! - Caller cannot provide directory name

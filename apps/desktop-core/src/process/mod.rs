//! Sidecar and CLI subprocess supervision.
//!
//! This module will contain:
//! - sidecar.rs  — Sidecar lifecycle, heartbeat monitoring, restart limiter
//! - registry.rs — Process group registry with PID/PGID/start time tracking
//! - signals.rs  — Graceful shutdown, SIGTERM → SIGKILL escalation
//!
//! # Restart policy
//! - Max 3 restarts in 60-second sliding window
//! - 4th consecutive failure enters diagnostics mode
//! - Heartbeat: 5s interval, 3s timeout, 3 consecutive lost → restart

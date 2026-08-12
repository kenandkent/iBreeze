use std::fmt;

/// Errors returned by the Rust reverse-handler table.  The authenticated
/// JSON-RPC transport itself is implemented by `rpc::sidecar::SidecarClient`;
/// this type is intentionally independent of any second multiplexer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IpcError {
    Backpressure,
    ConnectionLost,
    DeadlineExceeded,
    MethodNotAllowed,
    Internal(String),
}

impl fmt::Display for IpcError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Backpressure => write!(formatter, "IPC_BACKPRESSURE"),
            Self::ConnectionLost => write!(formatter, "IPC_CONNECTION_LOST"),
            Self::DeadlineExceeded => write!(formatter, "IPC_DEADLINE_EXCEEDED"),
            Self::MethodNotAllowed => write!(formatter, "METHOD_NOT_ALLOWED"),
            Self::Internal(message) => write!(formatter, "IPC_INTERNAL: {message}"),
        }
    }
}

impl std::error::Error for IpcError {}

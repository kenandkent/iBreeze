pub mod dispatcher;
pub mod frame;
pub mod multiplexer;
pub mod session;

pub use dispatcher::{handle_frame, GeneratedDispatcher, ReverseMethodTable};
pub use frame::{decode_frame, encode_frame, read_frame, write_frame, FrameError, MAX_FRAME_BYTES};
pub use multiplexer::{IpcError, Multiplexer, MAX_PENDING_PER_DIRECTION, MAX_STREAM_BUFFER_FRAMES};
pub use session::{IpcSession, IpcSessionMeta, HEARTBEAT_INTERVAL, MAX_MISSED_HEARTBEATS};

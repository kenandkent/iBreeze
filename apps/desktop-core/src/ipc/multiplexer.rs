use std::collections::HashMap;
use std::time::Duration;

use serde_json::Value;
use tokio::sync::{mpsc, oneshot};
use tokio::time::{timeout_at, Instant};
use uuid::Uuid;

use super::frame::encode_frame;

pub type RpcId = String;

pub const MAX_PENDING_PER_DIRECTION: usize = 256;
pub const MAX_STREAM_BUFFER_FRAMES: usize = 64;
pub const SEND_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IpcError {
    Backpressure,
    ConnectionLost,
    DeadlineExceeded,
    MethodNotAllowed,
    Internal(String),
}

impl std::fmt::Display for IpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            IpcError::Backpressure => write!(f, "IPC_BACKPRESSURE"),
            IpcError::ConnectionLost => write!(f, "IPC_CONNECTION_LOST"),
            IpcError::DeadlineExceeded => write!(f, "IPC_DEADLINE_EXCEEDED"),
            IpcError::MethodNotAllowed => write!(f, "METHOD_NOT_ALLOWED"),
            IpcError::Internal(msg) => write!(f, "IPC_INTERNAL: {msg}"),
        }
    }
}

impl std::error::Error for IpcError {}

pub struct PendingRequest {
    pub deadline: Instant,
    pub response_tx: oneshot::Sender<Result<Value, IpcError>>,
    pub cancel_tx: tokio::sync::watch::Sender<bool>,
}

pub struct ActiveStream {
    pub next_sequence: u64,
    pub stream_tx: mpsc::Sender<Value>,
}

pub struct Multiplexer {
    generation: u64,
    pending: HashMap<RpcId, PendingRequest>,
    streams: HashMap<Uuid, ActiveStream>,
    #[allow(clippy::type_complexity)]
    writer: mpsc::UnboundedSender<(Vec<u8>, oneshot::Sender<Result<(), IpcError>>)>,
}

impl Multiplexer {
    #[allow(clippy::type_complexity)]
    pub fn new(
        writer: mpsc::UnboundedSender<(Vec<u8>, oneshot::Sender<Result<(), IpcError>>)>,
    ) -> Self {
        Self {
            generation: 0,
            pending: HashMap::new(),
            streams: HashMap::new(),
            writer,
        }
    }

    pub fn generation(&self) -> u64 {
        self.generation
    }

    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    pub fn stream_count(&self) -> usize {
        self.streams.len()
    }

    pub fn register_pending(
        &mut self,
        id: RpcId,
        deadline: Instant,
    ) -> Result<oneshot::Receiver<Result<Value, IpcError>>, IpcError> {
        if self.pending.len() >= MAX_PENDING_PER_DIRECTION {
            return Err(IpcError::Backpressure);
        }
        let (tx, rx) = oneshot::channel();
        let (cancel_tx, _) = tokio::sync::watch::channel(false);
        self.pending.insert(
            id,
            PendingRequest {
                deadline,
                response_tx: tx,
                cancel_tx,
            },
        );
        Ok(rx)
    }

    pub fn resolve_pending(&mut self, id: &RpcId, result: Result<Value, IpcError>) {
        if let Some(req) = self.pending.remove(id) {
            let _ = req.response_tx.send(result);
        }
    }

    pub fn cancel_pending(&mut self, id: &RpcId) {
        if let Some(req) = self.pending.remove(id) {
            let _ = req.response_tx.send(Err(IpcError::ConnectionLost));
        }
    }

    pub fn register_stream(&mut self, request_id: Uuid) -> Result<mpsc::Receiver<Value>, IpcError> {
        if self.streams.len() >= MAX_PENDING_PER_DIRECTION {
            return Err(IpcError::Backpressure);
        }
        let (tx, rx) = mpsc::channel(MAX_STREAM_BUFFER_FRAMES);
        self.streams.insert(
            request_id,
            ActiveStream {
                next_sequence: 1,
                stream_tx: tx,
            },
        );
        Ok(rx)
    }

    pub fn push_stream_frame(&mut self, request_id: &Uuid, value: Value) -> Result<(), IpcError> {
        let stream = self
            .streams
            .get_mut(request_id)
            .ok_or(IpcError::ConnectionLost)?;
        stream
            .stream_tx
            .try_send(value)
            .map_err(|_| IpcError::Backpressure)
    }

    pub fn close_stream(&mut self, request_id: &Uuid) {
        self.streams.remove(request_id);
    }

    pub fn cancel_all(&mut self, err: IpcError) {
        for (_, req) in self.pending.drain() {
            let _ = req.response_tx.send(Err(err.clone()));
            let _ = req.cancel_tx.send(true);
        }
        for (_, stream) in self.streams.drain() {
            drop(stream.stream_tx);
        }
    }

    pub fn bump_generation(&mut self) -> u64 {
        self.generation += 1;
        self.cancel_all(IpcError::ConnectionLost);
        self.generation
    }

    pub async fn send_frame(&self, frame: Vec<u8>) -> Result<(), IpcError> {
        let (tx, rx) = oneshot::channel();
        self.writer
            .send((frame, tx))
            .map_err(|_| IpcError::ConnectionLost)?;
        timeout_at(Instant::now() + SEND_TIMEOUT, rx)
            .await
            .ok()
            .and_then(|r| r.ok())
            .unwrap_or(Err(IpcError::ConnectionLost))
    }

    pub async fn send_json(&self, obj: &Value) -> Result<(), IpcError> {
        let frame = encode_frame(obj).map_err(|e| IpcError::Internal(e.to_string()))?;
        self.send_frame(frame).await
    }
}

pub struct MultiplexerPair {
    pub core: Multiplexer,
    pub sidecar: Multiplexer,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pending_count_limits() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut mux = Multiplexer::new(tx);
        for i in 0..MAX_PENDING_PER_DIRECTION {
            let result = mux.register_pending(
                format!("core:{i}"),
                Instant::now() + Duration::from_secs(30),
            );
            assert!(result.is_ok(), "failed at {i}");
        }
        assert_eq!(mux.pending_count(), MAX_PENDING_PER_DIRECTION);
        assert!(matches!(
            mux.register_pending(
                "core:extra".to_owned(),
                Instant::now() + Duration::from_secs(30)
            ),
            Err(IpcError::Backpressure)
        ));
    }

    #[test]
    fn stream_count_limits() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut mux = Multiplexer::new(tx);
        for i in 0..MAX_PENDING_PER_DIRECTION {
            let id = Uuid::from_u128(i as u128);
            assert!(mux.register_stream(id).is_ok());
        }
        assert!(matches!(
            mux.register_stream(Uuid::new_v4()),
            Err(IpcError::Backpressure)
        ));
    }

    #[test]
    fn generation_bump_cancels_all() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut mux = Multiplexer::new(tx);
        let mut rx = mux
            .register_pending(
                "core:test".to_owned(),
                Instant::now() + Duration::from_secs(30),
            )
            .unwrap();
        let stream_id = Uuid::new_v4();
        assert!(mux.register_stream(stream_id).is_ok());
        let gen = mux.bump_generation();
        assert_eq!(gen, 1);
        assert_eq!(mux.pending_count(), 0);
        assert_eq!(mux.stream_count(), 0);
        assert!(rx.try_recv().unwrap().is_err());
    }

    #[test]
    fn resolve_pending_delivers_response() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut mux = Multiplexer::new(tx);
        let mut rx = mux
            .register_pending(
                "core:test".to_owned(),
                Instant::now() + Duration::from_secs(30),
            )
            .unwrap();
        let response = serde_json::json!({"result": "ok"});
        mux.resolve_pending(&"core:test".to_owned(), Ok(response.clone()));
        let delivered = rx.try_recv().unwrap().unwrap();
        assert_eq!(delivered, response);
    }

    #[test]
    fn push_stream_frame_roundtrip() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut mux = Multiplexer::new(tx);
        let stream_id = Uuid::new_v4();
        let mut stream_rx = mux.register_stream(stream_id).unwrap();
        let frame = serde_json::json!({"sequence": 1, "event": "output_text_delta"});
        mux.push_stream_frame(&stream_id, frame.clone()).unwrap();
        let received = stream_rx.try_recv().unwrap();
        assert_eq!(received, frame);
    }

    #[test]
    fn close_stream_removes_it() {
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut mux = Multiplexer::new(tx);
        let stream_id = Uuid::new_v4();
        assert!(mux.register_stream(stream_id).is_ok());
        assert_eq!(mux.stream_count(), 1);
        mux.close_stream(&stream_id);
        assert_eq!(mux.stream_count(), 0);
    }
}

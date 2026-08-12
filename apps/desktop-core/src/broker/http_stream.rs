use std::collections::HashMap;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::{mpsc, RwLock};
use uuid::Uuid;

use crate::error::AppError;

/// A subscriber is deliberately bounded.  A provider that produces data
/// faster than the authenticated IPC consumer can drain it must fail closed
/// instead of allowing an unbounded allocation in the desktop process.
pub const STREAM_SUBSCRIBER_CAPACITY: usize = 64;
pub const MAX_STREAM_HISTORY: usize = 4096;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BrokerEventKind {
    #[serde(rename = "output_text_delta")]
    OutputTextDelta,
    #[serde(rename = "tool_call_delta")]
    ToolCallDelta,
    #[serde(rename = "usage")]
    Usage,
    #[serde(rename = "completed")]
    Completed,
    #[serde(rename = "failed")]
    Failed,
}

impl BrokerEventKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            BrokerEventKind::OutputTextDelta => "output_text_delta",
            BrokerEventKind::ToolCallDelta => "tool_call_delta",
            BrokerEventKind::Usage => "usage",
            BrokerEventKind::Completed => "completed",
            BrokerEventKind::Failed => "failed",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrokerEvent {
    pub request_id: Uuid,
    pub sequence: u64,
    pub event: BrokerEventKind,
    pub payload: Value,
    pub received_at: DateTime<Utc>,
}

struct StreamState {
    next_sequence: u64,
    events: Vec<BrokerEvent>,
    completed: bool,
    subscribers: Vec<mpsc::Sender<BrokerEvent>>,
}

pub struct HttpStreamManager {
    streams: RwLock<HashMap<Uuid, StreamState>>,
}

impl HttpStreamManager {
    pub fn new() -> Self {
        Self {
            streams: RwLock::new(HashMap::new()),
        }
    }

    pub async fn create_stream(&self, request_id: Uuid) {
        let mut streams = self.streams.write().await;
        streams.insert(
            request_id,
            StreamState {
                next_sequence: 1,
                events: Vec::new(),
                completed: false,
                subscribers: Vec::new(),
            },
        );
    }

    pub async fn subscribe(
        &self,
        request_id: Uuid,
    ) -> Result<mpsc::Receiver<BrokerEvent>, AppError> {
        let mut streams = self.streams.write().await;
        let state = streams
            .get_mut(&request_id)
            .ok_or_else(|| AppError::NotFound("Stream not found".to_owned()))?;
        if state.events.len() > STREAM_SUBSCRIBER_CAPACITY {
            return Err(AppError::Sidecar("IPC_BACKPRESSURE".to_owned()));
        }
        let (tx, rx) = mpsc::channel(STREAM_SUBSCRIBER_CAPACITY);

        for event in &state.events {
            tx.try_send(event.clone())
                .map_err(|_| AppError::Sidecar("IPC_BACKPRESSURE".to_owned()))?;
        }

        if state.completed {
            drop(tx);
            return Ok(rx);
        }

        state.subscribers.push(tx);
        Ok(rx)
    }

    pub fn push_event(
        &self,
        request_id: Uuid,
        event: BrokerEventKind,
        payload: Value,
    ) -> Result<(), AppError> {
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current()
                .block_on(self.push_event_async(request_id, event, payload))
        })
    }

    pub async fn push_event_async(
        &self,
        request_id: Uuid,
        event: BrokerEventKind,
        payload: Value,
    ) -> Result<(), AppError> {
        let mut streams = self.streams.write().await;
        let state = streams
            .get_mut(&request_id)
            .ok_or_else(|| AppError::NotFound("Stream not found".to_owned()))?;
        if state.completed {
            return Ok(());
        }
        if state.events.len() >= MAX_STREAM_HISTORY {
            state.completed = true;
            state.subscribers.clear();
            return Err(AppError::Sidecar("IPC_BACKPRESSURE".to_owned()));
        }

        let broker_event = BrokerEvent {
            request_id,
            sequence: state.next_sequence,
            event,
            payload,
            received_at: Utc::now(),
        };
        for subscriber in &state.subscribers {
            if subscriber.try_send(broker_event.clone()).is_err() {
                state.completed = true;
                state.subscribers.clear();
                return Err(AppError::Sidecar("IPC_BACKPRESSURE".to_owned()));
            }
        }
        state.next_sequence += 1;
        state.events.push(broker_event);
        Ok(())
    }

    pub async fn get_events(&self, request_id: Uuid) -> Result<Vec<BrokerEvent>, AppError> {
        let streams = self.streams.read().await;
        let state = streams
            .get(&request_id)
            .ok_or_else(|| AppError::NotFound("Stream not found".to_owned()))?;
        Ok(state.events.clone())
    }

    pub fn complete(&self, request_id: Uuid) {
        let mut streams = tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(self.streams.write())
        });
        if let Some(state) = streams.get_mut(&request_id) {
            state.completed = true;
            state.subscribers.clear();
        }
    }

    pub async fn complete_async(&self, request_id: Uuid) {
        let mut streams = self.streams.write().await;
        if let Some(state) = streams.get_mut(&request_id) {
            state.completed = true;
            state.subscribers.clear();
        }
    }

    pub async fn is_completed(&self, request_id: Uuid) -> bool {
        let streams = self.streams.read().await;
        streams.get(&request_id).is_none_or(|s| s.completed)
    }

    pub async fn drop_stream(&self, request_id: Uuid) {
        let mut streams = self.streams.write().await;
        streams.remove(&request_id);
    }

    pub async fn active_count(&self) -> usize {
        self.streams.read().await.len()
    }
}

impl Default for HttpStreamManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn create_and_get_events() {
        let manager = HttpStreamManager::new();
        let request_id = Uuid::new_v4();
        manager.create_stream(request_id).await;

        manager
            .push_event_async(
                request_id,
                BrokerEventKind::OutputTextDelta,
                serde_json::json!({"text": "Hello"}),
            )
            .await
            .unwrap();
        manager
            .push_event_async(
                request_id,
                BrokerEventKind::Completed,
                serde_json::json!({"status": "ok"}),
            )
            .await
            .unwrap();

        let events = manager.get_events(request_id).await.unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].sequence, 1);
        assert_eq!(events[0].event, BrokerEventKind::OutputTextDelta);
        assert_eq!(events[1].sequence, 2);
        assert_eq!(events[1].event, BrokerEventKind::Completed);
    }

    #[tokio::test]
    async fn subscribe_receives_events() {
        let manager = HttpStreamManager::new();
        let request_id = Uuid::new_v4();
        manager.create_stream(request_id).await;
        let mut rx = manager.subscribe(request_id).await.unwrap();

        manager
            .push_event_async(
                request_id,
                BrokerEventKind::Usage,
                serde_json::json!({"tokens": 10}),
            )
            .await
            .unwrap();

        let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(event.event, BrokerEventKind::Usage);
    }

    #[tokio::test]
    async fn complete_marks_stream_finished() {
        let manager = HttpStreamManager::new();
        let request_id = Uuid::new_v4();
        manager.create_stream(request_id).await;
        assert!(!manager.is_completed(request_id).await);
        manager.complete_async(request_id).await;
        assert!(manager.is_completed(request_id).await);
    }

    #[tokio::test]
    async fn drop_stream_removes_it() {
        let manager = HttpStreamManager::new();
        let request_id = Uuid::new_v4();
        manager.create_stream(request_id).await;
        assert_eq!(manager.active_count().await, 1);
        manager.drop_stream(request_id).await;
        assert_eq!(manager.active_count().await, 0);
    }

    #[tokio::test]
    async fn subscribe_receives_past_events() {
        let manager = HttpStreamManager::new();
        let request_id = Uuid::new_v4();
        manager.create_stream(request_id).await;

        manager
            .push_event_async(
                request_id,
                BrokerEventKind::OutputTextDelta,
                serde_json::json!({"text": "past"}),
            )
            .await
            .unwrap();

        let mut rx = manager.subscribe(request_id).await.unwrap();
        let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(event.payload["text"], "past");
    }

    #[test]
    fn broker_event_kind_as_str() {
        assert_eq!(
            BrokerEventKind::OutputTextDelta.as_str(),
            "output_text_delta"
        );
        assert_eq!(BrokerEventKind::ToolCallDelta.as_str(), "tool_call_delta");
        assert_eq!(BrokerEventKind::Usage.as_str(), "usage");
        assert_eq!(BrokerEventKind::Completed.as_str(), "completed");
        assert_eq!(BrokerEventKind::Failed.as_str(), "failed");
    }
}

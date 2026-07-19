use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::time::Duration;

use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct RpcRequest {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub id: String,
    pub method: String,
    pub params: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RpcResponse {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub id: String,
    pub result: Option<serde_json::Value>,
    pub error: Option<serde_json::Value>,
}

pub struct RpcClient {
    socket_path: String,
}

impl RpcClient {
    pub fn new(socket_path: &str) -> Self {
        Self {
            socket_path: socket_path.to_string(),
        }
    }

    pub async fn call(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        let socket_path = self.socket_path.clone();
        let method = method.to_string();
        let id = uuid_simple();

        tokio::task::spawn_blocking(move || {
            let stream = UnixStream::connect(&socket_path)
                .map_err(|e| format!("Failed to connect to {}: {}", socket_path, e))?;

            stream
                .set_read_timeout(Some(Duration::from_secs(10)))
                .map_err(|e| e.to_string())?;

            let mut stream_clone =
                stream.try_clone().map_err(|e| format!("Failed to clone stream: {}", e))?;

            let request = RpcRequest {
                msg_type: "request".to_string(),
                id: id.clone(),
                method,
                params,
            };

            let mut msg = serde_json::to_string(&request).map_err(|e| e.to_string())?;
            msg.push('\n');

            stream_clone
                .write_all(msg.as_bytes())
                .map_err(|e| format!("Failed to send request: {}", e))?;

            let mut reader = BufReader::new(&stream);
            let mut response_line = String::new();
            reader
                .read_line(&mut response_line)
                .map_err(|e| format!("Failed to read response: {}", e))?;

            let response: RpcResponse = serde_json::from_str(response_line.trim())
                .map_err(|e| format!("Failed to parse response: {}", e))?;

            if let Some(err) = response.error {
                let msg = if let Some(s) = err.as_str() {
                    s.to_string()
                } else {
                    err.to_string()
                };
                return Err(msg);
            }

            Ok(response.result.unwrap_or(serde_json::Value::Null))
        })
        .await
        .map_err(|e| format!("Task join error: {}", e))?
    }
}

fn uuid_simple() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    format!("{:032x}", t)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::net::UnixListener;
    use std::thread;

    #[test]
    fn test_rpc_client_sys_health() {
        let dir = tempfile::tempdir().unwrap();
        let socket_path = dir.path().join("test.sock");
        let socket_str = socket_path.to_str().unwrap().to_string();

        let listener = UnixListener::bind(&socket_path).unwrap();

        let handle = thread::spawn(move || {
            let (stream, _) = listener.accept().unwrap();
            let mut reader = BufReader::new(&stream);
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();

            let request: RpcRequest = serde_json::from_str(line.trim()).unwrap();
            assert_eq!(request.method, "sys.health");

            let response = RpcResponse {
                msg_type: "response".to_string(),
                id: request.id,
                result: Some(serde_json::json!({
                    "status": "healthy",
                    "components": {"rpc": "up"}
                })),
                error: None,
            };

            let mut writer = reader.into_inner();
            let mut resp = serde_json::to_string(&response).unwrap();
            resp.push('\n');
            writer.write_all(resp.as_bytes()).unwrap();
        });

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(async {
            let client = RpcClient::new(&socket_str);
            client
                .call("sys.health", serde_json::json!({}))
                .await
                .unwrap()
        });

        assert_eq!(result["status"], "healthy");
        assert_eq!(result["components"]["rpc"], "up");

        handle.join().unwrap();
    }
}

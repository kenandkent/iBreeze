use std::sync::Arc;
use std::time::{Duration, Instant};

use base64::Engine;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::RwLock;
use tracing::{error, info, warn};

use crate::broker::egress::EgressBroker;
use crate::error::AppError;

pub const MAX_CONCURRENT_TUNNELS: usize = 32;
pub const MAX_TUNNEL_RATE_PER_MINUTE: u32 = 60;
pub const IDLE_TUNNEL_TIMEOUT: Duration = Duration::from_secs(120);
pub const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const MAX_HEADER_SIZE: usize = 16 * 1024;
pub const MAX_SINGLE_HEADER_SIZE: usize = 8 * 1024;

struct TunnelMetrics {
    minute_start: Instant,
    tunnels_this_minute: u32,
}

pub struct ConnectHandler {
    egress_broker: Arc<EgressBroker>,
    metrics: RwLock<TunnelMetrics>,
}

impl ConnectHandler {
    pub fn new(egress_broker: Arc<EgressBroker>) -> Self {
        Self {
            egress_broker,
            metrics: RwLock::new(TunnelMetrics {
                minute_start: Instant::now(),
                tunnels_this_minute: 0,
            }),
        }
    }

    pub async fn handle_connect(
        &self,
        stream: &mut TcpStream,
        peer_addr: std::net::SocketAddr,
    ) -> Result<(), AppError> {
        let mut buffer = vec![0u8; MAX_HEADER_SIZE];
        let mut total_read = 0;

        loop {
            if total_read >= MAX_HEADER_SIZE {
                Self::send_response(stream, "400", "Bad Request: headers too large").await?;
                return Err(AppError::Validation("Headers too large".to_owned()));
            }
            let n = stream
                .read(&mut buffer[total_read..])
                .await
                .map_err(|e| {
                    error!("read connect headers: {e}");
                    AppError::Network("CONNECT header read failed".to_owned())
                })?;
            if n == 0 {
                return Err(AppError::Network("Connection closed".to_owned()));
            }
            total_read += n;

            if let Some(pos) = buffer[..total_read].windows(4).position(|w| w == b"\r\n\r\n") {
                let header_bytes = &buffer[..pos + 4];

                let request_line_end = header_bytes
                    .windows(2)
                    .position(|w| w == b"\r\n")
                    .unwrap_or(header_bytes.len());
                let request_line =
                    std::str::from_utf8(&header_bytes[..request_line_end]).map_err(|_| {
                        AppError::Validation("Invalid UTF-8 in request line".to_owned())
                    })?;

                let parts: Vec<&str> = request_line.split(' ').collect();
                if parts.len() < 3 || parts[0] != "CONNECT" {
                    Self::send_response(stream, "405", "Method Not Allowed").await?;
                    return Err(AppError::Validation("Only CONNECT method allowed".to_owned()));
                }

                let authority = parts[1];
                let host_port: Vec<&str> = authority.split(':').collect();
                if host_port.len() != 2 {
                    Self::send_response(stream, "400", "Bad Request: invalid authority").await?;
                    return Err(AppError::Validation("Invalid authority".to_owned()));
                }

                let host = host_port[0].to_ascii_lowercase();
                let port: u16 = host_port[1].parse().map_err(|_| {
                    AppError::Validation("Invalid port".to_owned())
                })?;

                if port != 443 {
                    Self::send_response(stream, "403", "Forbidden: only port 443 allowed").await?;
                    return Err(AppError::Validation("Only port 443 allowed".to_owned()));
                }

                let headers = std::str::from_utf8(header_bytes).map_err(|_| {
                    AppError::Validation("Invalid UTF-8 in headers".to_owned())
                })?;

                let token = Self::extract_proxy_authorization(headers)
                    .ok_or_else(|| {
                        AppError::Unauthorized("Missing Proxy-Authorization".to_owned())
                    })?;

                let rate_ok = {
                    let mut metrics = self.metrics.write().await;
                    let now = Instant::now();
                    if now.duration_since(metrics.minute_start) >= Duration::from_secs(60) {
                        metrics.minute_start = now;
                        metrics.tunnels_this_minute = 0;
                    }
                    metrics.tunnels_this_minute += 1;
                    if metrics.tunnels_this_minute > MAX_TUNNEL_RATE_PER_MINUTE {
                        warn!("tunnel rate limit exceeded from {peer_addr}");
                        false
                    } else {
                        true
                    }
                };

                if !rate_ok {
                    Self::send_response(stream, "429", "Too Many Requests").await?;
                    return Err(AppError::Validation("Rate limit exceeded".to_owned()));
                }

                let lease = match self.egress_broker.validate_token_by_port(port, &token).await {
                    Ok(l) => l,
                    Err(_) => {
                        Self::send_response(stream, "407", "Proxy Authentication Required").await?;
                        return Err(AppError::Unauthorized("Invalid token".to_owned()));
                    }
                };

                let is_allowed = lease
                    .allowed_domains
                    .iter()
                    .any(|d| crate::broker::domain_policy::matches_domain(&host, d.as_str()));

                if !is_allowed {
                    Self::send_response(stream, "403", "Forbidden: domain not allowed").await?;
                    return Err(AppError::Security(format!("Domain not allowed: {host}")));
                }

                let remote = format!("{host}:{port}");
                Self::send_response(stream, "200", "Connection established").await?;
                stream.flush().await.ok();

                let mut remote_stream = tokio::time::timeout(
                    CONNECT_TIMEOUT,
                    TcpStream::connect(&remote),
                )
                .await
                .map_err(|_| AppError::Network("Connect timeout".to_owned()))?
                .map_err(|e| AppError::Network(format!("Connect failed: {e}")))?;

                info!(%host, port, "CONNECT tunnel established");

                let (mut ri, mut wi) = stream.split();
                let (mut rj, mut wj) = remote_stream.split();

                let client_to_remote = tokio::io::copy(&mut ri, &mut wj);
                let remote_to_client = tokio::io::copy(&mut rj, &mut wi);

                tokio::select! {
                    result = client_to_remote => {
                        if let Err(e) = result {
                            warn!("client->remote copy: {e}");
                        }
                    }
                    result = remote_to_client => {
                        if let Err(e) = result {
                            warn!("remote->client copy: {e}");
                        }
                    }
                }

                info!(%host, port, "CONNECT tunnel closed");
                return Ok(());
            }
        }
    }

    fn extract_proxy_authorization(headers: &str) -> Option<String> {
        for line in headers.lines() {
            if line.to_ascii_lowercase().starts_with("proxy-authorization:") {
                if let Some(value) = line.splitn(2, ':').nth(1) {
                    let value = value.trim();
                    if let Some(basic) = value.strip_prefix("Basic ") {
                        let decoded = base64::engine::general_purpose::STANDARD
                            .decode(basic)
                            .ok()?;
                        let decoded_str = std::str::from_utf8(&decoded).ok()?;
                        if let Some(token) = decoded_str.split(':').nth(1) {
                            return Some(token.to_owned());
                        }
                    }
                }
            }
        }
        None
    }

    async fn send_response(
        stream: &mut TcpStream,
        status: &str,
        message: &str,
    ) -> Result<(), AppError> {
        let response = format!("HTTP/1.1 {status} {message}\r\n\r\n");
        stream
            .write_all(response.as_bytes())
            .await
            .map_err(|e| AppError::Network(format!("Failed to send response: {e}")))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_proxy_authorization_valid() {
        let headers = "CONNECT api.example.com:443 HTTP/1.1\r\nProxy-Authorization: Basic aWJyZWV6ZTp0b2tlbl9oZXJl\r\nHost: api.example.com\r\n\r\n";
        let token = ConnectHandler::extract_proxy_authorization(headers);
        assert!(token.is_some());
        assert_eq!(token.unwrap(), "token_here");
    }

    #[test]
    fn extract_proxy_authorization_missing() {
        let headers = "CONNECT api.example.com:443 HTTP/1.1\r\nHost: api.example.com\r\n\r\n";
        assert!(ConnectHandler::extract_proxy_authorization(headers).is_none());
    }

    #[test]
    fn extract_proxy_authorization_case_insensitive() {
        let headers = "CONNECT api.example.com:443 HTTP/1.1\r\nProxy-Authorization: Basic aWJyZWV6ZTpzZWNyZXQ=\r\nHost: api.example.com\r\n\r\n";
        let token = ConnectHandler::extract_proxy_authorization(headers);
        assert!(token.is_some());
        assert_eq!(token.unwrap(), "secret");
    }

    #[test]
    fn extract_proxy_authorization_wrong_scheme() {
        let headers = "CONNECT api.example.com:443 HTTP/1.1\r\nProxy-Authorization: Bearer token\r\n\r\n";
        assert!(ConnectHandler::extract_proxy_authorization(headers).is_none());
    }

    #[test]
    fn extract_proxy_authorization_invalid_base64() {
        let headers = "CONNECT api.example.com:443 HTTP/1.1\r\nProxy-Authorization: Basic not-valid-base64!!!\r\n\r\n";
        assert!(ConnectHandler::extract_proxy_authorization(headers).is_none());
    }
}

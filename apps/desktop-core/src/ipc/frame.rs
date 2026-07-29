use std::io;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};

pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, thiserror::Error)]
pub enum FrameError {
    #[error("Invalid frame length: {0}")]
    InvalidLength(u32),
    #[error("Frame too large: {0} bytes")]
    TooLarge(usize),
    #[error("Invalid UTF-8: {0}")]
    InvalidUtf8(#[from] std::str::Utf8Error),
    #[error("Top-level JSON value is not an object")]
    NotAnObject,
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("IO error: {0}")]
    Io(#[from] io::Error),
    #[error("Connection closed")]
    ConnectionClosed,
}

pub fn encode_frame(obj: &serde_json::Value) -> Result<Vec<u8>, FrameError> {
    if !obj.is_object() {
        return Err(FrameError::NotAnObject);
    }
    let payload = serde_json::to_vec(obj)?;
    let len = payload.len();
    if len == 0 {
        return Err(FrameError::InvalidLength(0));
    }
    if len > MAX_FRAME_BYTES {
        return Err(FrameError::TooLarge(len));
    }
    let mut frame = Vec::with_capacity(4 + len);
    frame.extend_from_slice(&(len as u32).to_be_bytes());
    frame.extend_from_slice(&payload);
    Ok(frame)
}

pub fn decode_frame(data: &[u8]) -> Result<serde_json::Value, FrameError> {
    if data.len() < 4 {
        return Err(FrameError::InvalidLength(data.len() as u32));
    }
    let len = u32::from_be_bytes([data[0], data[1], data[2], data[3]]) as usize;
    if len == 0 {
        return Err(FrameError::InvalidLength(0));
    }
    if len > MAX_FRAME_BYTES {
        return Err(FrameError::TooLarge(len));
    }
    if data.len() < 4 + len {
        return Err(FrameError::InvalidLength(len as u32));
    }
    let body = &data[4..4 + len];
    let _ = std::str::from_utf8(body).map_err(FrameError::InvalidUtf8)?;
    let value: serde_json::Value = serde_json::from_slice(body)?;
    if !value.is_object() {
        return Err(FrameError::NotAnObject);
    }
    Ok(value)
}

pub async fn read_frame<R>(reader: &mut R) -> Result<serde_json::Value, FrameError>
where
    R: AsyncRead + Unpin,
{
    let mut header = [0u8; 4];
    if reader.read_exact(&mut header).await.is_err() {
        return Err(FrameError::ConnectionClosed);
    }
    let len = u32::from_be_bytes(header) as usize;
    if len == 0 {
        return Err(FrameError::InvalidLength(0));
    }
    if len > MAX_FRAME_BYTES {
        return Err(FrameError::TooLarge(len));
    }
    let mut body = vec![0u8; len];
    reader.read_exact(&mut body).await?;
    let _ = std::str::from_utf8(&body).map_err(FrameError::InvalidUtf8)?;
    let value: serde_json::Value = serde_json::from_slice(&body)?;
    if !value.is_object() {
        return Err(FrameError::NotAnObject);
    }
    Ok(value)
}

pub async fn write_frame<W>(writer: &mut W, obj: &serde_json::Value) -> Result<(), FrameError>
where
    W: AsyncWrite + Unpin,
{
    let frame = encode_frame(obj)?;
    writer.write_all(&frame).await?;
    writer.flush().await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_zero_length() {
        assert!(matches!(
            decode_frame(&[0, 0, 0, 0]),
            Err(FrameError::InvalidLength(0))
        ));
    }

    #[test]
    fn rejects_oversized() {
        let len = (MAX_FRAME_BYTES + 1) as u32;
        let mut header = len.to_be_bytes().to_vec();
        header.resize(4 + 1, 0);
        assert!(matches!(
            decode_frame(&header),
            Err(FrameError::TooLarge(_))
        ));
    }

    #[test]
    fn rejects_top_level_array() {
        let payload = b"[{}]";
        let mut frame = (payload.len() as u32).to_be_bytes().to_vec();
        frame.extend_from_slice(payload);
        assert!(matches!(decode_frame(&frame), Err(FrameError::NotAnObject)));
    }

    #[test]
    fn rejects_top_level_string() {
        let payload = b"\"hello\"";
        let mut frame = (payload.len() as u32).to_be_bytes().to_vec();
        frame.extend_from_slice(payload);
        assert!(matches!(decode_frame(&frame), Err(FrameError::NotAnObject)));
    }

    #[test]
    fn roundtrip_valid_object() {
        let obj = serde_json::json!({"method": "test", "id": "core:uuid"});
        let encoded = encode_frame(&obj).unwrap();
        let decoded = decode_frame(&encoded).unwrap();
        assert_eq!(obj, decoded);
    }

    #[test]
    fn encode_rejects_non_object() {
        assert!(matches!(
            encode_frame(&serde_json::Value::Array(vec![])),
            Err(FrameError::NotAnObject)
        ));
    }

    #[test]
    fn max_frame_boundary() {
        let large_val = serde_json::json!({"data": "x".repeat(MAX_FRAME_BYTES - 20)});
        let encoded = encode_frame(&large_val).unwrap();
        assert!(encoded.len() <= MAX_FRAME_BYTES + 4);
        let decoded = decode_frame(&encoded).unwrap();
        assert_eq!(decoded, large_val);
    }

    #[test]
    fn rejects_non_utf8() {
        let payload = vec![0xff, 0xfe, 0x00, 0x01];
        let len = payload.len() as u32;
        let mut frame = len.to_be_bytes().to_vec();
        frame.extend_from_slice(&payload);
        assert!(matches!(
            decode_frame(&frame),
            Err(FrameError::InvalidUtf8(_))
        ));
    }

    #[test]
    fn rejects_truncated_body() {
        let payload = b"{\"key\":";
        let len = 100u32; // lie about length
        let mut frame = len.to_be_bytes().to_vec();
        frame.extend_from_slice(payload);
        assert!(matches!(
            decode_frame(&frame),
            Err(FrameError::InvalidLength(_))
        ));
    }
}

use std::os::unix::net::UnixListener;
use std::thread;

use ibreeze_desktop_lib::rpc_client::RpcClient;

#[test]
fn test_rpc_client_sys_health() {
    let dir = tempfile::tempdir().unwrap();
    let socket_path = dir.path().join("test.sock");

    let listener = UnixListener::bind(&socket_path).unwrap();
    let socket_str = socket_path.to_str().unwrap().to_string();

    let handle = thread::spawn(move || {
        use std::io::{BufRead, BufReader, Write};

        let (stream, _) = listener.accept().unwrap();
        let mut reader = BufReader::new(&stream);
        let mut line = String::new();
        reader.read_line(&mut line).unwrap();

        let request: serde_json::Value = serde_json::from_str(line.trim()).unwrap();
        assert_eq!(request["method"], "sys.health");

        let response = serde_json::json!({
            "type": "response",
            "id": request["id"],
            "result": {
                "status": "healthy",
                "components": {"rpc": "up"}
            },
            "error": null
        });

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

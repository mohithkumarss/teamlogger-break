//! Minimal Chrome DevTools Protocol client — just enough to read TeamLogger's
//! window and press its buttons.
//!
//! Safety: it only ever talks to 127.0.0.1 (loopback). Page URLs that point
//! anywhere else are refused, so nothing here can reach another computer.

use serde_json::{json, Value};
use std::io::{Read, Write};
use std::net::{IpAddr, SocketAddr, TcpStream, ToSocketAddrs};
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
#[allow(dead_code)] // title/url: diagnostics and the mock-page safety check
pub struct Page {
    pub ws_url: String,
    pub title: String,
    pub url: String,
}

/// `GET path` on the local DevTools HTTP endpoint; returns the body.
pub fn http_get(port: u16, path: &str) -> Result<String, String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut s = TcpStream::connect_timeout(&addr, Duration::from_millis(400)).map_err(|e| e.to_string())?;
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = s.set_write_timeout(Some(Duration::from_millis(500)));
    // HTTP/1.1 + close: newer Chromium silently drops HTTP/1.0 requests
    s.write_all(format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n").as_bytes())
        .map_err(|e| e.to_string())?;
    let mut buf = Vec::new();
    let _ = s.take(4 * 1024 * 1024).read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    let (head, body) = text.split_once("\r\n\r\n").ok_or("no HTTP answer")?;
    let code = head.split_whitespace().nth(1).unwrap_or("");
    if !head.starts_with("HTTP/1.") || code != "200" {
        return Err(format!("HTTP {code}"));
    }
    Ok(body.to_string())
}

/// `ws://127.0.0.1:9333/devtools/page/…` → its socket address, only if it's loopback.
fn loopback_addr(ws_url: &str) -> Option<SocketAddr> {
    let rest = ws_url.strip_prefix("ws://")?;
    let hostport = rest.split('/').next()?;
    hostport.to_socket_addrs().ok()?.find(|a| match a.ip() {
        IpAddr::V4(ip) => ip.is_loopback(),
        IpAddr::V6(ip) => ip.is_loopback(),
    })
}

/// Pages (windows) of the app listening on `port`.
pub fn list_pages(port: u16) -> Result<Vec<Page>, String> {
    let v: Value = serde_json::from_str(&http_get(port, "/json/list")?).map_err(|e| e.to_string())?;
    Ok(v.as_array()
        .map(|a| a.as_slice())
        .unwrap_or_default()
        .iter()
        .filter(|p| p["type"] == "page")
        .filter_map(|p| {
            let ws = p["webSocketDebuggerUrl"].as_str()?;
            loopback_addr(ws)?;
            Some(Page {
                ws_url: ws.to_string(),
                title: p["title"].as_str().unwrap_or_default().to_string(),
                url: p["url"].as_str().unwrap_or_default().to_string(),
            })
        })
        .collect())
}

/// Run `expression` in the page and return its value (promises are awaited).
pub fn evaluate(ws_url: &str, expression: &str, timeout: Duration) -> Result<Value, String> {
    let addr = loopback_addr(ws_url).ok_or("refusing a non-local DevTools address")?;
    let stream = TcpStream::connect_timeout(&addr, Duration::from_millis(500)).map_err(|e| e.to_string())?;
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    let (mut ws, _) = tungstenite::client::client(ws_url, stream).map_err(|e| format!("websocket: {e}"))?;
    let msg = json!({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": { "expression": expression, "returnByValue": true, "awaitPromise": true }
    });
    ws.send(tungstenite::Message::Text(msg.to_string().into())).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + timeout;
    let result = loop {
        if Instant::now() > deadline {
            break Err("DevTools didn't answer in time".to_string());
        }
        match ws.read() {
            Ok(tungstenite::Message::Text(t)) => {
                let v: Value = serde_json::from_str(t.as_str()).map_err(|e| e.to_string())?;
                if v["id"] != 1 {
                    continue; // an event, not our answer
                }
                let r = &v["result"];
                if let Some(ex) = r.get("exceptionDetails") {
                    break Err(format!("script error: {}", ex["text"].as_str().unwrap_or("?")));
                }
                break Ok(r["result"]["value"].clone());
            }
            Ok(_) => continue,
            Err(e) => break Err(e.to_string()),
        }
    };
    let _ = ws.close(None);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_loopback_addresses_are_accepted() {
        assert!(loopback_addr("ws://127.0.0.1:9333/devtools/page/AB").is_some());
        assert!(loopback_addr("ws://[::1]:9333/devtools/page/AB").is_some());
        assert!(loopback_addr("ws://10.0.0.5:9333/devtools/page/AB").is_none());
        assert!(loopback_addr("ws://8.8.8.8:9333/x").is_none());
        assert!(loopback_addr("http://127.0.0.1:9333/x").is_none());
        assert!(evaluate("ws://10.0.0.5:9333/devtools/page/AB", "1", Duration::from_millis(100)).is_err());
    }

    #[test]
    fn http_get_reads_the_body() {
        use std::net::TcpListener;
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        let t = std::thread::spawn(move || {
            let (mut c, _) = l.accept().unwrap();
            let mut b = [0u8; 512];
            let _ = c.read(&mut b);
            c.write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n[{\"type\":\"page\",\"title\":\"T\",\"url\":\"file:///x\",\"webSocketDebuggerUrl\":\"ws://127.0.0.1:1/devtools/page/A\"},{\"type\":\"page\",\"webSocketDebuggerUrl\":\"ws://10.1.1.1:1/p\"},{\"type\":\"worker\",\"webSocketDebuggerUrl\":\"ws://127.0.0.1:1/w\"}]").unwrap();
        });
        let pages = list_pages(port).unwrap();
        t.join().unwrap();
        assert_eq!(pages.len(), 1, "non-local pages and non-pages are dropped");
        assert_eq!(pages[0].title, "T");
    }
}

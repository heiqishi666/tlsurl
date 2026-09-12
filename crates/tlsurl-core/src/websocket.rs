use std::{future::Future, time::Duration};

use futures_util::{
    SinkExt, StreamExt,
    stream::{SplitSink, SplitStream},
};
use serde::Deserialize;
use tokio::sync::Mutex;
use wreq::ws::{
    WebSocket as Socket, WebSocketRequestBuilder,
    message::{CloseFrame, Message},
};

use crate::{
    Client, Error, positive_ms,
    stream::{CancellationToken, cancellable},
};

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct WebSocketOptions {
    pub protocols: Vec<String>,
    pub timeout_ms: Option<u32>,
    pub operation_timeout_ms: Option<u32>,
    pub max_message_bytes: Option<u32>,
}

pub struct WebSocketMessage {
    pub kind: &'static str,
    pub data: Vec<u8>,
    pub code: Option<u16>,
}

pub struct WebSocket {
    pub protocol: Option<String>,
    tx: Mutex<Option<SplitSink<Socket, Message>>>,
    rx: Mutex<Option<SplitStream<Socket>>>,
    cancellation: CancellationToken,
    closing: CancellationToken,
    operation_timeout: Duration,
    max_message_bytes: usize,
}

// A Python task can drop its Rust future before the cancellation branch runs.
// The held resource must therefore also be cleared when its guard is dropped.
struct SocketGuard<'a, T> {
    slot: tokio::sync::MutexGuard<'a, Option<T>>,
    cancellation: &'a CancellationToken,
}
impl<T> std::ops::Deref for SocketGuard<'_, T> {
    type Target = Option<T>;
    fn deref(&self) -> &Self::Target {
        &self.slot
    }
}
impl<T> std::ops::DerefMut for SocketGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.slot
    }
}
impl<T> Drop for SocketGuard<'_, T> {
    fn drop(&mut self) {
        if self.cancellation.is_cancelled() {
            *self.slot = None;
        }
    }
}

fn closed() -> Error {
    Error {
        code: "CLOSED",
        message: "websocket is closed".into(),
    }
}
fn invalid(message: &str) -> Error {
    Error {
        code: "INVALID_REQUEST",
        message: message.into(),
    }
}

impl Client {
    pub async fn websocket(
        &self,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        options: WebSocketOptions,
    ) -> Result<WebSocket, Error> {
        let url = url::Url::parse(&url).map_err(|_| invalid("invalid websocket URL"))?;
        if !matches!(url.scheme(), "ws" | "wss") {
            return Err(invalid("expected ws or wss URL"));
        }
        for (index, protocol) in options.protocols.iter().enumerate() {
            if wreq::header::HeaderName::from_bytes(protocol.as_bytes()).is_err()
                || options.protocols[..index].contains(protocol)
            {
                return Err(invalid("invalid or duplicate websocket subprotocol"));
            }
        }
        let operation_timeout = positive_ms(options.operation_timeout_ms.unwrap_or(30000))?;
        let max_message_bytes = options.max_message_bytes.unwrap_or(16777216) as usize;
        if max_message_bytes == 0 {
            return Err(invalid("max_message_bytes must be positive"));
        }
        let mut request = self.inner.get(url.as_str());
        if let Some(timeout) = options.timeout_ms {
            request = request.timeout(positive_ms(timeout)?);
        }
        for (name, value) in headers {
            request = request.header(name, value);
        }
        let socket = WebSocketRequestBuilder::new(request)
            .protocols(options.protocols)
            .max_message_size(max_message_bytes)
            .max_frame_size(max_message_bytes)
            .write_buffer_size(0)
            .max_write_buffer_size(max_message_bytes.saturating_add(1024))
            .send()
            .await?
            .into_websocket()
            .await?;
        let protocol = socket
            .protocol()
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let (tx, rx) = socket.split();
        Ok(WebSocket {
            protocol,
            tx: Mutex::new(Some(tx)),
            rx: Mutex::new(Some(rx)),
            cancellation: CancellationToken::new(),
            closing: CancellationToken::new(),
            operation_timeout,
            max_message_bytes,
        })
    }
}

impl WebSocket {
    async fn sender(&self) -> SocketGuard<'_, SplitSink<Socket, Message>> {
        SocketGuard {
            slot: self.tx.lock().await,
            cancellation: &self.cancellation,
        }
    }
    async fn receiver(&self) -> SocketGuard<'_, SplitStream<Socket>> {
        SocketGuard {
            slot: self.rx.lock().await,
            cancellation: &self.cancellation,
        }
    }

    pub fn abort(&self) {
        self.cancellation.cancel();
        if let Ok(mut tx) = self.tx.try_lock() {
            *tx = None;
        }
        if let Ok(mut rx) = self.rx.try_lock() {
            *rx = None;
        }
    }

    async fn bounded<T>(&self, future: impl Future<Output = Result<T, Error>>) -> Result<T, Error> {
        cancellable(&self.cancellation, async {
            tokio::time::timeout(self.operation_timeout, future)
                .await
                .map_err(|_| Error {
                    code: "TIMEOUT",
                    message: "websocket operation timed out".into(),
                })?
        })
        .await
    }

    async fn operation<T>(
        &self,
        future: impl Future<Output = Result<T, Error>>,
    ) -> Result<T, Error> {
        let result = self
            .bounded(async {
                tokio::select! {
                    biased;
                    _ = self.closing.cancelled() => Err(closed()),
                    result = future => result,
                }
            })
            .await;
        if result.as_ref().is_err_and(|error| error.code != "CLOSED") {
            self.abort();
        }
        result
    }

    pub async fn send(&self, kind: String, data: Vec<u8>) -> Result<(), Error> {
        if self.closing.is_cancelled() {
            return Err(closed());
        }
        if data.len() > self.max_message_bytes {
            return Err(invalid("message exceeds max_message_bytes"));
        }
        if matches!(kind.as_str(), "ping" | "pong") && data.len() > 125 {
            return Err(invalid("control payload exceeds 125 bytes"));
        }
        let message = match kind.as_str() {
            "text" => Message::Text(
                String::from_utf8(data)
                    .map_err(|_| invalid("text must be UTF-8"))?
                    .into(),
            ),
            "binary" => Message::Binary(data.into()),
            "ping" => Message::Ping(data.into()),
            "pong" => Message::Pong(data.into()),
            _ => return Err(invalid("unknown websocket message kind")),
        };
        self.operation(async {
            self.sender()
                .await
                .as_mut()
                .ok_or_else(closed)?
                .send(message)
                .await
                .map_err(Error::from)
        })
        .await
    }

    pub async fn recv(&self) -> Result<Option<WebSocketMessage>, Error> {
        if self.closing.is_cancelled() {
            return Err(closed());
        }
        let message = self
            .operation(async {
                self.receiver()
                    .await
                    .as_mut()
                    .ok_or_else(closed)?
                    .next()
                    .await
                    .transpose()
                    .map_err(Error::from)
            })
            .await?;
        let is_close = matches!(message, Some(Message::Close(_)) | None);
        // Flush tungstenite's automatic pong/close reply without requiring a second recv call.
        if matches!(message, Some(Message::Ping(_)) | Some(Message::Close(_))) {
            let flushed = self
                .bounded(async {
                    self.sender()
                        .await
                        .as_mut()
                        .ok_or_else(closed)?
                        .flush()
                        .await
                        .map_err(Error::from)
                })
                .await;
            if let Err(error) = flushed {
                self.abort();
                return Err(error);
            }
        }
        if is_close {
            self.closing.cancel();
            self.abort();
        }
        Ok(message.map(|message| match message {
            Message::Text(value) => WebSocketMessage {
                kind: "text",
                data: value.as_bytes().to_vec(),
                code: None,
            },
            Message::Binary(value) => WebSocketMessage {
                kind: "binary",
                data: value.to_vec(),
                code: None,
            },
            Message::Ping(value) => WebSocketMessage {
                kind: "ping",
                data: value.to_vec(),
                code: None,
            },
            Message::Pong(value) => WebSocketMessage {
                kind: "pong",
                data: value.to_vec(),
                code: None,
            },
            Message::Close(frame) => WebSocketMessage {
                kind: "close",
                data: frame
                    .as_ref()
                    .map_or_else(Vec::new, |f| f.reason.as_bytes().to_vec()),
                code: frame.map(|f| f.code.into()),
            },
        }))
    }

    pub async fn close(&self, code: u16, reason: String) -> Result<(), Error> {
        if !matches!(code, 1000..=1003 | 1007..=1014 | 3000..=4999) || reason.len() > 123 {
            return Err(invalid(
                "invalid close code or reason longer than 123 UTF-8 bytes",
            ));
        }
        if self.closing.is_cancelled() || self.cancellation.is_cancelled() {
            return Ok(());
        }
        self.closing.cancel();
        let result = self
            .bounded(async {
                self.sender()
                    .await
                    .as_mut()
                    .ok_or_else(closed)?
                    .send(Message::Close(Some(CloseFrame {
                        code: code.into(),
                        reason: reason.into(),
                    })))
                    .await?;
                let mut rx = self.receiver().await;
                while let Some(message) = rx.as_mut().ok_or_else(closed)?.next().await {
                    if matches!(message?, Message::Close(_)) {
                        break;
                    }
                }
                Ok(())
            })
            .await;
        self.abort();
        result
    }
}

impl Drop for WebSocket {
    fn drop(&mut self) {
        self.abort();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn abort_clears_resource_when_an_external_future_drops_its_guard() {
        let slot = Mutex::new(Some(1));
        let cancellation = CancellationToken::new();
        let guard = SocketGuard {
            slot: slot.lock().await,
            cancellation: &cancellation,
        };
        cancellation.cancel();
        assert!(slot.try_lock().is_err());
        drop(guard);
        assert!(slot.lock().await.is_none());
    }
}

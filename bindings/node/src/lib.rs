use napi::bindgen_prelude::*;
use napi_derive::napi;
use std::sync::Arc;

#[napi(object)]
pub struct Cookie {
    pub name: String,
    pub value: String,
}

#[napi(object)]
pub struct Header {
    pub name: String,
    pub value: Buffer,
}

#[napi(object)]
pub struct Response {
    pub status: u16,
    pub http_version: String,
    pub url: String,
    pub headers: Vec<Header>,
    pub body: Buffer,
}

#[napi]
pub struct Cancellation {
    token: tlsurl_core::stream::CancellationToken,
}

#[napi]
impl Cancellation {
    #[napi(constructor)]
    pub fn new() -> Self {
        Self {
            token: tlsurl_core::stream::CancellationToken::new(),
        }
    }
    #[napi]
    pub fn cancel(&self) {
        self.token.cancel();
    }
}

impl Default for Cancellation {
    fn default() -> Self {
        Self::new()
    }
}

#[napi]
pub struct StreamResponse {
    inner: Arc<tlsurl_core::StreamResponse>,
}

#[napi]
impl StreamResponse {
    #[napi(getter)]
    pub fn status(&self) -> u16 {
        self.inner.head.status
    }
    #[napi(getter)]
    pub fn http_version(&self) -> String {
        self.inner.head.http_version.clone()
    }
    #[napi(getter)]
    pub fn url(&self) -> String {
        self.inner.head.url.clone()
    }
    #[napi(getter)]
    pub fn headers(&self) -> Vec<Header> {
        self.inner
            .head
            .headers
            .iter()
            .map(|(name, value)| Header {
                name: name.clone(),
                value: value.clone().into(),
            })
            .collect()
    }
    #[napi]
    pub fn close(&self) {
        self.inner.close();
    }
    #[napi]
    pub fn next_chunk<'env>(&self, env: &'env Env) -> Result<PromiseRaw<'env, Option<Buffer>>> {
        let inner = self.inner.clone();
        env.spawn_future(async move {
            inner
                .next_chunk()
                .await
                .map(|value| value.map(Buffer::from))
                .map_err(|error| Error::from_reason(error.to_string()))
        })
    }
}

#[napi(object)]
pub struct WebSocketMessage {
    pub kind: String,
    pub data: Buffer,
    pub code: Option<u16>,
}

#[napi]
pub struct WebSocket {
    inner: Arc<tlsurl_core::websocket::WebSocket>,
}

#[napi]
impl WebSocket {
    #[napi(getter)]
    pub fn protocol(&self) -> Option<String> {
        self.inner.protocol.clone()
    }
    #[napi]
    pub fn abort(&self) {
        self.inner.abort();
    }
    #[napi]
    pub fn send<'env>(
        &self,
        env: &'env Env,
        kind: String,
        data: Buffer,
    ) -> Result<PromiseRaw<'env, ()>> {
        let inner = self.inner.clone();
        let data = data.to_vec();
        env.spawn_future(async move {
            inner
                .send(kind, data)
                .await
                .map_err(|e| Error::from_reason(e.to_string()))
        })
    }
    #[napi]
    pub fn recv<'env>(&self, env: &'env Env) -> Result<PromiseRaw<'env, Option<WebSocketMessage>>> {
        let inner = self.inner.clone();
        env.spawn_future(async move {
            inner
                .recv()
                .await
                .map(|message| {
                    message.map(|m| WebSocketMessage {
                        kind: m.kind.into(),
                        data: m.data.into(),
                        code: m.code,
                    })
                })
                .map_err(|e| Error::from_reason(e.to_string()))
        })
    }
    #[napi]
    pub fn close<'env>(
        &self,
        env: &'env Env,
        code: u16,
        reason: String,
    ) -> Result<PromiseRaw<'env, ()>> {
        let inner = self.inner.clone();
        env.spawn_future(async move {
            inner
                .close(code, reason)
                .await
                .map_err(|e| Error::from_reason(e.to_string()))
        })
    }
}

#[napi]
pub struct Client {
    inner: Option<tlsurl_core::Client>,
}

fn config_integer(value: Option<f64>, default: u32) -> Result<u32> {
    let value = value.unwrap_or(f64::from(default));
    if !value.is_finite() || value < 1.0 || value > f64::from(u32::MAX) || value.fract() != 0.0 {
        return Err(Error::from_reason(
            "INVALID_CONFIG: expected a positive 32-bit integer",
        ));
    }
    Ok(value as u32)
}

impl Client {
    fn live(&self) -> Result<&tlsurl_core::Client> {
        self.inner
            .as_ref()
            .ok_or_else(|| Error::from_reason("CLOSED: client is closed"))
    }
}

#[napi]
impl Client {
    #[napi(constructor)]
    pub fn new(
        timeout_ms: Option<f64>,
        max_response_bytes: Option<f64>,
        options: Option<String>,
    ) -> Result<Self> {
        Ok(Self {
            inner: Some(
                tlsurl_core::Client::with_options(
                    config_integer(timeout_ms, 30000)?,
                    config_integer(max_response_bytes, 16777216)?,
                    tlsurl_core::parse_options(options.as_deref())
                        .map_err(|error| Error::from_reason(error.to_string()))?,
                )
                .map_err(|error| Error::from_reason(error.to_string()))?,
            ),
        })
    }

    #[napi]
    pub fn set_cookie(&self, url: String, value: String) -> Result<()> {
        self.live()?
            .set_cookie(&url, &value)
            .map_err(|error| Error::from_reason(error.to_string()))
    }

    #[napi]
    pub fn cookies(&self, url: String) -> Result<Vec<Cookie>> {
        self.live()?
            .cookies(&url)
            .map(|cookies| {
                cookies
                    .into_iter()
                    .map(|(name, value)| Cookie { name, value })
                    .collect()
            })
            .map_err(|error| Error::from_reason(error.to_string()))
    }

    #[napi]
    pub fn clear_cookies(&self) -> Result<()> {
        self.live()?.clear_cookies();
        Ok(())
    }

    #[napi]
    pub fn close(&mut self) {
        self.inner.take();
    }

    #[napi]
    #[allow(clippy::too_many_arguments)] // Explicit native ABI; public API uses RequestOptions.
    pub fn request<'env>(
        &self,
        env: &'env Env,
        method: String,
        url: String,
        headers: Option<Vec<Header>>,
        body: Option<Buffer>,
        options: Option<String>,
        cancellation: &Cancellation,
    ) -> Result<PromiseRaw<'env, Response>> {
        let options = tlsurl_core::parse_options(options.as_deref())
            .map_err(|error| Error::from_reason(error.to_string()))?;
        let headers = headers
            .unwrap_or_default()
            .into_iter()
            .map(|header| (header.name, header.value.to_vec()))
            .collect();
        // Copy mutable JS buffers before handing the request to a worker thread.
        let body = body.map(|body| body.to_vec());
        let client = self.live()?.clone();
        let token = cancellation.token.clone();
        env.spawn_future(async move {
            let response = tlsurl_core::stream::cancellable(
                &token,
                client.request_with_options(method, url, headers, body, options),
            )
            .await
            .map_err(|error| Error::from_reason(error.to_string()))?;
            Ok(Response {
                status: response.status,
                http_version: response.http_version,
                url: response.url,
                headers: response
                    .headers
                    .into_iter()
                    .map(|(name, value)| Header {
                        name,
                        value: value.into(),
                    })
                    .collect(),
                body: response.body.into(),
            })
        })
    }
    #[napi]
    #[allow(clippy::too_many_arguments)] // Explicit native ABI; public API uses RequestOptions.
    pub fn stream<'env>(
        &self,
        env: &'env Env,
        method: String,
        url: String,
        headers: Option<Vec<Header>>,
        body: Option<Buffer>,
        options: Option<String>,
        cancellation: &Cancellation,
    ) -> Result<PromiseRaw<'env, StreamResponse>> {
        let options = tlsurl_core::parse_options(options.as_deref())
            .map_err(|error| Error::from_reason(error.to_string()))?;
        let headers = headers
            .unwrap_or_default()
            .into_iter()
            .map(|h| (h.name, h.value.to_vec()))
            .collect();
        let body = body.map(|b| b.to_vec());
        let client = self.live()?.clone();
        let token = cancellation.token.clone();
        env.spawn_future(async move {
            tlsurl_core::stream::cancellable(
                &token,
                client.stream_with_options(method, url, headers, body, options),
            )
            .await
            .map(|inner| StreamResponse {
                inner: Arc::new(inner),
            })
            .map_err(|error| Error::from_reason(error.to_string()))
        })
    }
    #[napi]
    pub fn websocket<'env>(
        &self,
        env: &'env Env,
        url: String,
        headers: Vec<Header>,
        options: String,
        cancellation: &Cancellation,
    ) -> Result<PromiseRaw<'env, WebSocket>> {
        let options = tlsurl_core::parse_options(Some(&options))
            .map_err(|e| Error::from_reason(e.to_string()))?;
        let headers = headers
            .into_iter()
            .map(|h| (h.name, h.value.to_vec()))
            .collect();
        let client = self.live()?.clone();
        let token = cancellation.token.clone();
        env.spawn_future(async move {
            tlsurl_core::stream::cancellable(&token, client.websocket(url, headers, options))
                .await
                .map(|inner| WebSocket {
                    inner: Arc::new(inner),
                })
                .map_err(|e| Error::from_reason(e.to_string()))
        })
    }
}

#[napi]
pub fn available_profiles() -> Result<Vec<String>> {
    tlsurl_core::available_profiles().map_err(|error| Error::from_reason(error.to_string()))
}

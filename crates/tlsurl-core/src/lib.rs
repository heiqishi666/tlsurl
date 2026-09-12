//! Shared request semantics for the Python and Node.js bindings.

use std::{fmt, time::Duration};

use futures_util::StreamExt;

#[derive(Debug)]
pub struct Error {
    pub code: &'static str,
    pub message: String,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for Error {}

impl From<wreq::Error> for Error {
    fn from(error: wreq::Error) -> Self {
        let code = if error.is_timeout() {
            "TIMEOUT"
        } else if error.is_builder() {
            "INVALID_REQUEST"
        } else if error.is_tls() {
            "TLS"
        } else if error.is_dns() {
            "DNS"
        } else if error.is_connect() {
            "CONNECT"
        } else {
            "REQUEST"
        };
        Self {
            code,
            message: error.without_uri().to_string(),
        }
    }
}

#[derive(Clone)]
pub struct Client {
    inner: wreq::Client,
    max_response_bytes: usize,
}

pub struct Response {
    pub status: u16,
    pub url: String,
    pub headers: Vec<(String, Vec<u8>)>,
    pub body: Vec<u8>,
}

impl Client {
    pub fn new(timeout_ms: u32, max_response_bytes: u32) -> Result<Self, Error> {
        if timeout_ms == 0 || max_response_bytes == 0 {
            return Err(Error {
                code: "INVALID_CONFIG",
                message: "timeout_ms and max_response_bytes must be positive".into(),
            });
        }
        Ok(Self {
            inner: wreq::Client::builder()
                .no_proxy()
                .cookie_store(true)
                .redirect(wreq::redirect::Policy::limited(10))
                .timeout(Duration::from_millis(timeout_ms.into()))
                .build()?,
            max_response_bytes: max_response_bytes as usize,
        })
    }

    pub async fn request(
        &self,
        method: String,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        body: Option<Vec<u8>>,
    ) -> Result<Response, Error> {
        let method = wreq::Method::from_bytes(method.as_bytes()).map_err(|error| Error {
            code: "INVALID_REQUEST",
            message: error.to_string(),
        })?;
        let mut request = self.inner.request(method, url);
        let mut original_headers = wreq::header::OrigHeaderMap::new();
        for (name, value) in headers {
            original_headers.insert(name.clone());
            request = request.header(name, value);
        }
        request = request.orig_headers(original_headers);
        if let Some(body) = body {
            request = request.body(body);
        }
        let response = request.send().await?;
        let status = response.status().as_u16();
        let url = response.uri().to_string();
        let headers = response
            .headers()
            .iter()
            .map(|(name, value)| (name.to_string(), value.as_bytes().to_vec()))
            .collect();
        let mut stream = response.bytes_stream();
        let mut body = Vec::new();
        while let Some(chunk) = stream.next().await {
            let chunk = chunk?;
            if chunk.len() > self.max_response_bytes.saturating_sub(body.len()) {
                return Err(Error {
                    code: "BODY_TOO_LARGE",
                    message: format!("response exceeds {} bytes", self.max_response_bytes),
                });
            }
            body.extend_from_slice(&chunk);
        }
        Ok(Response {
            status,
            url,
            headers,
            body,
        })
    }
}

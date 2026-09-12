//! Shared request semantics for the Python and Node.js bindings.

use std::{fmt, sync::Arc, time::Duration};

use futures_util::StreamExt;
use serde::Deserialize;

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ClientOptions {
    pub connect_timeout_ms: Option<u32>,
    pub read_timeout_ms: Option<u32>,
    pub proxy: Option<String>,
    pub verify: Option<bool>,
    pub ca_pem: Option<String>,
    pub max_redirects: Option<u32>,
    pub cookies: Option<bool>,
    pub user_agent: Option<String>,
    pub http_version: Option<String>,
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct RequestOptions {
    pub params: Vec<(String, String)>,
    pub timeout_ms: Option<u32>,
    pub max_redirects: Option<u32>,
    pub basic_auth: Option<(String, String)>,
    pub bearer_token: Option<String>,
}

pub fn parse_options<T: serde::de::DeserializeOwned + Default>(
    json: Option<&str>,
) -> Result<T, Error> {
    json.map_or_else(
        || Ok(T::default()),
        |json| {
            serde_json::from_str(json).map_err(|_| Error {
                code: "INVALID_CONFIG",
                message: "invalid options: check field names and value types".into(),
            })
        },
    )
}

fn positive_ms(value: u32) -> Result<Duration, Error> {
    if value == 0 {
        return Err(Error {
            code: "INVALID_CONFIG",
            message: "timeout must be positive".into(),
        });
    }
    Ok(Duration::from_millis(value.into()))
}

fn redirect_policy(limit: u32) -> wreq::redirect::Policy {
    if limit == 0 {
        wreq::redirect::Policy::none()
    } else {
        wreq::redirect::Policy::limited(limit as usize)
    }
}

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
    jar: Arc<wreq::cookie::Jar>,
}

pub struct Response {
    pub status: u16,
    pub url: String,
    pub headers: Vec<(String, Vec<u8>)>,
    pub body: Vec<u8>,
}

impl Client {
    pub fn new(timeout_ms: u32, max_response_bytes: u32) -> Result<Self, Error> {
        Self::with_options(timeout_ms, max_response_bytes, ClientOptions::default())
    }

    pub fn with_options(
        timeout_ms: u32,
        max_response_bytes: u32,
        options: ClientOptions,
    ) -> Result<Self, Error> {
        if timeout_ms == 0 || max_response_bytes == 0 {
            return Err(Error {
                code: "INVALID_CONFIG",
                message: "timeout_ms and max_response_bytes must be positive".into(),
            });
        }
        let jar = Arc::new(wreq::cookie::Jar::default());
        let mut builder = wreq::Client::builder()
            .no_proxy()
            .redirect(redirect_policy(options.max_redirects.unwrap_or(10)))
            .timeout(positive_ms(timeout_ms)?)
            .tls_cert_verification(options.verify.unwrap_or(true));
        if options.cookies.unwrap_or(true) {
            builder = builder.cookie_provider(jar.clone());
        }
        if let Some(timeout) = options.connect_timeout_ms {
            builder = builder.connect_timeout(positive_ms(timeout)?);
        }
        if let Some(timeout) = options.read_timeout_ms {
            builder = builder.read_timeout(positive_ms(timeout)?);
        }
        if let Some(proxy) = options.proxy {
            builder = builder.proxy(wreq::Proxy::all(proxy)?);
        }
        if let Some(pem) = options.ca_pem {
            builder = builder
                .tls_cert_store(wreq::tls::trust::CertStore::from_pem_stack(pem.as_bytes())?);
        }
        if let Some(agent) = options.user_agent {
            builder = builder.user_agent(agent);
        }
        if let Some(version) = options.http_version {
            builder = match version.as_str() {
                "auto" => builder,
                "1.1" => builder.http1_only(),
                "2" => builder.http2_only(),
                _ => {
                    return Err(Error {
                        code: "INVALID_CONFIG",
                        message: "http_version must be auto, 1.1 or 2".into(),
                    });
                }
            };
        }
        Ok(Self {
            inner: builder.build()?,
            max_response_bytes: max_response_bytes as usize,
            jar,
        })
    }

    pub fn clear_cookies(&self) {
        self.jar.clear();
    }

    pub async fn request(
        &self,
        method: String,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        body: Option<Vec<u8>>,
    ) -> Result<Response, Error> {
        self.request_with_options(method, url, headers, body, RequestOptions::default())
            .await
    }

    pub async fn request_with_options(
        &self,
        method: String,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        body: Option<Vec<u8>>,
        options: RequestOptions,
    ) -> Result<Response, Error> {
        let method = wreq::Method::from_bytes(method.as_bytes()).map_err(|error| Error {
            code: "INVALID_REQUEST",
            message: error.to_string(),
        })?;
        let mut url = url::Url::parse(&url).map_err(|_| Error {
            code: "INVALID_REQUEST",
            message: "invalid absolute URL".into(),
        })?;
        if !matches!(url.scheme(), "http" | "https") {
            return Err(Error {
                code: "INVALID_REQUEST",
                message: "only http and https URLs are supported".into(),
            });
        }
        if !options.params.is_empty() {
            url.query_pairs_mut().extend_pairs(options.params);
        }
        if options.basic_auth.is_some() && options.bearer_token.is_some() {
            return Err(Error {
                code: "INVALID_REQUEST",
                message: "basic_auth and bearer_token are mutually exclusive".into(),
            });
        }
        if (options.basic_auth.is_some() || options.bearer_token.is_some())
            && headers
                .iter()
                .any(|(name, _)| name.eq_ignore_ascii_case("authorization"))
        {
            return Err(Error {
                code: "INVALID_REQUEST",
                message: "explicit Authorization header conflicts with authentication options"
                    .into(),
            });
        }
        let mut request = self.inner.request(method, url.as_str());
        if let Some(timeout) = options.timeout_ms {
            request = request.timeout(positive_ms(timeout)?);
        }
        if let Some(limit) = options.max_redirects {
            request = request.redirect(redirect_policy(limit));
        }
        if let Some((user, password)) = options.basic_auth {
            request = request.basic_auth(user, Some(password));
        }
        if let Some(token) = options.bearer_token {
            request = request.bearer_auth(token);
        }
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

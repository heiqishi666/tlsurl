//! Shared request semantics for the Python and Node.js bindings.

use std::{fmt, sync::Arc, time::Duration};

use futures_util::StreamExt;
use serde::Deserialize;
use wreq::cookie::IntoCookie;
mod protocol;
mod random_tls;
pub mod stream;
mod upload;
pub mod websocket;
pub use stream::StreamResponse;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MultipartPart {
    pub name: String,
    #[serde(default)]
    pub offset: usize,
    #[serde(default)]
    pub length: usize,
    pub file: Option<String>,
    pub filename: Option<String>,
    pub content_type: Option<String>,
}

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
    pub tls: Option<protocol::TlsConfig>,
    pub random_tls: bool,
    pub random_tls_seed: Option<u32>,
    pub http2: Option<protocol::Http2Config>,
    pub identity: Option<protocol::IdentityConfig>,
    pub profile: Option<wreq_util::Profile>,
    pub platform: Option<wreq_util::Platform>,
    pub decompress: Option<bool>,
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct RequestOptions {
    pub body_file: Option<String>,
    pub params: Vec<(String, String)>,
    pub timeout_ms: Option<u32>,
    pub max_redirects: Option<u32>,
    pub basic_auth: Option<(String, String)>,
    pub bearer_token: Option<String>,
    pub multipart: Option<Vec<MultipartPart>>,
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
    pub http_version: String,
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
        let mut builder = wreq::Client::builder().no_proxy();
        if options.random_tls {
            if options.tls.is_some() || options.profile.is_some() || options.platform.is_some() {
                return Err(Error {
                    code: "INVALID_CONFIG",
                    message: "random_tls cannot be combined with tls, profile or platform".into(),
                });
            }
            builder = builder.tls_options(random_tls::options(options.random_tls_seed)?);
        } else if options.random_tls_seed.is_some() {
            return Err(Error {
                code: "INVALID_CONFIG",
                message: "random_tls_seed requires random_tls=true".into(),
            });
        }
        let mut profile_tls = None;
        let mut profile_http2 = None;
        if let Some(profile) = options.profile {
            let emulation = wreq::IntoEmulation::into_emulation(
                wreq_util::Emulation::builder()
                    .profile(profile)
                    .platform(options.platform.unwrap_or_default())
                    .build(),
            );
            profile_tls = emulation.tls_options.clone();
            profile_http2 = emulation.http2_options.clone();
            builder = builder.emulation(emulation);
        } else if options.platform.is_some() {
            return Err(Error {
                code: "INVALID_CONFIG",
                message: "platform requires a profile".into(),
            });
        }
        if options.decompress == Some(false) {
            builder = builder.no_gzip().no_brotli().no_deflate().no_zstd();
        }
        builder = builder
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
        if let Some(tls) = options.tls {
            builder = tls.apply(builder, profile_tls)?;
        }
        if let Some(http2) = options.http2 {
            builder = http2.apply(builder, profile_http2)?;
        }
        if let Some(identity) = options.identity {
            builder = identity.apply(builder)?;
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

    pub fn set_cookie(&self, url: &str, value: &str) -> Result<(), Error> {
        let url = http_url(url)?;
        let cookie = value.into_cookie().ok_or_else(|| Error {
            code: "INVALID_REQUEST",
            message: "invalid Set-Cookie value".into(),
        })?;
        self.jar.add(cookie, url.as_str());
        Ok(())
    }

    pub fn cookies(&self, url: &str) -> Result<Vec<(String, String)>, Error> {
        let url = http_url(url)?;
        Ok(self
            .jar
            .matches(url.as_str())
            .map(|c| (c.name().to_owned(), c.value().to_owned()))
            .collect())
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
        let response = self
            .stream_with_options(method, url, headers, body, options)
            .await?;
        let mut body = Vec::new();
        while let Some(chunk) = response.next_chunk().await? {
            if chunk.len() > self.max_response_bytes.saturating_sub(body.len()) {
                return Err(Error {
                    code: "BODY_TOO_LARGE",
                    message: format!("response exceeds {} bytes", self.max_response_bytes),
                });
            }
            body.extend_from_slice(&chunk);
        }
        Ok(Response {
            status: response.head.status,
            http_version: response.head.http_version.clone(),
            url: response.head.url.clone(),
            headers: response.head.headers.clone(),
            body,
        })
    }

    pub async fn stream_with_options(
        &self,
        method: String,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        body: Option<Vec<u8>>,
        options: RequestOptions,
    ) -> Result<StreamResponse, Error> {
        let method = wreq::Method::from_bytes(method.as_bytes()).map_err(|error| Error {
            code: "INVALID_REQUEST",
            message: error.to_string(),
        })?;
        let mut url = http_url(&url)?;
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
        if options.body_file.is_some() && (body.is_some() || options.multipart.is_some()) {
            return Err(Error {
                code: "INVALID_REQUEST",
                message: "body_file conflicts with another request body".into(),
            });
        }
        let has_files = options.body_file.is_some()
            || options
                .multipart
                .as_ref()
                .is_some_and(|parts| parts.iter().any(|part| part.file.is_some()));
        if has_files
            && headers.iter().any(|(name, _)| {
                name.eq_ignore_ascii_case("content-length")
                    || name.eq_ignore_ascii_case("transfer-encoding")
            })
        {
            return Err(Error {
                code: "INVALID_REQUEST",
                message: "file upload framing is managed by the client".into(),
            });
        }
        let has_headers = !headers.is_empty();
        let mut original_headers = wreq::header::OrigHeaderMap::new();
        for (name, value) in headers {
            original_headers.insert(name.clone());
            request = request.header(name, value);
        }
        if has_headers {
            request = request.orig_headers(original_headers);
        }
        if let Some(parts) = options.multipart {
            let data = body.unwrap_or_default();
            let mut form = wreq::multipart::Form::new();
            for descriptor in parts {
                let filename = descriptor.filename.or_else(|| {
                    descriptor
                        .file
                        .as_ref()
                        .and_then(|path| std::path::Path::new(path).file_name())
                        .map(|name| name.to_string_lossy().into_owned())
                });
                let mut part = if let Some(path) = descriptor.file {
                    if descriptor.offset != 0 || descriptor.length != 0 {
                        return Err(Error {
                            code: "INVALID_REQUEST",
                            message: "multipart file cannot include a byte range".into(),
                        });
                    }
                    let (body, length) = upload::file_body(&path).await?;
                    wreq::multipart::Part::stream_with_length(body, length)
                } else {
                    let end = descriptor.offset.checked_add(descriptor.length);
                    let bytes = end
                        .and_then(|end| data.get(descriptor.offset..end))
                        .ok_or_else(|| Error {
                            code: "INVALID_REQUEST",
                            message: "invalid multipart byte range".into(),
                        })?;
                    wreq::multipart::Part::bytes(bytes.to_vec())
                };
                if let Some(filename) = filename {
                    part = part.file_name(filename);
                }
                if let Some(content_type) = descriptor.content_type {
                    part = part.mime_str(&content_type)?;
                }
                form = form.part(descriptor.name, part);
            }
            request = request.multipart(form);
        } else if let Some(path) = options.body_file {
            let (body, length) = upload::file_body(&path).await?;
            request = request
                .header(wreq::header::CONTENT_LENGTH, length)
                .body(body);
        } else if let Some(body) = body {
            request = request.body(body);
        }
        let response = request.send().await?;
        let status = response.status().as_u16();
        let http_version = match response.version() {
            wreq::Version::HTTP_09 => "0.9",
            wreq::Version::HTTP_10 => "1.0",
            wreq::Version::HTTP_11 => "1.1",
            wreq::Version::HTTP_2 => "2",
            _ => "unknown",
        }
        .to_owned();
        let url = response.uri().to_string();
        let headers = response
            .headers()
            .iter()
            .map(|(name, value)| (name.to_string(), value.as_bytes().to_vec()))
            .collect();
        Ok(StreamResponse::new(
            Response {
                status,
                http_version,
                url,
                headers,
                body: Vec::new(),
            },
            response.bytes_stream().boxed(),
        ))
    }
}

fn http_url(value: &str) -> Result<url::Url, Error> {
    let url = url::Url::parse(value).map_err(|_| Error {
        code: "INVALID_REQUEST",
        message: "invalid absolute URL".into(),
    })?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(Error {
            code: "INVALID_REQUEST",
            message: "only http and https URLs are supported".into(),
        });
    }
    Ok(url)
}

pub fn available_profiles() -> Result<Vec<String>, Error> {
    wreq_util::Profile::VARIANTS
        .iter()
        .map(|profile| {
            serde_json::to_value(profile)
                .ok()
                .and_then(|value| value.as_str().map(ToOwned::to_owned))
                .ok_or_else(|| Error {
                    code: "INTERNAL",
                    message: "failed to serialize profile name".into(),
                })
        })
        .collect()
}

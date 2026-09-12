use napi::bindgen_prelude::*;
use napi_derive::napi;

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
pub struct Client {
    inner: tlsurl_core::Client,
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

#[napi]
impl Client {
    #[napi(constructor)]
    pub fn new(
        timeout_ms: Option<f64>,
        max_response_bytes: Option<f64>,
        options: Option<String>,
    ) -> Result<Self> {
        Ok(Self {
            inner: tlsurl_core::Client::with_options(
                config_integer(timeout_ms, 30000)?,
                config_integer(max_response_bytes, 16777216)?,
                tlsurl_core::parse_options(options.as_deref())
                    .map_err(|error| Error::from_reason(error.to_string()))?,
            )
            .map_err(|error| Error::from_reason(error.to_string()))?,
        })
    }

    #[napi]
    pub fn set_cookie(&self, url: String, value: String) -> Result<()> {
        self.inner
            .set_cookie(&url, &value)
            .map_err(|error| Error::from_reason(error.to_string()))
    }

    #[napi]
    pub fn cookies(&self, url: String) -> Result<Vec<Cookie>> {
        self.inner
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
    pub fn clear_cookies(&self) {
        self.inner.clear_cookies();
    }

    #[napi]
    pub fn request<'env>(
        &self,
        env: &'env Env,
        method: String,
        url: String,
        headers: Option<Vec<Header>>,
        body: Option<Buffer>,
        options: Option<String>,
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
        let client = self.inner.clone();
        env.spawn_future(async move {
            let response = client
                .request_with_options(method, url, headers, body, options)
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
}

#[napi]
pub fn available_profiles() -> Result<Vec<String>> {
    tlsurl_core::available_profiles().map_err(|error| Error::from_reason(error.to_string()))
}

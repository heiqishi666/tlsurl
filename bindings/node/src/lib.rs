use napi::bindgen_prelude::*;
use napi_derive::napi;

#[napi(object)]
pub struct Header {
    pub name: String,
    pub value: Buffer,
}

#[napi(object)]
pub struct Response {
    pub status: u16,
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
    pub fn new(timeout_ms: Option<f64>, max_response_bytes: Option<f64>) -> Result<Self> {
        Ok(Self {
            inner: tlsurl_core::Client::new(
                config_integer(timeout_ms, 30000)?,
                config_integer(max_response_bytes, 16777216)?,
            )
            .map_err(|error| Error::from_reason(error.to_string()))?,
        })
    }

    #[napi]
    pub fn request<'env>(
        &self,
        env: &'env Env,
        method: String,
        url: String,
        headers: Option<Vec<Header>>,
        body: Option<Buffer>,
    ) -> Result<PromiseRaw<'env, Response>> {
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
                .request(method, url, headers, body)
                .await
                .map_err(|error| Error::from_reason(error.to_string()))?;
            Ok(Response {
                status: response.status,
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

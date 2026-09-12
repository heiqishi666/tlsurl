use pyo3::{exceptions::PyRuntimeError, prelude::*, types::PyBytes};
use std::sync::Arc;

fn py_error(error: tlsurl_core::Error) -> PyErr {
    PyRuntimeError::new_err(error.to_string())
}

#[pyclass(module = "tlsurl._native")]
struct Response {
    inner: tlsurl_core::Response,
}

#[pymethods]
impl Response {
    #[getter]
    fn status(&self) -> u16 {
        self.inner.status
    }

    #[getter]
    fn http_version(&self) -> &str {
        &self.inner.http_version
    }

    #[getter]
    fn url(&self) -> &str {
        &self.inner.url
    }

    #[getter]
    fn body<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.inner.body)
    }

    #[getter]
    fn headers<'py>(&self, py: Python<'py>) -> Vec<(String, Bound<'py, PyBytes>)> {
        self.inner
            .headers
            .iter()
            .map(|(name, value)| (name.clone(), PyBytes::new(py, value)))
            .collect()
    }
}

#[pyclass(module = "tlsurl._native")]
struct StreamResponse {
    inner: Arc<tlsurl_core::StreamResponse>,
}

#[pymethods]
impl StreamResponse {
    #[getter]
    fn status(&self) -> u16 {
        self.inner.head.status
    }
    #[getter]
    fn http_version(&self) -> &str {
        &self.inner.head.http_version
    }
    #[getter]
    fn url(&self) -> &str {
        &self.inner.head.url
    }
    #[getter]
    fn headers<'py>(&self, py: Python<'py>) -> Vec<(String, Bound<'py, PyBytes>)> {
        self.inner
            .head
            .headers
            .iter()
            .map(|(name, value)| (name.clone(), PyBytes::new(py, value)))
            .collect()
    }
    fn close(&self) {
        self.inner.close();
    }
    fn next_chunk<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyBytes>>> {
        let chunk = py
            .detach(|| pyo3_async_runtimes::tokio::get_runtime().block_on(self.inner.next_chunk()))
            .map_err(py_error)?;
        Ok(chunk.map(|chunk| PyBytes::new(py, &chunk)))
    }
    fn next_chunk_async<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let chunk = inner.next_chunk().await.map_err(py_error)?;
            Ok(Python::attach(|py| {
                chunk.map(|chunk| PyBytes::new(py, &chunk).unbind())
            }))
        })
    }
}

#[pyclass(module = "tlsurl._native")]
struct WebSocketMessage {
    inner: tlsurl_core::websocket::WebSocketMessage,
}
#[pymethods]
impl WebSocketMessage {
    #[getter]
    fn kind(&self) -> &str {
        self.inner.kind
    }
    #[getter]
    fn code(&self) -> Option<u16> {
        self.inner.code
    }
    #[getter]
    fn data<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.inner.data)
    }
}

#[pyclass(module = "tlsurl._native")]
struct WebSocket {
    inner: Arc<tlsurl_core::websocket::WebSocket>,
}
#[pymethods]
impl WebSocket {
    #[getter]
    fn protocol(&self) -> Option<String> {
        self.inner.protocol.clone()
    }
    fn abort(&self) {
        self.inner.abort();
    }
    fn send(&self, py: Python<'_>, kind: String, data: Vec<u8>) -> PyResult<()> {
        py.detach(|| {
            pyo3_async_runtimes::tokio::get_runtime().block_on(self.inner.send(kind, data))
        })
        .map_err(py_error)
    }
    fn send_async<'py>(
        &self,
        py: Python<'py>,
        kind: String,
        data: Vec<u8>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            inner.send(kind, data).await.map_err(py_error)
        })
    }
    fn recv(&self, py: Python<'_>) -> PyResult<Option<WebSocketMessage>> {
        py.detach(|| pyo3_async_runtimes::tokio::get_runtime().block_on(self.inner.recv()))
            .map(|message| message.map(|inner| WebSocketMessage { inner }))
            .map_err(py_error)
    }
    fn recv_async<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            inner
                .recv()
                .await
                .map(|message| message.map(|inner| WebSocketMessage { inner }))
                .map_err(py_error)
        })
    }
    fn close(&self, py: Python<'_>, code: u16, reason: String) -> PyResult<()> {
        py.detach(|| {
            pyo3_async_runtimes::tokio::get_runtime().block_on(self.inner.close(code, reason))
        })
        .map_err(py_error)
    }
    fn close_async<'py>(
        &self,
        py: Python<'py>,
        code: u16,
        reason: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            inner.close(code, reason).await.map_err(py_error)
        })
    }
}

#[pyclass(module = "tlsurl._native")]
struct Client {
    inner: tlsurl_core::Client,
}

#[pymethods]
impl Client {
    #[new]
    #[pyo3(signature = (timeout_ms=30000, max_response_bytes=16777216, options=None))]
    fn new(timeout_ms: u32, max_response_bytes: u32, options: Option<String>) -> PyResult<Self> {
        let _guard = pyo3_async_runtimes::tokio::get_runtime().enter();
        Ok(Self {
            inner: tlsurl_core::Client::with_options(
                timeout_ms,
                max_response_bytes,
                tlsurl_core::parse_options(options.as_deref()).map_err(py_error)?,
            )
            .map_err(py_error)?,
        })
    }

    fn set_cookie(&self, url: &str, value: &str) -> PyResult<()> {
        self.inner.set_cookie(url, value).map_err(py_error)
    }

    fn cookies(&self, url: &str) -> PyResult<Vec<(String, String)>> {
        self.inner.cookies(url).map_err(py_error)
    }

    fn clear_cookies(&self) {
        self.inner.clear_cookies();
    }

    #[pyo3(signature = (method, url, headers=None, body=None, options=None))]
    fn request(
        &self,
        py: Python<'_>,
        method: String,
        url: String,
        headers: Option<Vec<(String, Vec<u8>)>>,
        body: Option<Vec<u8>>,
        options: Option<String>,
    ) -> PyResult<Response> {
        let options = tlsurl_core::parse_options(options.as_deref()).map_err(py_error)?;
        py.detach(|| {
            pyo3_async_runtimes::tokio::get_runtime()
                .block_on(self.inner.request_with_options(
                    method,
                    url,
                    headers.unwrap_or_default(),
                    body,
                    options,
                ))
                .map(|inner| Response { inner })
                .map_err(py_error)
        })
    }

    #[pyo3(signature = (method, url, headers=None, body=None, options=None))]
    fn request_async<'py>(
        &self,
        py: Python<'py>,
        method: String,
        url: String,
        headers: Option<Vec<(String, Vec<u8>)>>,
        body: Option<Vec<u8>>,
        options: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let options = tlsurl_core::parse_options(options.as_deref()).map_err(py_error)?;
        let client = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            client
                .request_with_options(method, url, headers.unwrap_or_default(), body, options)
                .await
                .map(|inner| Response { inner })
                .map_err(py_error)
        })
    }
    #[pyo3(signature = (method, url, headers=None, body=None, options=None))]
    fn stream(
        &self,
        py: Python<'_>,
        method: String,
        url: String,
        headers: Option<Vec<(String, Vec<u8>)>>,
        body: Option<Vec<u8>>,
        options: Option<String>,
    ) -> PyResult<StreamResponse> {
        let options = tlsurl_core::parse_options(options.as_deref()).map_err(py_error)?;
        py.detach(|| {
            pyo3_async_runtimes::tokio::get_runtime().block_on(self.inner.stream_with_options(
                method,
                url,
                headers.unwrap_or_default(),
                body,
                options,
            ))
        })
        .map(|inner| StreamResponse {
            inner: Arc::new(inner),
        })
        .map_err(py_error)
    }
    #[pyo3(signature = (method, url, headers=None, body=None, options=None))]
    fn stream_async<'py>(
        &self,
        py: Python<'py>,
        method: String,
        url: String,
        headers: Option<Vec<(String, Vec<u8>)>>,
        body: Option<Vec<u8>>,
        options: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let options = tlsurl_core::parse_options(options.as_deref()).map_err(py_error)?;
        let client = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            client
                .stream_with_options(method, url, headers.unwrap_or_default(), body, options)
                .await
                .map(|inner| StreamResponse {
                    inner: Arc::new(inner),
                })
                .map_err(py_error)
        })
    }
    fn websocket(
        &self,
        py: Python<'_>,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        options: String,
    ) -> PyResult<WebSocket> {
        let options = tlsurl_core::parse_options(Some(&options)).map_err(py_error)?;
        py.detach(|| {
            pyo3_async_runtimes::tokio::get_runtime()
                .block_on(self.inner.websocket(url, headers, options))
        })
        .map(|inner| WebSocket {
            inner: Arc::new(inner),
        })
        .map_err(py_error)
    }
    fn websocket_async<'py>(
        &self,
        py: Python<'py>,
        url: String,
        headers: Vec<(String, Vec<u8>)>,
        options: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let options = tlsurl_core::parse_options(Some(&options)).map_err(py_error)?;
        let client = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            client
                .websocket(url, headers, options)
                .await
                .map(|inner| WebSocket {
                    inner: Arc::new(inner),
                })
                .map_err(py_error)
        })
    }
}

#[pyfunction]
fn available_profiles() -> PyResult<Vec<String>> {
    tlsurl_core::available_profiles().map_err(py_error)
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(available_profiles, module)?)?;
    module.add_class::<Client>()?;
    module.add_class::<Response>()?;
    module.add_class::<StreamResponse>()?;
    module.add_class::<WebSocket>()?;
    module.add_class::<WebSocketMessage>()?;
    Ok(())
}

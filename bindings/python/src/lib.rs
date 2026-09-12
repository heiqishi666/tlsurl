use pyo3::{exceptions::PyRuntimeError, prelude::*, types::PyBytes};

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
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Client>()?;
    module.add_class::<Response>()?;
    Ok(())
}

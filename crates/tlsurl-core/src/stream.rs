use bytes::Bytes;
use futures_util::{StreamExt, stream::BoxStream};
use tokio::sync::Mutex;
pub use tokio_util::sync::CancellationToken;

use crate::{Error, Response};

type Body = BoxStream<'static, Result<Bytes, wreq::Error>>;

/// A pull-based response. No application background queue is created.
pub struct StreamResponse {
    pub head: Response,
    body: Mutex<Option<Body>>,
    cancellation: CancellationToken,
}

impl StreamResponse {
    pub(crate) fn new(head: Response, body: Body) -> Self {
        Self {
            head,
            body: Mutex::new(Some(body)),
            cancellation: CancellationToken::new(),
        }
    }

    pub fn close(&self) {
        self.cancellation.cancel();
        // If a read holds the lock, cancellation wakes it and it drops the body.
        if let Ok(mut body) = self.body.try_lock() {
            *body = None;
        }
    }

    pub async fn next_chunk(&self) -> Result<Option<Vec<u8>>, Error> {
        let mut body = self.body.lock().await;
        if self.cancellation.is_cancelled() {
            *body = None;
            return Err(cancelled());
        }
        let Some(stream) = body.as_mut() else {
            return Ok(None);
        };
        let result = tokio::select! {
            biased;
            _ = self.cancellation.cancelled() => Err(cancelled()),
            chunk = stream.next() => chunk.transpose().map(|chunk| chunk.map(|b| b.to_vec())).map_err(Error::from),
        };
        if !matches!(result, Ok(Some(_))) {
            *body = None;
        }
        result
    }
}

impl Drop for StreamResponse {
    fn drop(&mut self) {
        self.close();
    }
}

pub fn cancelled() -> Error {
    Error {
        code: "CANCELLED",
        message: "operation cancelled".into(),
    }
}

pub async fn cancellable<T>(
    token: &CancellationToken,
    future: impl std::future::Future<Output = Result<T, Error>>,
) -> Result<T, Error> {
    tokio::select! {
        biased;
        _ = token.cancelled() => Err(cancelled()),
        result = future => result,
    }
}

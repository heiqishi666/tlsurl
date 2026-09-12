use tokio::io::AsyncReadExt;
use tokio_util::io::ReaderStream;

use crate::Error;

pub async fn file_body(path: &str) -> Result<(wreq::Body, u64), Error> {
    let file = tokio::fs::File::open(path).await.map_err(file_error)?;
    let metadata = file.metadata().await.map_err(file_error)?;
    if !metadata.is_file() {
        return Err(Error {
            code: "INVALID_REQUEST",
            message: "upload source must be a regular file".into(),
        });
    }
    let length = metadata.len();
    // Bound each read and prevent an appended file from exceeding its declared length.
    let stream = ReaderStream::with_capacity(file.take(length), 64 * 1024);
    Ok((wreq::Body::wrap_stream(stream), length))
}

fn file_error(_: std::io::Error) -> Error {
    Error {
        code: "FILE_IO",
        message: "cannot open or inspect upload file".into(),
    }
}

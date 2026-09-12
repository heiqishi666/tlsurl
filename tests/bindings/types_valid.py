"""Static consumer examples; this module is checked, never executed."""
from pathlib import Path
from tlsurl import Client, AsyncClient, Response, StreamResponse, WebSocket, AsyncWebSocket, TlsOptions, MultipartFile


def synchronous(url: str) -> None:
    tls: TlsOptions = {"min_version": "1.2", "alpn": ["h2", "http/1.1"]}
    file: MultipartFile = {"name": "file", "file": Path("payload.bin")}
    with Client(tls=tls, platform="windows", http_version="auto") as client:
        response: Response = client.post(url, json={"name": "value"}, params=[("a", "1")], timeout_ms=500)
        response.raise_for_status().json()
        client.post(url, multipart=[file])
        client.post(url, body_file=Path("payload.bin"))
        stream: StreamResponse = client.stream("GET", url)
        with stream:
            for chunk in stream:
                assert isinstance(chunk, bytes)
        socket: WebSocket = client.websocket(url, protocols=["echo"])
        with socket:
            socket.send("hello")
            message = socket.recv()
            if message:
                message.data.decode()


async def asynchronous(url: str) -> None:
    async with AsyncClient(http2={"initial_window_size": 65535}) as client:
        response: Response = await client.get(url, headers={"X-Test": "yes"})
        response.text()
        async with await client.stream("GET", url) as stream:
            async for chunk in stream:
                assert isinstance(chunk, bytes)
        socket: AsyncWebSocket = await client.websocket(url)
        async with socket:
            await socket.send(b"hello")
            await socket.recv()

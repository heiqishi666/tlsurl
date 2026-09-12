"""Native HTTP clients. Responses are buffered, with a configurable size limit."""

from ._native import Client, Response


class AsyncClient:
    def __init__(self, timeout_ms=30000, max_response_bytes=16777216):
        self._client = Client(timeout_ms, max_response_bytes)

    async def request(self, method, url, headers=None, body=None):
        return await self._client.request_async(method, url, headers, body)


__all__ = ["Client", "AsyncClient", "Response"]

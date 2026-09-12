"""Precompiled HTTP clients with shared Rust request semantics."""

import json as _json
from urllib.parse import urlencode

from . import _native

_UNSET = object()


class Error(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _error(error):
    code, separator, message = str(error).partition(": ")
    return Error(code if separator else "REQUEST", message if separator else str(error))


class Response:
    def __init__(self, native):
        self._native = native

    @property
    def status(self):
        return self._native.status

    @property
    def url(self):
        return self._native.url

    @property
    def headers(self):
        return self._native.headers

    @property
    def body(self):
        return self._native.body

    def text(self, encoding="utf-8", errors="strict"):
        return self.body.decode(encoding, errors)

    def json(self):
        return _json.loads(self.body)

    def raise_for_status(self):
        if 400 <= self.status < 600:
            raise Error("HTTP_STATUS", f"HTTP status {self.status}")
        return self


def _pairs(value):
    return list(value.items()) if hasattr(value, "items") else list(value)


def _prepare(headers, body, *, params=None, json=_UNSET, form=None, multipart=None,
             basic_auth=None, bearer_token=None, timeout_ms=None, max_redirects=None):
    headers = [(name, value.encode("utf-8") if isinstance(value, str) else bytes(value))
               for name, value in _pairs(headers or [])]
    if sum([body is not None, json is not _UNSET, form is not None, multipart is not None]) > 1:
        raise Error("INVALID_REQUEST", "body, json, form and multipart are mutually exclusive")
    content_type = None
    if json is not _UNSET:
        body = _json.dumps(json, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        content_type = "application/json"
    elif form is not None:
        body = urlencode(_pairs(form), doseq=True).encode()
        content_type = "application/x-www-form-urlencoded"
    elif isinstance(body, str):
        body = body.encode()
    if content_type and not any(name.lower() == "content-type" for name, _ in headers):
        headers.append(("Content-Type", content_type.encode()))
    options = {"params": _pairs(params) if params is not None else []}
    for name, value in (("basic_auth", basic_auth), ("bearer_token", bearer_token),
                        ("timeout_ms", timeout_ms), ("max_redirects", max_redirects)):
        if value is not None:
            options[name] = value
    if multipart is not None:
        chunks, parts, offset = [], [], 0
        for part in multipart:
            unknown = set(part) - {"name", "data", "filename", "content_type"}
            if unknown:
                raise Error("INVALID_REQUEST", "unknown multipart field")
            data = part["data"]
            data = data.encode() if isinstance(data, str) else bytes(data)
            parts.append({"name": part["name"], "offset": offset, "length": len(data),
                          "filename": part.get("filename"), "content_type": part.get("content_type")})
            chunks.append(data)
            offset += len(data)
        body = b"".join(chunks)
        options["multipart"] = parts
    return headers, body, _json.dumps(options, allow_nan=False)


class Client:
    def __init__(self, timeout_ms=30000, max_response_bytes=16777216, **options):
        for name, value in (("timeout_ms", timeout_ms), ("max_response_bytes", max_response_bytes)):
            if type(value) is not int or not 0 < value <= 2**32 - 1:
                raise Error("INVALID_CONFIG", f"{name} must be a positive 32-bit integer")
        try:
            self._client = _native.Client(timeout_ms, max_response_bytes,
                                          _json.dumps(options, allow_nan=False))
        except RuntimeError as error:
            raise _error(error) from None

    def _get_client(self):
        if self._client is None:
            raise Error("CLOSED", "client is closed")
        return self._client

    def request(self, method, url, headers=None, body=None, **options):
        client = self._get_client()
        headers, body, config = _prepare(headers, body, **options)
        try:
            return Response(client.request(method, url, headers, body, config))
        except RuntimeError as error:
            raise _error(error) from None

    async def request_async(self, method, url, headers=None, body=None, **options):
        client = self._get_client()
        headers, body, config = _prepare(headers, body, **options)
        try:
            return Response(await client.request_async(method, url, headers, body, config))
        except RuntimeError as error:
            raise _error(error) from None

    def get(self, url, **options):
        return self.request("GET", url, **options)

    def post(self, url, **options):
        return self.request("POST", url, **options)

    def set_cookie(self, url, value):
        try:
            self._get_client().set_cookie(url, value)
        except RuntimeError as error:
            raise _error(error) from None

    def cookies(self, url):
        try:
            return self._get_client().cookies(url)
        except RuntimeError as error:
            raise _error(error) from None

    def clear_cookies(self):
        self._get_client().clear_cookies()

    def close(self):
        self._client = None

    def __enter__(self):
        self._get_client()
        return self

    def __exit__(self, *_):
        self.close()


class AsyncClient(Client):
    async def request(self, method, url, headers=None, body=None, **options):
        return await self.request_async(method, url, headers, body, **options)

    async def __aenter__(self):
        self._get_client()
        return self

    async def __aexit__(self, *_):
        self.close()


__all__ = ["Client", "AsyncClient", "Response", "Error"]

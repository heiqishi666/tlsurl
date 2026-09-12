"""Exercise installed native packages against the same local HTTP fixture."""

import argparse
import asyncio
import base64
import json
import ssl
import subprocess
import tempfile
import textwrap
import threading
import time
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import tlsurl


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError):
            # Timeout/cancellation tests deliberately close pooled connections.
            pass

    def do_GET(self):
        self.do_POST()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/slow":
            time.sleep(0.25)
        status = 200
        headers = [("X-Duplicate", "one"), ("X-Duplicate", "two")]
        if self.path == "/multipart":
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
            body = json.dumps([{"name": part.get_param("name", header="content-disposition"),
                                "filename": part.get_filename(),
                                "type": part.get_content_type(),
                                "data": base64.b64encode(part.get_payload(decode=True)).decode()}
                               for part in message.iter_parts()]).encode()
        elif urlsplit(self.path).path == "/inspect":
            body = json.dumps({"path": self.path, "body": body.decode(),
                               "authorization": self.headers.get("Authorization"),
                               "content_type": self.headers.get("Content-Type"),
                               "user_agent": self.headers.get("User-Agent")}).encode()
        elif self.path == "/redirect":
            status = 302
            headers.append(("Location", "/cookie"))
            headers.append(("Set-Cookie", "session=works; Path=/"))
        elif self.path == "/cookie":
            body = self.headers.get("Cookie", "").encode()
        elif self.path == "/large":
            body = b"x" * 2048
        elif self.path == "/error":
            status = 404
        elif self.path == "/headers":
            body = json.dumps(self.headers.get_all("X-Input")).encode()
        elif self.path == "/header-names":
            body = json.dumps([k for k in self.headers if k.lower() == "x-input"]).encode()
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def expect_error(action, code):
    try:
        action()
    except RuntimeError as error:
        assert code in str(error), str(error)
    else:
        raise AssertionError(f"expected {code}")


def check_sync(base):
    client = tlsurl.Client()
    payload = bytes(range(256))
    response = client.request("POST", base + "/echo", body=payload)
    assert response.status == 200 and response.body == payload
    assert [v for k, v in response.headers if k == "x-duplicate"] == [b"one", b"two"]
    response = client.request("GET", base + "/headers", [("X-Input", b"one"), ("X-Input", b"two")])
    assert json.loads(response.body) == ["one", "two"]
    response = client.request("GET", base + "/header-names", [("X-Input", b"one"), ("x-InPut", b"two")])
    # Upstream groups repeated names and uses the first spelling for that group.
    assert json.loads(response.body) == ["X-Input", "X-Input"], response.body
    response = client.request("GET", base + "/redirect")
    assert response.url == base + "/cookie" and response.body == b"session=works", (response.status, response.url, response.body)
    assert client.request("GET", base + "/error").status == 404
    expect_error(lambda: tlsurl.Client(0), "INVALID_CONFIG")
    expect_error(lambda: client.request("BAD METHOD", base), "INVALID_REQUEST")
    expect_error(lambda: tlsurl.Client(30).request("GET", base + "/slow"), "TIMEOUT")
    expect_error(lambda: tlsurl.Client(max_response_bytes=1024).request("GET", base + "/large"), "BODY_TOO_LARGE")
    response = client.get(base + "/inspect?existing=1", params=[("q", "a b"), ("q", "中文")])
    assert response.json()["path"] == "/inspect?existing=1&q=a+b&q=%E4%B8%AD%E6%96%87"
    response = client.post(base + "/inspect", json={"word": "中文"})
    assert json.loads(response.json()["body"]) == {"word": "中文"}
    assert response.json()["content_type"] == "application/json"
    assert client.post(base + "/inspect", json=None).json()["body"] == "null"
    assert client.post(base + "/inspect", form=[("q", "a b"), ("q", "中文")]).json()["body"] == "q=a+b&q=%E4%B8%AD%E6%96%87"
    assert client.get(base + "/inspect", basic_auth=("user", "pass")).json()["authorization"] == "Basic dXNlcjpwYXNz"
    assert client.get(base + "/inspect", bearer_token="token").json()["authorization"] == "Bearer token"
    assert client.get(base + "/redirect", max_redirects=0).status == 302
    client.clear_cookies()
    assert client.get(base + "/cookie").body == b""
    assert tlsurl.Client(cookies=False).get(base + "/redirect").body == b""
    with tlsurl.Client(user_agent="tlsurl-test", http_version="1.1") as configured:
        assert configured.get(base + "/inspect").json()["user_agent"] == "tlsurl-test"
    expect_error(lambda: configured.get(base), "CLOSED")
    expect_error(lambda: client.get(base + "/slow", timeout_ms=10), "TIMEOUT")
    expect_error(lambda: client.post(base, body=b"x", json={}), "INVALID_REQUEST")
    expect_error(lambda: client.get(base, basic_auth=("u", "p"), bearer_token="t"), "INVALID_REQUEST")
    expect_error(lambda: tlsurl.Client(connect_timeout_ms=0), "INVALID_CONFIG")
    expect_error(lambda: tlsurl.Client(unknown=True), "INVALID_CONFIG")
    try:
        client.get(base + "/error").raise_for_status()
    except tlsurl.Error as error:
        assert error.code == "HTTP_STATUS"
    else:
        raise AssertionError("HTTP status error missing")
    # This fixture acts as a forward proxy; the invalid destination must never be resolved.
    assert tlsurl.Client(proxy=base).get("http://not-a-real-host.invalid/inspect").json()["path"] == "http://not-a-real-host.invalid/inspect"
    client.set_cookie(base, "manual=value; Path=/")
    assert client.cookies(base) == [("manual", "value")]
    assert client.get(base + "/cookie").text() == "manual=value"
    client.set_cookie(base, "manual=gone; Path=/; Max-Age=0")
    assert client.cookies(base) == []
    client.set_cookie(base, "secure=hidden; Secure; Path=/")
    assert client.cookies(base) == []
    response = client.post(base + "/multipart", multipart=[
        {"name": "field", "data": "中文"},
        {"name": "file", "data": bytes(range(256)), "filename": "data.bin", "content_type": "application/octet-stream"},
    ])
    parts = response.json()
    assert parts[0]["name"] == "field" and base64.b64decode(parts[0]["data"]) == "中文".encode()
    assert parts[1]["filename"] == "data.bin" and base64.b64decode(parts[1]["data"]) == bytes(range(256))
    expect_error(lambda: client.post(base, multipart=[], json={}), "INVALID_REQUEST")
    expect_error(lambda: client.get(base, headers={"Authorization": "custom"}, bearer_token="token"), "INVALID_REQUEST")


async def check_async(base):
    client = tlsurl.AsyncClient()
    responses = await asyncio.gather(*[
        client.request("POST", base + "/echo", body=bytes([i])) for i in range(8)
    ])
    assert [r.body for r in responses] == [bytes([i]) for i in range(8)]
    task = asyncio.create_task(client.request("GET", base + "/slow"))
    await asyncio.sleep(0.02)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("request was not cancelled")
    assert (await client.request("GET", base + "/echo")).status == 200
    async with tlsurl.AsyncClient() as configured:
        assert (await configured.post(base + "/echo", json={"async": True})).json() == {"async": True}
    try:
        await configured.get(base)
    except tlsurl.Error as error:
        assert error.code == "CLOSED"
    else:
        raise AssertionError("closed async client accepted request")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True)
    parser.add_argument("--https", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    support = Path(__file__).resolve().parents[1] / "support"
    with tempfile.TemporaryDirectory() as cert_dir:
        cert = Path(cert_dir) / "cert.pem"
        key = Path(cert_dir) / "key.pem"
        cert.write_text(ssl.DER_cert_to_PEM_cert((support / "server.cert").read_bytes()))
        key_body = base64.b64encode((support / "server.key").read_bytes()).decode("ascii")
        key.write_text("-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(textwrap.wrap(key_body, 64)) + "\n-----END RSA PRIVATE KEY-----\n")
        context.load_cert_chain(cert, key)
    tls_server.socket = context.wrap_socket(tls_server.socket, server_side=True)
    tls_thread = threading.Thread(target=tls_server.serve_forever, daemon=True)
    tls_thread.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    tls_base = f"https://127.0.0.1:{tls_server.server_port}"
    try:
        check_sync(base)
        asyncio.run(check_async(base))
        try:
            tlsurl.Client().request("GET", tls_base)
        except RuntimeError:
            pass
        else:
            raise AssertionError("untrusted TLS certificate was accepted")
        assert tlsurl.Client(verify=False).get(tls_base).status == 200
        subprocess.run([
            "node", str(Path(__file__).with_name("smoke.cjs")), base,
            str(Path(args.node_module).resolve()), tls_base, *(["--https"] if args.https else []),
        ], check=True)
        if args.https:
            assert ssl.OPENSSL_VERSION
            assert tlsurl.Client().request("GET", "https://example.com").status == 200
        print("Python sync/async and Node package integration checks passed")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        tls_server.shutdown()
        tls_server.server_close()
        tls_thread.join()


if __name__ == "__main__":
    main()

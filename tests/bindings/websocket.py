"""Exercise installed WebSocket APIs with a standard ws server and local TLS CA."""
import argparse
import asyncio
import json
from pathlib import Path
import queue
import subprocess
import threading

import tlsurl
from stream import state


def check_sync(base, secure):
    ca = Path(__file__).with_name("certs").joinpath("ca.pem").read_text()
    with tlsurl.Client(ca_pem=ca) as client:
        client.set_cookie(secure.replace("wss:", "https:"), "ws_cookie=ok; Secure; Path=/")
        with client.websocket(secure + "/headers?id=py-wss", protocols=["echo"], headers={"X-Test": "yes"}) as socket:
            assert socket.protocol == "echo"
            headers = json.loads(socket.recv().data)
            assert headers["x-test"] == "yes" and headers["cookie"] == "ws_cookie=ok"
            socket.send("你好")
            message = socket.recv()
            assert message.kind == "text" and message.data.decode() == "你好"
            socket.send(bytes(range(256)))
            assert socket.recv().data == bytes(range(256))
            socket.ping(b"hello")
            message = socket.recv()
            assert message.kind == "pong" and message.data == b"hello"
            socket.send("server-ping")
            assert socket.recv().kind == "ping"
            state(base.replace("ws:", "http:"), "py-wss", lambda s: s and s["pongs"] == 1)
            socket.send("fragment")
            assert socket.recv().data == b"firstsecond"
            for call in [lambda: socket.close(1005), lambda: socket.ping(b"x" * 126)]:
                try:
                    call()
                except tlsurl.Error as error:
                    assert error.code == "INVALID_REQUEST"
                else:
                    raise AssertionError("invalid websocket control frame accepted")
            socket.close(4000, "done")
        final = state(base.replace("ws:", "http:"), "py-wss", lambda s: s and s["closed"] and s["code"] is not None)
        assert final["code"] == 4000 and final["reason"] == "done"
        with client.websocket(base + "/echo?id=py-remote") as socket:
            socket.send("server-close")
            message = socket.recv()
            assert (message.kind, message.code, message.data) == ("close", 4001, b"bye")
        with client.websocket(base + "/echo?id=py-limit", max_message_bytes=1024) as socket:
            socket.send("large")
            try:
                socket.recv()
            except tlsurl.Error:
                pass
            else:
                raise AssertionError("oversized message accepted")
        with client.websocket(base + "/echo?id=py-timeout", operation_timeout_ms=100) as socket:
            try:
                socket.recv()
            except tlsurl.Error as error:
                assert error.code == "TIMEOUT"
            else:
                raise AssertionError("websocket receive timeout did not fire")
        for url, options in [(base + "/reject", {}), (base + "/echo", {"protocols": ["invalid,token"]})]:
            try:
                client.websocket(url, **options)
            except tlsurl.Error:
                pass
            else:
                raise AssertionError("invalid handshake accepted")
    try:
        tlsurl.Client().websocket(secure + "/echo")
    except tlsurl.Error:
        pass
    else:
        raise AssertionError("untrusted wss certificate accepted")


async def check_async(base):
    async with tlsurl.AsyncClient() as client:
        async with await client.websocket(base + "/echo?id=py-duplex") as socket:
            pending = asyncio.create_task(socket.recv())
            await asyncio.sleep(0.02)
            await socket.send("duplex")
            assert (await asyncio.wait_for(pending, 2)).data == b"duplex"
            pending = asyncio.create_task(socket.recv())
            await asyncio.sleep(0.02)
            await socket.close()
            try:
                await pending
            except tlsurl.Error as error:
                assert error.code == "CLOSED"
            else:
                raise AssertionError("close did not interrupt receive")
        async with await client.websocket(base + "/echo?id=py-iterator") as socket:
            await socket.send("one")
            async for message in socket:
                assert message.data == b"one"
                break
        for attempt in range(10):
            socket = await client.websocket(base + f"/echo?id=py-abort-{attempt}")
            pending = asyncio.create_task(socket.recv())
            await asyncio.sleep(0 if attempt % 2 == 0 else 0.005)
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("receive cancellation failed")
            await asyncio.to_thread(state, base.replace("ws:", "http:"), f"py-abort-{attempt}", lambda s: s and s["closed"])
        pending = asyncio.create_task(client.websocket(base + "/hang?id=py-handshake"))
        await asyncio.to_thread(state, base.replace("ws:", "http:"), "py-handshake", lambda s: s is not None)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("handshake cancellation failed")
        await asyncio.to_thread(state, base.replace("ws:", "http:"), "py-handshake", lambda s: s and s["closed"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True)
    args = parser.parse_args()
    server = subprocess.Popen(["node", str(Path(__file__).with_name("websocket_server.cjs"))], stdout=subprocess.PIPE, text=True)
    ready = queue.Queue()
    threading.Thread(target=lambda: ready.put(server.stdout.readline()), daemon=True).start()
    try:
        ports = json.loads(ready.get(timeout=15))
        base = f"ws://127.0.0.1:{ports['port']}"
        secure = f"wss://localhost:{ports['tlsPort']}"
        check_sync(base, secure)
        asyncio.run(check_async(base))
        subprocess.run(["node", str(Path(__file__).with_name("websocket.cjs")), base, secure, str(Path(args.node_module).resolve())], check=True, timeout=60)
        print("Python sync/async WS/WSS, frames, duplex, close, limits and cancellation checks passed")
    finally:
        server.terminate()
        server.wait(timeout=10)
        server.stdout.close()


if __name__ == "__main__":
    main()

"""Validate pull streaming and cancellation against observable server sockets."""
import argparse
import asyncio
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from urllib.request import urlopen

import tlsurl


def state(base, identifier, predicate):
    for _ in range(100):
        with urlopen(f"{base}/state?id={identifier}", timeout=2) as response:
            value = json.load(response)
        if predicate(value):
            return value
        time.sleep(0.02)
    raise AssertionError(f"server state did not converge: {identifier}")


def check_sync(base):
    with tlsurl.Client(max_response_bytes=1024) as client:
        with client.stream("GET", f"{base}/stream?id=py-full") as response:
            assert response.status == 200 and response.http_version == "1.1"
            assert ("x-stream", b"yes") in response.headers
            result = b"".join(response)
            assert result == bytes(range(256)) * 4096
        huge_size = 128 * 1024 * 1024
        with client.stream("GET", f"{base}/stream?id=py-pull&size={huge_size}") as response:
            assert response.next_chunk()
            time.sleep(0.1)
            assert state(base, "py-pull", lambda s: s and s["produced"] > 0)["produced"] < huge_size
        state(base, "py-pull", lambda s: s and s["closed"])
        response = client.stream("GET", f"{base}/hold?id=py-close")
        outcome = queue.Queue()
        def read():
            try:
                response.next_chunk()
                outcome.put("unexpected success")
            except tlsurl.Error as error:
                outcome.put(error.code)
        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        response.close()
        assert outcome.get(timeout=3) == "CANCELLED"
        worker.join(timeout=3)
        state(base, "py-close", lambda s: s and s["closed"])
        with client.stream("GET", f"{base}/hold?id=py-timeout", timeout_ms=100) as response:
            try:
                response.next_chunk()
            except tlsurl.Error as error:
                assert error.code == "TIMEOUT"
            else:
                raise AssertionError("stream body timeout did not fire")


async def check_async(base):
    async with tlsurl.AsyncClient(max_response_bytes=1024) as client:
        async with await client.stream("GET", f"{base}/stream?id=py-async") as response:
            chunks = [chunk async for chunk in response]
            assert b"".join(chunks) == bytes(range(256)) * 4096
        for i in range(10):
            identifier = f"py-cancel-{i}"
            pending = asyncio.create_task(client.get(f"{base}/delayed?id={identifier}"))
            await asyncio.to_thread(state, base, identifier, lambda s: s is not None)
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("request cancellation did not propagate")
            await asyncio.to_thread(state, base, identifier, lambda s: s and s["closed"])
        response = await client.stream("GET", f"{base}/hold?id=py-asynccancel")
        pending = asyncio.create_task(response.next_chunk_async())
        await asyncio.sleep(0.05)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("stream cancellation did not propagate")
        await asyncio.to_thread(state, base, "py-asynccancel", lambda s: s and s["closed"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True)
    args = parser.parse_args()
    server = subprocess.Popen(["node", str(Path(__file__).with_name("stream_server.cjs"))], stdout=subprocess.PIPE, text=True)
    ready = queue.Queue()
    threading.Thread(target=lambda: ready.put(server.stdout.readline()), daemon=True).start()
    try:
        base = f"http://127.0.0.1:{json.loads(ready.get(timeout=15))['port']}"
        check_sync(base)
        asyncio.run(check_async(base))
        subprocess.run(["node", str(Path(__file__).with_name("stream.cjs")), base, str(Path(args.node_module).resolve())], check=True, timeout=60)
        print("Python sync/async streaming, backpressure and transport cancellation checks passed")
    finally:
        server.terminate()
        server.wait(timeout=10)
        server.stdout.close()


if __name__ == "__main__":
    main()

"""Exercise file upload through installed packages, with bounded consumer memory."""
import argparse
import asyncio
import base64
from email.parser import BytesParser
from email.policy import default
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading

import tlsurl
from stream import state


def check_sync(base, directory):
    file = directory / "payload.bin"
    payload = file.read_bytes()
    with tlsurl.Client() as client:
        result = client.post(f"{base}/upload?id=py-file", body_file=file).json()
        assert result["size"] == len(payload) == int(result["length"])
        assert result["sha256"] == hashlib.sha256(payload).hexdigest()
        assert client.post(f"{base}/upload?id=py-empty", body_file=directory / "empty.bin").json()["size"] == 0
        result = client.post(f"{base}/upload-multipart?id=py-multipart", multipart=[
            {"name": "note", "data": "hello"},
            {"name": "file", "file": file, "content_type": "application/octet-stream"},
        ]).json()
        body = base64.b64decode(result["body"])
        assert len(body) == int(result["length"])
        message = BytesParser(policy=default).parsebytes(f"Content-Type: {result['contentType']}\r\n\r\n".encode() + body)
        parts = list(message.iter_parts())
        assert parts[0].get_payload(decode=True) == b"hello"
        assert parts[1].get_filename() == "payload.bin"
        assert parts[1].get_payload(decode=True) == payload
        for options, code in [
            ({"body_file": directory / "missing"}, "FILE_IO"),
            ({"body_file": file, "body": b"conflict"}, "INVALID_REQUEST"),
            ({"body_file": file, "headers": {"Content-Length": "1"}}, "INVALID_REQUEST"),
            ({"multipart": [{"name": "bad", "file": file, "data": b"conflict"}]}, "INVALID_REQUEST"),
        ]:
            try:
                client.post(base + "/upload", **options)
            except tlsurl.Error as error:
                assert error.code == code
            else:
                raise AssertionError("invalid upload accepted")
        assert client.post(base + "/upload-redirect", body_file=file).status == 307


async def check_async(base, directory):
    async with tlsurl.AsyncClient() as client:
        result = (await client.post(base + "/upload?id=py-async-file", body_file=directory / "payload.bin")).json()
        assert result["size"] == (directory / "payload.bin").stat().st_size
        pending = asyncio.create_task(client.post(base + "/upload-slow?id=py-upload-cancel", body_file=directory / "huge.bin"))
        await asyncio.to_thread(state, base, "py-upload-cancel", lambda s: s and s.get("received", 0) > 0)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("file upload cancellation failed")
        final = await asyncio.to_thread(state, base, "py-upload-cancel", lambda s: s and s["closed"])
        assert final["received"] < (directory / "huge.bin").stat().st_size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True)
    args = parser.parse_args()
    server = subprocess.Popen(["node", str(Path(__file__).with_name("stream_server.cjs"))], stdout=subprocess.PIPE, text=True)
    ready = queue.Queue()
    threading.Thread(target=lambda: ready.put(server.stdout.readline()), daemon=True).start()
    try:
        base = f"http://127.0.0.1:{json.loads(ready.get(timeout=15))['port']}"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "payload.bin").write_bytes(bytes(range(256)) * 1024)
            (directory / "empty.bin").write_bytes(b"")
            with (directory / "huge.bin").open("wb") as output:
                output.truncate(128 * 1024 * 1024)
            check_sync(base, directory)
            asyncio.run(check_async(base, directory))
            subprocess.run(["node", str(Path(__file__).with_name("upload.cjs")), base, str(Path(args.node_module).resolve()), temporary], check=True, timeout=60)
        print("Python sync/async raw/multipart file upload and cancellation checks passed")
    finally:
        server.terminate()
        server.wait(timeout=10)
        server.stdout.close()


if __name__ == "__main__":
    main()

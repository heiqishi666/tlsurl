"""Bounded local soak test; reports actual counts, RSS and server connection release."""
import argparse
import asyncio
import gc
from functools import cache
import json
import os
from pathlib import Path
import platform
import queue
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

from node_runtime import node_executable

import tlsurl


@cache
def windows_memory_reader():
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ["peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile"]]
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = wintypes.HANDLE
    read = ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    return ctypes, Counters, process, read


def rss_bytes():
    if sys.platform == "win32":
        ctypes, Counters, process, read = windows_memory_reader()
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not read(process(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError()
        return counters.working
    if sys.platform == "linux":
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())])) * 1024


def metrics(base):
    with urlopen(base + "/metrics", timeout=5) as response:
        return json.load(response)


async def soak(base, seconds, output):
    client = tlsurl.AsyncClient()
    requests = streams = cancellations = rounds = 0
    expected = bytes(range(256)) * 4
    async def request():
        nonlocal requests
        assert (await client.get(base + "/stream?size=1024&id=stress-python")).body == expected
        requests += 1
    async def batch():
        nonlocal streams, cancellations, rounds
        await asyncio.gather(*(request() for _ in range(16)))
        async with await client.stream("GET", base + "/stream?size=65536&id=stress-python-stream") as response:
            size = 0
            async for chunk in response:
                size += len(chunk)
            assert size == 65536
        streams += 1
        rounds += 1
        if rounds % 10 == 0:
            response = await client.stream("GET", base + "/hold?id=stress-python-cancel")
            pending = asyncio.create_task(response.next_chunk_async())
            await asyncio.sleep(0)
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("cancellation did not propagate")
            cancellations += 1
    for _ in range(5):
        await batch()
    gc.collect()
    baseline = peak = rss_bytes()
    start = time.monotonic()
    next_log = start + 30
    initial = requests, streams, cancellations
    while time.monotonic() - start < seconds:
        await batch()
        peak = max(peak, rss_bytes())
        if time.monotonic() >= next_log:
            print(json.dumps({"language": "python", "elapsedSeconds": round(time.monotonic() - start), "requests": requests - initial[0], "rssBytes": rss_bytes(), "errors": 0}), flush=True)
            next_log += 30
    active = await asyncio.to_thread(metrics, base)
    assert active["connections"] < requests / 2, "connection pool was not reused"
    client.close()
    for _ in range(100):
        final = await asyncio.to_thread(metrics, base)
        if final["activeConnections"] <= 1:
            break
        await asyncio.sleep(0.05)
    assert final["activeConnections"] <= 1, f"connections retained after close: {final}"
    gc.collect()
    peak = max(peak, rss_bytes())
    assert peak - baseline < 128 * 1024 * 1024, f"excessive RSS growth: {peak - baseline}"
    report = {"language": "python", "runtime": platform.python_version(), "elapsedSeconds": time.monotonic() - start,
              "requests": requests - initial[0], "streams": streams - initial[1], "cancellations": cancellations - initial[2],
              "errors": 0, "baselineRssBytes": baseline, "peakRssBytes": peak, "finalRssBytes": rss_bytes(), "server": final}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True)
    parser.add_argument("--seconds", type=int, default=30, help="duration per language")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("--seconds must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([node_executable(), str(Path(__file__).with_name("stream_server.cjs"))], stdout=subprocess.PIPE, text=True)
    ready = queue.Queue()
    threading.Thread(target=lambda: ready.put(server.stdout.readline()), daemon=True).start()
    try:
        base = f"http://127.0.0.1:{json.loads(ready.get(timeout=15))['port']}"
        asyncio.run(soak(base, args.seconds, args.output / "python.json"))
        subprocess.run([node_executable(), "--expose-gc", str(Path(__file__).with_name("stress.cjs")), base,
                        str(Path(args.node_module).resolve()), str(args.seconds), str((args.output / "node.json").resolve())], check=True, timeout=args.seconds + 60)
    finally:
        server.terminate()
        server.wait(timeout=10)
        server.stdout.close()


if __name__ == "__main__":
    main()

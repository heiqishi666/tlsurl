"""Install actual npm tarballs through an isolated, loopback-only registry."""

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
from urllib.parse import unquote, urlsplit


def install(artifacts, consumer):
    packages = {}
    for archive in sorted(artifacts.rglob("*.tgz")):
        with tarfile.open(archive) as tar:
            manifest = json.load(tar.extractfile("package/package.json"))
            names = tar.getnames()
        name = manifest["name"]
        if name in packages:
            raise ValueError(f"duplicate package: {name}")
        if name == "tlsurl" and any(n.endswith(".node") for n in names):
            raise ValueError("main package must not contain native binaries")
        packages[name] = (manifest, archive.read_bytes())
    main = packages["tlsurl"][0]
    expected = main["optionalDependencies"]
    assert len(expected) == 5, expected
    for name, (manifest, _) in packages.items():
        if name != "tlsurl":
            assert expected[name] == manifest["version"], name

    class Registry(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path).strip("/")
            name = path.split("/")[0]
            if name not in packages:
                self.send_error(404)
                return
            manifest, blob = packages[name]
            if path == name:
                version = manifest["version"]
                published = dict(manifest, dist={
                    "tarball": f"http://127.0.0.1:{self.server.server_port}/{name}/-/package.tgz",
                    "integrity": "sha512-" + base64.b64encode(hashlib.sha512(blob).digest()).decode(),
                })
                blob = json.dumps({"name": name, "dist-tags": {"latest": version},
                                   "versions": {version: published}}).encode()
            elif path != f"{name}/-/package.tgz":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    consumer.mkdir(parents=True, exist_ok=False)
    (consumer / "package.json").write_text('{"name":"tlsurl-consumer","private":true}')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as cache:
            subprocess.run([
                shutil.which("npm.cmd") or shutil.which("npm"), "install",
                f"tlsurl@{main['version']}", "--ignore-scripts", "--no-audit", "--no-fund",
                "--include=optional", "--cache", cache,
                "--registry", f"http://127.0.0.1:{server.server_port}",
            ], cwd=consumer, check=True)
        installed = [p.name for p in (consumer / "node_modules").glob("tlsurl-*")]
        assert len(installed) == 1, installed
        assert installed[0] in expected, installed
        subprocess.run(["node", "-e", "const m=require('tlsurl'); new m.Client()"],
                       cwd=consumer, check=True)
        subprocess.run(["node", "--input-type=module", "-e",
                        "import {Client} from 'tlsurl'; new Client()"], cwd=consumer, check=True)
        print(f"Automatic platform selection passed: {installed[0]}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--consumer", type=Path, required=True)
    args = parser.parse_args()
    install(args.artifacts.resolve(), args.consumer.resolve())

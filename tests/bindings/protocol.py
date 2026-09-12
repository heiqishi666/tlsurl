"""Verify actual TLS handshakes, mTLS and HTTP/2 settings of installed packages."""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import threading

import tlsurl


def rejected(action):
    try:
        action()
    except tlsurl.Error:
        return
    raise AssertionError("expected TLS/configuration rejection")


def check(ports):
    certs = Path(__file__).with_name("certs")
    ca = (certs / "ca.pem").read_text()
    normal = f"https://localhost:{ports['normal']}"
    client = tlsurl.Client(ca_pem=ca)
    response = client.get(normal)
    assert response.http_version == "2", response.http_version
    assert response.json()["alpn"] == "h2"
    rejected(lambda: tlsurl.Client(2000).get(normal))
    rejected(lambda: client.get(f"https://127.0.0.1:{ports['normal']}"))
    response = tlsurl.Client(ca_pem=ca, tls={"alpn": ["http/1.1"], "min_version": "1.2", "max_version": "1.2",
                                            "cipher_list": "ECDHE-RSA-AES128-GCM-SHA256", "curves_list": "P-256"}).get(normal)
    assert response.http_version == "1.1"
    assert response.json()["tlsVersion"] == "TLSv1.2"
    assert response.json()["cipher"] == "ECDHE-RSA-AES128-GCM-SHA256"
    tls12 = f"https://localhost:{ports['tls12']}"
    rejected(lambda: tlsurl.Client(2000, ca_pem=ca, tls={"min_version": "1.3"}).get(tls12))
    rejected(lambda: tlsurl.Client(tls={"min_version": "1.3", "max_version": "1.2"}))
    rejected(lambda: tlsurl.Client(http2={"max_frame_size": 1}))
    rejected(lambda: tlsurl.Client(tls={"alpn": ["h3"]}))
    order = ["method", "path", "authority", "scheme"]
    response = tlsurl.Client(ca_pem=ca, http2={"initial_window_size": 777777, "header_table_size": 1234,
                                             "enable_push": False, "pseudo_order": order}).get(normal)
    details = response.json()
    assert details["settings"]["initialWindowSize"] == 777777, details
    assert details["settings"]["headerTableSize"] == 1234, details
    assert details["settings"]["enablePush"] is False
    assert [h for h in details["headers"] if h.startswith(":")] == [":" + h for h in order], details
    mtls = f"https://localhost:{ports['mtls']}"
    rejected(lambda: tlsurl.Client(2000, ca_pem=ca).get(mtls))
    identity = {"certificate_pem": (certs / "client.pem").read_text(),
                "private_key_pem": (certs / "client-key.pem").read_text()}
    assert tlsurl.Client(ca_pem=ca, identity=identity).get(mtls).json()["authorized"] is True
    print("Python TLS trust, hostname, version, ALPN, cipher, mTLS and HTTP/2 wire checks passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", required=True)
    args = parser.parse_args()
    server = subprocess.Popen(["node", str(Path(__file__).with_name("protocol_server.cjs"))],
                              stdout=subprocess.PIPE, text=True)
    try:
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(server.stdout.readline()), daemon=True).start()
        ports = json.loads(ready.get(timeout=15))
        check(ports)
        subprocess.run(["node", str(Path(__file__).with_name("protocol.cjs")),
                        str(Path(args.node_module).resolve()), json.dumps(ports)], check=True, timeout=60)
    finally:
        server.terminate()
        server.wait(timeout=10)
        server.stdout.close()


if __name__ == "__main__":
    main()

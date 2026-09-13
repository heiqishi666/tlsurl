"""Loopback ClientHello capture: independent JA3/JA4 calculation, no external service.
Specifications: github.com/salesforce/ja3 and
https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4.md
"""
import hashlib
import json
from pathlib import Path
import queue
import select
import socket
import socketserver
import subprocess
import threading

from node_runtime import node_executable
import tlsurl


def words(data):
    assert len(data) % 2 == 0
    return [int.from_bytes(data[i:i+2], 'big') for i in range(0, len(data), 2)]


def clean(values):
    return [v for v in values if not (v & 0x0f0f == 0x0a0a and v >> 8 == v & 255)]


def fingerprint(hello):
    assert hello[0] == 1
    data = memoryview(hello)[4:]
    version = int.from_bytes(data[:2], 'big')
    offset = 34
    offset += 1 + data[offset]
    count = int.from_bytes(data[offset:offset+2], 'big')
    ciphers = clean(words(data[offset+2:offset+2+count]))
    offset += 2 + count
    offset += 1 + data[offset]
    end = offset + 2 + int.from_bytes(data[offset:offset+2], 'big')
    offset += 2
    extensions = {}
    while offset < end:
        kind, size = words(data[offset:offset+4])
        extensions[kind] = bytes(data[offset+4:offset+4+size])
        offset += 4 + size
    assert offset == end == len(data)
    ids = clean(extensions)
    curves = clean(words(extensions.get(10, b'\0\0')[2:]))
    points = list(extensions.get(11, b'\0')[1:])
    raw3 = ','.join([str(version), *('-'.join(map(str, v)) for v in (ciphers, ids, curves, points))])
    versions = clean(words(extensions[43][1:])) if 43 in extensions else [version]
    alpn = extensions.get(16, b'\0\0\0')
    first = alpn[3:3+alpn[2]]
    if first:
        edges = bytes([first[0], first[-1]])
        alpn_id = edges.decode('ascii') if all(chr(v).isascii() and chr(v).isalnum() for v in edges) else first.hex()[0] + first.hex()[-1]
    else:
        alpn_id = '00'
    prefix = 't' + {0x304:'13', 0x303:'12'}.get(max(versions), '00') + ('d' if 0 in ids else 'i')
    prefix += f'{min(len(ciphers), 99):02}{min(len(ids), 99):02}' + alpn_id
    hexes = lambda values: ','.join(f'{v:04x}' for v in values)
    digest = lambda value: hashlib.sha256(value.encode()).hexdigest()[:12] if value else '000000000000'
    ext = hexes(sorted(v for v in ids if v not in (0, 16)))
    sigs = clean(words(extensions.get(13, b'\0\0')[2:]))
    raw4c = ext + ('_' + hexes(sigs) if sigs else '')
    return {'ja3': hashlib.md5(raw3.encode()).hexdigest(),
            'ja4': prefix + '_' + digest(hexes(sorted(ciphers))) + '_' + digest(raw4c),
            'ciphers': ciphers, 'versions': versions}


def check_reference_vector():
    # Published JA4 example; build a ClientHello fixture from its documented fields.
    ciphers = bytes.fromhex('130113021303c02bc02fc02cc030cca9cca8c013c014009c009d002f0035')
    ids = [27, 0, 51, 16, 17513, 23, 45, 13, 5, 35, 18, 43, 65281, 11, 10, 21]
    payloads = {16: b'\x00\x03\x02h2', 43: b'\x02\x03\x04',
                13: bytes.fromhex('001004030804040105030805050108060601'),
                10: b'\0\0', 11: b'\0'}
    extensions = b''.join(v.to_bytes(2, 'big') + len(payloads.get(v, b'')).to_bytes(2, 'big')
                          + payloads.get(v, b'') for v in ids)
    body = b'\x03\x03' + bytes(32) + b'\0' + len(ciphers).to_bytes(2, 'big') + ciphers + b'\x01\0'
    body += len(extensions).to_bytes(2, 'big') + extensions
    actual = fingerprint(b'\x01' + len(body).to_bytes(3, 'big') + body)
    assert actual['ja4'] == 't13d1516h2_8daaf6152771_e5627efa2ab1', actual


class Capture(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with socket.create_connection(('127.0.0.1', self.server.backend), timeout=10) as upstream:
                downstream = self.request
                pending = bytearray()
                hello = bytearray()
                captured = False
                while True:
                    ready, _, _ = select.select([downstream, upstream], [], [], 10)
                    if not ready:
                        return
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        if source is downstream and not captured:
                            pending.extend(chunk)
                            while len(pending) >= 5:
                                size = int.from_bytes(pending[3:5], 'big')
                                if len(pending) < size + 5:
                                    break
                                assert pending[0] == 22
                                hello.extend(pending[5:size+5])
                                del pending[:size+5]
                                if len(hello) >= 4 and len(hello) >= 4 + int.from_bytes(hello[1:4], 'big'):
                                    self.server.results.put(fingerprint(hello))
                                    captured = True
                                    break
                        (upstream if source is downstream else downstream).sendall(chunk)
        except Exception as error:
            self.server.results.put(error)


def check(ports, node_module):
    check_reference_vector()
    ca = Path(__file__).with_name('certs').joinpath('ca.pem').read_text(encoding='utf-8')
    servers = [Capture(('127.0.0.1', 0), Forward) for _ in range(2)]
    results = queue.Queue()
    for server in servers:
        server.backend = ports['normal']
        server.results = results
        threading.Thread(target=server.serve_forever, daemon=True).start()
    urls = [f'https://localhost:{s.server_address[1]}' for s in servers]
    def take():
        result = results.get(timeout=10)
        if isinstance(result, Exception):
            raise result
        assert 0x304 in result['versions'] and min(result['versions']) >= 0x303, result
        return result
    try:
        python = []
        for seed in range(16):
            with tlsurl.Client(random_tls=True, random_tls_seed=seed, ca_pem=ca) as client:
                for url in urls:
                    assert client.get(url).json()["tlsVersion"] == "TLSv1.3"
                    python.append(take())
                assert client.get(f"https://localhost:{ports['tls12']}").json()["tlsVersion"] == "TLSv1.2"
            assert python[-1] == python[-2], (seed, python[-2:])
        for key in ('ja3', 'ja4'):
            assert len({v[key] for v in python}) >= 12, python
        for options in ({'random_tls': True, 'tls': {}}, {'random_tls': True, 'profile': 'chrome_149'},
                        {'random_tls': True, 'platform': 'windows'}, {'random_tls_seed': 1},
                        {'random_tls': True, 'random_tls_seed': -1}, {'random_tls': 1},
                        {'random_tls': True, 'random_tls_seed': 2**32}, {'random_tls': True, 'random_tls_seed': True}):
            try:
                tlsurl.Client(**options)
            except tlsurl.Error as error:
                assert error.code == 'INVALID_CONFIG', error
            else:
                raise AssertionError(options)
        for _ in range(4):
            with tlsurl.Client(random_tls=True, ca_pem=ca) as client:
                assert client.get(urls[0]).status == 200
                take()
        subprocess.run([node_executable(), str(Path(__file__).with_name('random_tls.cjs')),
                        str(Path(node_module).resolve()), json.dumps(urls), ca, f"https://localhost:{ports['tls12']}"], check=True, timeout=90)
        node = [take() for _ in python]
        assert node == python, (node, python)
        print('Random TLS: 16 seeds, stable fresh connections, Python/Node identical JA3+JA4, valid TLS and rejected conflicts passed')
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()

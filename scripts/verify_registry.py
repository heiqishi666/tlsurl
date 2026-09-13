"""Read back public registry archives and compare their bytes with the accepted candidate."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import urlopen

from collect_native import contents
from prepare_release import verify
from publish_packages import remote_json


def check_download(url, local, allowed_host):
    if urlparse(url).scheme != "https" or urlparse(url).hostname != allowed_host:
        raise ValueError("unexpected registry download URL")
    digest = hashlib.sha256()
    size = 0
    with urlopen(url, timeout=60) as response:
        if urlparse(response.url).scheme != "https" or urlparse(response.url).hostname != allowed_host:
            raise ValueError("unexpected registry download redirect")
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > local.stat().st_size:
                raise ValueError(f"registry archive is larger than candidate: {local.name}")
            digest.update(chunk)
    expected = hashlib.sha256(local.read_bytes()).hexdigest()
    if size != local.stat().st_size or digest.hexdigest() != expected:
        raise ValueError(f"registry bytes differ from candidate: {local.name}")
    return {"file": local.name, "sha256": expected, "bytes": size, "url": url}


def check(directory, commit, registry="both"):
    if registry not in ("pypi", "npm", "both"):
        raise ValueError("unknown registry")
    report = verify(directory, commit)
    results = []
    for filename in report["npm"] if registry != "pypi" else []:
        archive = directory / filename
        manifest = json.loads(contents(archive)["package/package.json"])
        remote = remote_json(f"https://registry.npmjs.org/{quote(manifest['name'], safe='')}/{quote(report['version'], safe='')}")
        if remote is None:
            raise ValueError(f"npm package not publicly available: {manifest['name']}")
        results.append(check_download(remote["dist"]["tarball"], archive, "registry.npmjs.org"))
    if registry != "npm":
        remote = remote_json(f"https://pypi.org/pypi/tlsurl/{quote(report['version'], safe='')}/json")
        if remote is None:
            raise ValueError("PyPI version not publicly available")
        files = {item["filename"]: item for item in remote["urls"]}
        wheels = list(directory.glob("*.whl"))
        if set(files) != {wheel.name for wheel in wheels}:
            raise ValueError("PyPI published wheel set differs from candidate")
        for wheel in wheels:
            results.append(check_download(files[wheel.name]["url"], wheel, "files.pythonhosted.org"))
    return {"version": report["version"], "commit": commit, "registry": registry, "files": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry", choices=["pypi", "npm", "both"], default="both")
    args = parser.parse_args()
    result = check(args.directory, args.commit, args.registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(result['files'])} public registry archives against candidate bytes")

"""Hash-checked registry retry handling; npm writes require explicit --apply."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from collect_native import contents
from prepare_release import verify


def remote_json(url):
    try:
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def npm(directory, report, apply=False):
    pending = []
    for name in report["npm"]:
        archive = directory / name
        manifest = json.loads(contents(archive)["package/package.json"])
        package = manifest["name"]
        remote = remote_json(f"https://registry.npmjs.org/{quote(package, safe='')}/{quote(report['version'], safe='')}")
        if remote is not None:
            expected = "sha512-" + base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
            if remote.get("dist", {}).get("integrity") != expected:
                raise ValueError(f"published npm content differs: {package}@{report['version']}")
            print(f"Already published with identical bytes: {package}")
        else:
            pending.append(archive)
    # Preflight every package before writing any; platform packages precede main.
    executable = shutil.which("npm.cmd") or shutil.which("npm")
    if not executable:
        raise RuntimeError("npm CLI is required")
    for archive in pending:
        args = [executable, "publish", str(archive.resolve()), "--ignore-scripts", "--access", "public",
                "--registry", "https://registry.npmjs.org"]
        args += ["--provenance"] if apply else ["--dry-run"]
        subprocess.run(args, check=True)


def pypi(directory, report, pending):
    remote = remote_json(f"https://pypi.org/pypi/tlsurl/{quote(report['version'], safe='')}/json")
    existing = {} if remote is None else {item["filename"]: item["digests"]["sha256"] for item in remote["urls"]}
    wheels = list(directory.glob("*.whl"))
    if set(existing) - {wheel.name for wheel in wheels}:
        raise ValueError("PyPI version contains unexpected files")
    selected = []
    for wheel in wheels:
        if wheel.name in existing:
            if existing[wheel.name] != hashlib.sha256(wheel.read_bytes()).hexdigest():
                raise ValueError(f"published PyPI content differs: {wheel.name}")
            print(f"Already published with identical bytes: {wheel.name}")
        else:
            selected.append(wheel)
    pending.mkdir(parents=True, exist_ok=False)
    for wheel in selected:
        shutil.copy2(wheel, pending / wheel.name)
    print(f"Pending PyPI wheels: {len(selected)}")
    return len(selected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--registry", choices=["npm", "pypi"], required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pending", type=Path)
    args = parser.parse_args()
    report = verify(args.directory, args.commit)
    if args.registry == "npm":
        npm(args.directory, report, args.apply)
    else:
        if args.apply or args.pending is None:
            parser.error("PyPI prepares --pending wheels; upload uses the trusted publisher action")
        pypi(args.directory, report, args.pending)

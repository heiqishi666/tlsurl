"""Validate five build outputs and assemble one unpublished release directory."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def contents(path):
    with tarfile.open(path) as tar:
        return {m.name: tar.extractfile(m).read() for m in tar if m.isfile()}


def collect(source, destination):
    groups = sorted(p for p in source.iterdir() if p.is_dir())
    if len(groups) != 5:
        raise ValueError(f"expected five platform artifacts, got {len(groups)}")
    main_contents = None
    platforms = set()
    wheels = set()
    selected = {}
    source_commit = None
    for group in groups:
        archives = list(group.rglob("*.tgz"))
        group_wheels = list(group.rglob("*.whl"))
        if len(archives) != 2 or len(group_wheels) != 1:
            raise ValueError(f"incomplete artifacts: {group}")
        audits = list(group.rglob("native-audit-*.json"))
        if len(audits) != 1:
            raise ValueError(f"expected one native audit: {group}")
        audit = json.loads(audits[0].read_text(encoding="utf-8"))
        commit = audit.get("git_commit")
        if not commit or (source_commit is not None and source_commit != commit):
            raise ValueError("audits must refer to the same source commit")
        source_commit = commit
        if audit.get("schema") != 1 or {item["language"] for item in audit["binaries"]} != {"python", "node"} or len(audit["binaries"]) != 2:
            raise ValueError("incomplete audit report")
        by_name = {path.name: path for path in [*archives, *group_wheels]}
        for item in audit["binaries"]:
            path = by_name.get(item["archive"])
            if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != item["archive_sha256"]:
                raise ValueError("audit does not match packaged artifact")
        selected[audits[0].name] = audits[0]
        for archive in archives:
            files = contents(archive)
            manifest = json.loads(files["package/package.json"])
            name = manifest["name"]
            if name == "tlsurl":
                if any(n.endswith(".node") for n in files):
                    raise ValueError("main package contains native binaries")
                if main_contents is not None and main_contents != files:
                    raise ValueError("main package contents differ between platforms")
                main_contents = files
            else:
                if name in platforms:
                    raise ValueError(f"duplicate platform: {name}")
                if f"package/{manifest['main']}" not in files:
                    raise ValueError(f"missing native binary: {name}")
                platforms.add(name)
            selected[archive.name] = archive
        wheel = group_wheels[0]
        if wheel.name in wheels:
            raise ValueError(f"duplicate wheel: {wheel.name}")
        wheels.add(wheel.name)
        selected[wheel.name] = wheel
    if main_contents is None:
        raise ValueError("missing main package")
    manifest = json.loads(main_contents["package/package.json"])
    dependencies = manifest["optionalDependencies"]
    if set(dependencies) != platforms or len(platforms) != 5:
        raise ValueError("platform packages do not match main optionalDependencies")
    for archive in selected.values():
        if archive.suffix == ".tgz":
            package = json.loads(contents(archive)["package/package.json"])
            if package["version"] != manifest["version"]:
                raise ValueError(f"version mismatch: {archive}")
    if any(version != manifest["version"] for version in dependencies.values()):
        raise ValueError("optional dependencies must use the exact release version")
    destination.mkdir(parents=True, exist_ok=False)
    checksums = []
    for name, path in sorted(selected.items()):
        shutil.copy2(path, destination / name)
        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}")
    (destination / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
    print(f"Validated {len(wheels)} wheels, {len(platforms)} platform packages and one main package")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    collect(args.source, args.destination)

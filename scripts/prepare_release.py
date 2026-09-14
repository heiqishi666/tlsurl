"""Download only a successful main-branch native build and verify its release bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from collect_native import collect, contents

REPOSITORY = "knight-bili/tlsurl"


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", f"repos/{REPOSITORY}/{path}"], text=True, encoding="utf-8"))


def verify(directory, commit):
    checksums = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_.+\-]+)", line)
        if not match or match[2] in checksums:
            raise ValueError("invalid or duplicate checksum entry")
        checksums[match[2]] = match[1]
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != set(checksums) | {"SHA256SUMS"} or len(checksums) != 16:
        raise ValueError("release must contain exactly 16 audited files and checksums")
    for name, digest in checksums.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"checksum mismatch: {name}")
    archives = list(directory.glob("*.tgz"))
    main = [path for path in archives if json.loads(contents(path)["package/package.json"])["name"] == "tlsurl"]
    if len(main) != 1:
        raise ValueError("expected one npm main package")
    audits = list(directory.glob("native-audit-*.json"))
    if len(audits) != 5:
        raise ValueError("expected five native audits")
    # Reuse collection gates for versions, platform coverage and audited hashes.
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        for index, path in enumerate(audits):
            audit = json.loads(path.read_text())
            if audit["git_commit"] != commit:
                raise ValueError("audit source commit differs from selected CI run")
            group = source / str(index)
            group.mkdir()
            shutil.copy2(path, group / path.name)
            shutil.copy2(main[0], group / main[0].name)
            for item in audit["binaries"]:
                name = item["archive"]
                if name not in checksums:
                    raise ValueError("audit references an unknown archive")
                shutil.copy2(directory / name, group / name)
        collect(source, Path(temporary) / "validated")
    notice = (Path(__file__).resolve().parents[1] / "docs/THIRD_PARTY_LICENSES.txt").read_bytes()
    for archive in archives:
        if contents(archive).get("package/THIRD_PARTY_LICENSES.txt") != notice:
            raise ValueError("npm license bundle differs from release source")
    import zipfile
    for wheel in directory.glob("*.whl"):
        with zipfile.ZipFile(wheel) as package:
            names = [name for name in package.namelist() if name.endswith(".dist-info/licenses/THIRD_PARTY_LICENSES.txt")]
            if len(names) != 1 or package.read(names[0]) != notice:
                raise ValueError("wheel license bundle differs from release source")
    manifest = json.loads(contents(main[0])["package/package.json"])
    return {"commit": commit, "version": manifest["version"],
            "npm": [path.name for path in sorted(archives) if path != main[0]] + [main[0].name]}


def prepare(run_id, commit, directory):
    if not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("invalid run id or source commit")
    run = api(f"actions/runs/{run_id}")
    if (run["status"] != "completed" or run["conclusion"] != "success" or run["head_sha"] != commit
            or run["head_branch"] != "main" or run["event"] not in ["push", "workflow_dispatch"]
            or run["path"] != ".github/workflows/native-packages.yml"
            or run["head_repository"]["full_name"] != REPOSITORY):
        raise ValueError("selected run is not a successful native build of this main commit")
    jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")
    if jobs["total_count"] != 31 or len(jobs["jobs"]) != 31 or any(job["conclusion"] != "success" for job in jobs["jobs"]):
        raise ValueError("all 31 build, collection and compatibility jobs must pass")
    directory.mkdir(parents=True, exist_ok=False)
    subprocess.run(["gh", "run", "download", run_id, "--repo", REPOSITORY,
                    "--name", "native-release", "--dir", str(directory)], check=True)
    report = verify(directory, commit)
    print(json.dumps(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.run_id, args.commit, args.destination)

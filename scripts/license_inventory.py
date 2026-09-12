"""Inventory enabled binding dependencies and available license texts; never infer approval."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def cargo(*args):
    return subprocess.check_output(["cargo", *args], cwd=ROOT, text=True, encoding="utf-8")


def inventory(output):
    metadata = json.loads(cargo("metadata", "--locked", "--format-version", "1"))
    tree = cargo("tree", "--locked", "-p", "tlsurl-python", "-p", "tlsurl-node",
                 "--edges", "normal,build", "--target", "all", "--prefix", "none", "--format", "{p}|{l}")
    selected = {match.groups() for line in tree.splitlines()
                if (match := re.match(r"(\S+) v([^\s|]+)", line))}
    packages = []
    for package in metadata["packages"]:
        if (package["name"], package["version"]) not in selected:
            continue
        root = Path(package["manifest_path"]).parent
        files = []
        if package["source"]:
            files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                           if path.is_file() and re.match(r"(?i)^(licen[cs]e|copying|notice|copyright)([.\-_]|$)", path.name))
        elif (root / "LICENSE").is_file():
            files = ["LICENSE"]
        packages.append({"name": package["name"], "version": package["version"],
                         "license": package["license"], "repository": package["repository"],
                         "source": package["source"], "licenseFiles": files})
    if len(packages) != len(selected):
        raise ValueError("dependency tree and metadata disagree")
    packages.sort(key=lambda item: (item["name"], item["version"]))
    report = {"scope": "Enabled normal/build dependencies for both bindings across all targets; includes build tools, not a linked-symbol inventory.",
              "packages": packages,
              "missingLicenseFiles": [f"{item['name']}@{item['version']}" for item in packages if not item["licenseFiles"]]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inventoried {len(packages)} packages; {len(report['missingLicenseFiles'])} require source license lookup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    inventory(parser.parse_args().output)

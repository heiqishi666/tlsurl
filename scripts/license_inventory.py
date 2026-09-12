"""Inventory enabled binding dependencies and available license texts; never infer approval."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def cargo(*args):
    return subprocess.check_output(["cargo", *args], cwd=ROOT, text=True, encoding="utf-8")


def inventory(output, bundle=None):
    texts = []
    metadata = json.loads(cargo("metadata", "--locked", "--format-version", "1"))
    selected = set()
    for target in ["x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu", "x86_64-pc-windows-msvc",
                   "x86_64-apple-darwin", "aarch64-apple-darwin"]:
        tree = cargo("tree", "--locked", "-p", "tlsurl-python", "-p", "tlsurl-node",
                     "--edges", "normal,build", "--target", target, "--prefix", "none", "--format", "{p}|{l}")
        selected.update(match.groups() for line in tree.splitlines()
                        if (match := re.match(r"(\S+) v([^\s|]+)", line)))
    packages = []
    for package in sorted(metadata["packages"], key=lambda item: (item["name"], item["version"])):
        if (package["name"], package["version"]) not in selected:
            continue
        root = Path(package["manifest_path"]).parent
        files = []
        if package["source"]:
            files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                           if path.is_file() and re.match(r"(?i)^(licen[cs]e|copying|notice|copyright)([.\-_]|$)", path.name))
        elif (root / "LICENSE").is_file():
            files = ["LICENSE"]
        if not files:
            if package["source"]:
                root = ROOT / "docs" / "licenses" / f"{package['name']}-{package['version']}"
                files = ["LICENSE"] if (root / "LICENSE").is_file() else []
            else:
                root = ROOT
                files = ["LICENSE"]
        if bundle:
            texts.append(f"\n===== {package['name']} {package['version']} =====\nDeclared license: {package['license']}\nRepository: {package['repository'] or 'https://github.com/heiqishi666/tlsurl'}\n")
            for name in files:
                texts.append(f"\n--- {name} ---\n" + (root / name).read_text(encoding="utf-8"))
            if (root / "SOURCE.md").is_file():
                texts.append((root / "SOURCE.md").read_text(encoding="utf-8"))
        packages.append({"name": package["name"], "version": package["version"],
                         "license": package["license"], "repository": package["repository"],
                         "source": package["source"], "licenseFiles": files})
    if len(packages) != len(selected):
        raise ValueError("dependency tree and metadata disagree")
    packages.sort(key=lambda item: (item["name"], item["version"]))
    report = {"scope": "Enabled normal/build dependencies for both bindings across the five supported targets; includes build tools, not a linked-symbol inventory.",
              "packages": packages,
              "missingLicenseFiles": [f"{item['name']}@{item['version']}" for item in packages if not item["licenseFiles"]]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if bundle:
        if report["missingLicenseFiles"]:
            raise ValueError("cannot bundle licenses with missing source texts")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text("Third-party license texts for tlsurl precompiled packages.\nIncludes normal and build dependencies for five release targets; inclusion does not imply every component is linked.\n" + "\n".join(texts), encoding="utf-8", newline="\n")
    print(f"Inventoried {len(packages)} packages; {len(report['missingLicenseFiles'])} require source license lookup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    inventory(args.output, args.bundle)

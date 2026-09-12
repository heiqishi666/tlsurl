"""Build installable artifacts for the current host; never publish packages."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NODE = ROOT / "bindings" / "node"


def run(args, cwd=ROOT, **kwargs):
    return subprocess.run(args, cwd=cwd, check=True, **kwargs)


def main():
    import clang

    os.environ.setdefault("LIBCLANG_PATH", str(Path(clang.__file__).parent / "native"))
    os.environ.setdefault("CMAKE_GENERATOR", "Ninja")
    (DIST / "wheels").mkdir(parents=True, exist_ok=True)
    (DIST / "npm").mkdir(parents=True, exist_ok=True)
    wheel_args = [
        sys.executable, "-m", "maturin", "build", "--release", "--locked",
        "--manifest-path", "bindings/python/Cargo.toml", "--out", str(DIST / "wheels"),
    ]
    if sys.platform == "linux":
        wheel_args += ["--compatibility", "manylinux_2_28"]
    run(wheel_args)
    # Resolve npm.cmd explicitly on Windows without a shell-built command string.
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("npm is required on the build machine")
    run([npm, "ci", "--ignore-scripts"], cwd=NODE)
    run([npm, "run", "build"], cwd=NODE)
    run([npm, "pack", "--ignore-scripts", "--pack-destination", str(DIST / "npm")], cwd=NODE)
    binaries = list(NODE.glob("tlsurl.*.node"))
    if len(binaries) != 1:
        raise RuntimeError("build in a clean checkout with exactly one host binary")
    binary = binaries[0]
    platform = binary.name.removeprefix("tlsurl.").removesuffix(".node")
    platform_dir = NODE / "npm" / platform
    shutil.copy2(binary, platform_dir / binary.name)
    run([npm, "pack", "--ignore-scripts", "--pack-destination", str(DIST / "npm")], cwd=platform_dir)
    print(json.dumps({"wheels": str(DIST / "wheels"), "npm": str(DIST / "npm")}))


if __name__ == "__main__":
    main()

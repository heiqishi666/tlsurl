"""Check positive and negative examples against installed wheel/npm declarations."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def checked(args, *, valid, expected_lines=(), pattern="", cwd=None):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd)
    if valid:
        if result.returncode:
            raise AssertionError(result.stdout)
    else:
        rejected = {int(line) for line in re.findall(pattern, result.stdout)}
        if result.returncode == 0 or not set(expected_lines).issubset(rejected):
            raise AssertionError(f"negative examples were not all rejected: {result.stdout}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-module", type=Path, required=True)
    args = parser.parse_args()
    for version in ["3.10", "3.14"]:
        common = [sys.executable, "-m", "mypy", "--strict", "--no-incremental", "--python-version", version]
        checked([*common, str(ROOT / "types_valid.py")], valid=True)
        checked([*common, str(ROOT / "types_invalid.py")], valid=False,
                expected_lines=range(4, 9), pattern=r"types_invalid\.py:(\d+): error:")
    # Import the public type helpers as well: a stub-only name must not promise a missing runtime export.
    subprocess.run([sys.executable, str(ROOT / "types_valid.py")], check=True)
    consumer = args.node_module.resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix=".tlsurl-types-", dir=consumer) as temporary:
        directory = Path(temporary)
        for name in ["types_valid.ts", "types_invalid.ts"]:
            shutil.copy2(ROOT / name, directory / name)
        common = ["node", str(ROOT / "node_modules/typescript/bin/tsc"), "--strict", "--noEmit",
                  "--target", "es2022", "--module", "nodenext", "--typeRoots", str(ROOT / "node_modules/@types")]
        checked([*common, str(directory / "types_valid.ts")], valid=True, cwd=directory)
        checked([*common, str(directory / "types_invalid.ts")], valid=False, cwd=directory,
                expected_lines=range(3, 9), pattern=r"types_invalid\.ts\((\d+),\d+\): error")
    print("Installed Python 3.10/3.14 and TypeScript declarations accept valid calls and reject all negative examples")


if __name__ == "__main__":
    main()

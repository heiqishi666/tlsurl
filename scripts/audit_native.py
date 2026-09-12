"""Inspect packaged native binaries on their build host; fail on portability drift."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import tarfile
import tempfile
import zipfile


def command(*args):
    return subprocess.check_output(args, text=True, errors="replace", env={**os.environ, "LC_ALL": "C"})


def architecture(data):
    if data[:4] == b"\x7fELF":
        if data[4:6] != b"\x02\x01":
            raise ValueError("expected little-endian ELF64")
        machine = struct.unpack_from("<H", data, 18)[0]
        return "ELF", {62: "x64", 183: "arm64"}.get(machine, str(machine))
    if data[:2] == b"MZ":
        offset = struct.unpack_from("<I", data, 60)[0]
        if data[offset:offset + 4] != b"PE\0\0":
            raise ValueError("invalid PE signature")
        machine = struct.unpack_from("<H", data, offset + 4)[0]
        return "PE", {0x8664: "x64", 0xAA64: "arm64"}.get(machine, str(machine))
    if data[:4] == b"\xcf\xfa\xed\xfe":
        machine = struct.unpack_from("<I", data, 4)[0]
        return "Mach-O", {0x1000007: "x64", 0x100000C: "arm64"}.get(machine, str(machine))
    raise ValueError("unsupported native format (expected one architecture)")


def numeric_version(value):
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * max(0, 3 - len(parts))


def inspect(path):
    data = path.read_bytes()
    kind, arch = architecture(data)
    result = {"format": kind, "architecture": arch, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if kind == "ELF":
        dynamic = command("readelf", "--dynamic", "--wide", str(path))
        versions = command("readelf", "--version-info", "--wide", str(path))
        symbols = command("readelf", "--dyn-syms", "--wide", str(path))
        result["needed"] = sorted(set(re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic)))
        result["rpaths"] = re.findall(r"\((?:RUNPATH|RPATH)\).*\[(.*?)\]", dynamic)
        result["symbol_versions"] = {}
        for namespace in ["GLIBC", "GLIBCXX", "CXXABI"]:
            found = set(re.findall(rf"\b{namespace}_(\d+(?:\.\d+)+)", versions))
            if found:
                result["symbol_versions"][namespace] = max(found, key=numeric_version)
        exported = []
        for line in symbols.splitlines():
            fields = line.split()
            if len(fields) >= 8 and fields[4] in {"GLOBAL", "WEAK"} and fields[6] != "UND":
                exported.append(fields[7].split("@")[0])
    elif kind == "PE":
        dependencies = command("dumpbin", "/nologo", "/dependents", str(path))
        exports = command("dumpbin", "/nologo", "/exports", str(path))
        result["needed"] = sorted(set(name.lower() for name in re.findall(r"(?im)^\s+([a-z0-9_.-]+\.dll)\s*$", dependencies)))
        exported = re.findall(r"(?im)^\s+\d+\s+[0-9a-f]+\s+[0-9a-f]+\s+(\S+)", exports)
    else:
        load_commands = command("otool", "-l", str(path))
        exports = command("nm", "-gU", str(path))
        result["needed"], result["rpaths"], result["minimum_macos"] = [], [], []
        for block in re.split(r"Load command \d+", load_commands):
            if re.search(r"cmd LC_(?:LOAD|LOAD_WEAK|REEXPORT)_DYLIB\b", block):
                result["needed"] += re.findall(r"\bname (.*?) \(offset", block)
            if "cmd LC_RPATH" in block:
                result["rpaths"] += re.findall(r"\bpath (.*?) \(offset", block)
            if "cmd LC_BUILD_VERSION" in block:
                result["minimum_macos"] += re.findall(r"\bminos (\d+(?:\.\d+)+)", block)
            if "cmd LC_VERSION_MIN_MACOSX" in block:
                result["minimum_macos"] += re.findall(r"\bversion (\d+(?:\.\d+)+)", block)
        exported = [line.split()[-1].removeprefix("_") for line in exports.splitlines() if line.split()]
    result["entry_points"] = [name for name in exported if name.startswith(("PyInit_", "napi_register_module_"))]
    result["unprefixed_crypto_exports"] = [name for name in exported if re.match(r"^(SSL_|OPENSSL_|CRYPTO_|EVP_|X509_)", name)]
    return result


def validate(result, language, expected_arch):
    if result["architecture"] != expected_arch:
        raise ValueError(f"wrong architecture: {result['architecture']} != {expected_arch}")
    expected_entry = "PyInit__native" if language == "python" else "napi_register_module_v1"
    if expected_entry not in result["entry_points"]:
        raise ValueError(f"missing native entry point: {expected_entry}")
    if result["unprefixed_crypto_exports"]:
        raise ValueError("unprefixed crypto symbols exported")
    needed = result["needed"]
    if result["format"] == "ELF":
        allowed = {"libc.so.6", "libm.so.6", "libgcc_s.so.1", "libstdc++.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1", "ld-linux-x86-64.so.2", "ld-linux-aarch64.so.1"}
        if set(needed) - allowed:
            raise ValueError(f"unexpected Linux libraries: {set(needed) - allowed}")
        for namespace, maximum in {"GLIBC": "2.28", "GLIBCXX": "3.4.25", "CXXABI": "1.3.11"}.items():
            actual = result["symbol_versions"].get(namespace)
            if actual and numeric_version(actual) > numeric_version(maximum):
                raise ValueError(f"{namespace}_{actual} exceeds supported baseline {maximum}")
        if any(part.startswith("/") for value in result["rpaths"] for part in value.split(":")):
            raise ValueError("absolute Linux runtime search path")
    elif result["format"] == "PE":
        allowed = {"kernel32.dll", "ntdll.dll", "ws2_32.dll", "bcrypt.dll", "bcryptprimitives.dll", "advapi32.dll", "crypt32.dll", "secur32.dll", "userenv.dll", "user32.dll", "shell32.dll", "ole32.dll", "vcruntime140.dll", "vcruntime140_1.dll", "ucrtbase.dll"}
        if language == "python":
            allowed.add("python3.dll")
        unexpected = [name for name in needed if name not in allowed and not name.startswith(("api-ms-win-", "ext-ms-win-"))]
        if unexpected:
            raise ValueError(f"unexpected Windows libraries: {unexpected}")
    else:
        if not result["minimum_macos"] or any(numeric_version(value) > numeric_version("11.0") for value in result["minimum_macos"]):
            raise ValueError(f"unexpected macOS deployment minimum: {result['minimum_macos']}")
        if any(not name.startswith(("/usr/lib/", "/System/Library/")) for name in needed):
            raise ValueError(f"non-system macOS library: {needed}")
        if any(path.startswith("/") for path in result["rpaths"]):
            raise ValueError("absolute macOS runtime search path")


def audit(artifacts, output):
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}[machine]
    reports = []
    wheels = sorted(artifacts.rglob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("audit expects exactly one host wheel")
    binaries = []
    with zipfile.ZipFile(wheels[0]) as wheel:
        natives = [name for name in wheel.namelist() if name.endswith((".so", ".pyd"))]
        if len(natives) != 1:
            raise ValueError("expected one Python native extension")
        binaries.append((wheels[0], "python", natives[0], wheel.read(natives[0])))
    for archive in sorted(artifacts.rglob("*.tgz")):
        with tarfile.open(archive) as package:
            for member in package:
                if member.isfile() and member.name.endswith(".node"):
                    binaries.append((archive, "node", member.name, package.extractfile(member).read()))
    if len(binaries) != 2:
        raise ValueError("expected one wheel and one Node native binary")
    with tempfile.TemporaryDirectory() as temporary:
        for archive, language, name, data in binaries:
            native = Path(temporary) / Path(name).name
            native.write_bytes(data)
            result = inspect(native)
            validate(result, language, arch)
            reports.append({"archive": archive.name, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "language": language, "binary": name, **result})
    report = {
        "schema": 1, "git_commit": command("git", "-c", f"safe.directory={Path(__file__).resolve().parents[1]}", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD").strip(),
        "host": {"system": platform.system(), "release": platform.release(), "machine": machine, "libc": platform.libc_ver()},
        "toolchain": {"rust": command("rustc", "--version").strip(), "python": platform.python_version(), "node": command("node", "--version").strip()},
        "binaries": reports,
        "scope": "Binary linkage and deployment metadata; not proof of execution on the oldest OS or CPU.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Native artifact audit passed: {platform.system()} {arch}, {len(reports)} binaries")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.artifacts, args.output)

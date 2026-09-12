"""Release gates must reject incompatible or unaudited artifacts."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_native import validate
from collect_native import collect


class NativePolicyTests(unittest.TestCase):
    def test_rejects_incompatible_linkage(self):
        valid = {"format": "ELF", "architecture": "x64", "entry_points": ["napi_register_module_v1"],
                 "unprefixed_crypto_exports": [], "needed": ["libc.so.6"], "rpaths": [],
                 "symbol_versions": {"GLIBC": "2.28"}}
        validate(valid, "node", "x64")
        for change in [
            {"architecture": "arm64"}, {"needed": ["libssl.so.3"]},
            {"symbol_versions": {"GLIBC": "2.34"}}, {"symbol_versions": {"GLIBCXX": "3.4.29"}},
            {"unprefixed_crypto_exports": ["SSL_new"]}, {"entry_points": []},
            {"rpaths": ["/home/builder/private/lib"]},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate({**copy.deepcopy(valid), **change}, "node", "x64")


def tar(path, files):
    with tarfile.open(path, "w:gz") as archive:
        for name, value in files.items():
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            member = tarfile.TarInfo("package/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


class CollectionTests(unittest.TestCase):
    def fixture(self, root):
        platforms = [f"tlsurl-test-{index}" for index in range(5)]
        main = {"name": "tlsurl", "version": "0.1.0", "optionalDependencies": dict.fromkeys(platforms, "0.1.0")}
        for index, name in enumerate(platforms):
            group = root / name
            group.mkdir()
            tar(group / "tlsurl-0.1.0.tgz", {"package.json": main})
            native = group / f"{name}-0.1.0.tgz"
            tar(native, {"package.json": {"name": name, "version": "0.1.0", "main": "native.node"}, "native.node": b"test fixture"})
            wheel = group / f"tlsurl-0.1.0-cp310-abi3-test_{index}.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("tlsurl-0.1.0.dist-info/METADATA", "Metadata-Version: 2.4\nName: tlsurl\nVersion: 0.1.0\n")
            report = {"schema": 1, "git_commit": "source-commit", "binaries": [
                {"archive": path.name, "language": language, "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path, language in [(native, "node"), (wheel, "python")]
            ]}
            (group / f"native-audit-{index}.json").write_text(json.dumps(report))

    def test_collects_matching_audits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            self.fixture(source)
            collect(source, root / "release")
            self.assertEqual(len((root / "release/SHA256SUMS").read_text().splitlines()), 16)

    def test_rejects_mismatched_wheel_metadata_even_with_valid_audit(self):
        for metadata in ["Name: other\nVersion: 0.1.0\n", "Name: tlsurl\nVersion: 0.2.0\n",
                         "Name: tlsurl\nVersion: 0.1.0\nVersion: 0.2.0\n"]:
            with self.subTest(metadata=metadata), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                source.mkdir()
                self.fixture(source)
                group = source / "tlsurl-test-0"
                wheel = next(group.glob("*.whl"))
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr("tlsurl-0.1.0.dist-info/METADATA", metadata)
                audit = group / "native-audit-0.json"
                report = json.loads(audit.read_text())
                report["binaries"][1]["archive_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
                audit.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, "wheel name or version mismatch"):
                    collect(source, root / "release")
                self.assertFalse((root / "release").exists())

    def test_rejects_changed_artifact_or_missing_audit(self):
        for mutation in ["tamper", "missing", "different-commit"]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                source.mkdir()
                self.fixture(source)
                group = source / "tlsurl-test-0"
                audit = group / "native-audit-0.json"
                if mutation == "tamper":
                    (group / "tlsurl-0.1.0-cp310-abi3-test_0.whl").write_bytes(b"changed after audit")
                elif mutation == "missing":
                    audit.unlink()
                else:
                    audit.write_text(audit.read_text().replace("source-commit", "other-commit"))
                with self.assertRaises(ValueError):
                    collect(source, root / "release")


if __name__ == "__main__":
    unittest.main()

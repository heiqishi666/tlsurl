"""Reject releases from failed/incomplete runs and tampered artifact bundles."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_release import prepare, verify
from publish_packages import npm, pypi
from test_audit import tar
from verify_registry import check_download, check


class ReleaseTests(unittest.TestCase):
    def test_rejects_unapproved_run_before_download(self):
        valid = {"status": "completed", "conclusion": "success", "head_sha": "a" * 40,
                 "head_branch": "main", "event": "push", "path": ".github/workflows/native-packages.yml",
                 "head_repository": {"full_name": "heiqishi666/tlsurl"}}
        for change in [{"conclusion": "failure"}, {"status": "in_progress"}, {"head_sha": "b" * 40},
                       {"head_branch": "other"}, {"event": "pull_request"}, {"path": "other.yml"},
                       {"head_repository": {"full_name": "other/tlsurl"}}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                with patch("prepare_release.api", return_value={**valid, **change}), patch("prepare_release.subprocess.run") as download:
                    with self.assertRaises(ValueError):
                        prepare("123", "a" * 40, Path(temp) / "release")
                    download.assert_not_called()
        with tempfile.TemporaryDirectory() as temp:
            with patch("prepare_release.api", side_effect=[valid, {"total_count": 30, "jobs": []}]), patch("prepare_release.subprocess.run") as download:
                with self.assertRaises(ValueError):
                    prepare("123", "a" * 40, Path(temp) / "release")
                download.assert_not_called()

    def test_rejects_tampered_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lines = []
            for index in range(16):
                name = f"artifact-{index}.txt"
                (root / name).write_bytes(b"original")
                lines.append(f"{hashlib.sha256(b'original').hexdigest()}  {name}")
            (root / "SHA256SUMS").write_text("\n".join(lines))
            (root / "artifact-0.txt").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify(root, "a" * 40)


class RegistryRetryTests(unittest.TestCase):
    def test_npm_conflict_prevents_all_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ["platform", "main"]:
                tar(root / f"{name}.tgz", {"package.json": {"name": name}})
            with patch("publish_packages.remote_json", side_effect=[None, {"dist": {"integrity": "wrong"}}]), patch("publish_packages.subprocess.run") as publish:
                with self.assertRaisesRegex(ValueError, "published npm content differs"):
                    npm(root, {"npm": ["platform.tgz", "main.tgz"], "version": "0.1.0"}, apply=True)
                publish.assert_not_called()

    def test_pypi_retry_selects_only_missing_identical_version_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.whl").write_bytes(b"one")
            (root / "two.whl").write_bytes(b"two")
            remote = {"urls": [{"filename": "one.whl", "digests": {"sha256": hashlib.sha256(b"one").hexdigest()}}]}
            with patch("publish_packages.remote_json", return_value=remote):
                self.assertEqual(pypi(root, {"version": "0.1.0"}, root / "pending"), 1)
                self.assertEqual([p.name for p in (root / "pending").iterdir()], ["two.whl"])
            remote["urls"][0]["digests"]["sha256"] = "wrong"
            with patch("publish_packages.remote_json", return_value=remote):
                with self.assertRaisesRegex(ValueError, "published PyPI content differs"):
                    pypi(root, {"version": "0.1.0"}, root / "rejected")
                self.assertFalse((root / "rejected").exists())


class RegistrySelectionTests(unittest.TestCase):
    def test_only_selected_registry_is_contacted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.whl").write_bytes(b"wheel")
            tar(root / "main.tgz", {"package.json": {"name": "tlsurl"}})
            report = {"version": "0.1.0", "npm": ["main.tgz"]}
            def remote(url):
                if "registry.npmjs.org" in url:
                    return {"dist": {"tarball": "https://registry.npmjs.org/main.tgz"}}
                return {"urls": [{"filename": "one.whl", "url": "https://files.pythonhosted.org/one.whl"}]}
            for registry, count in [("pypi", 1), ("npm", 1), ("both", 2)]:
                with self.subTest(registry=registry), patch("verify_registry.verify", return_value=report), \
                        patch("verify_registry.remote_json", side_effect=remote) as fetch, \
                        patch("verify_registry.check_download", return_value={}) as download:
                    result = check(root, "a" * 40, registry)
                    self.assertEqual(result["registry"], registry)
                    self.assertEqual(len(result["files"]), count)
                    self.assertEqual(download.call_count, count)
                    urls = [call.args[0] for call in fetch.call_args_list]
                    self.assertEqual(any("pypi.org" in url for url in urls), registry != "npm")
                    self.assertEqual(any("registry.npmjs.org" in url for url in urls), registry != "pypi")
            with patch("verify_registry.verify") as verify_bundle:
                with self.assertRaisesRegex(ValueError, "unknown registry"):
                    check(root, "a" * 40, "invalid")
                verify_bundle.assert_not_called()


class RegistryDownloadTests(unittest.TestCase):
    def test_actual_bytes_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "package.tgz"
            path.write_bytes(b"candidate")
            for body, succeeds in [(b"candidate", True), (b"different", False), (b"extra bytes", False)]:
                response = io.BytesIO(body)
                response.url = "https://registry.npmjs.org/test.tgz"
                with patch("verify_registry.urlopen", return_value=response):
                    if succeeds:
                        self.assertEqual(check_download(response.url, path, "registry.npmjs.org")["bytes"], 9)
                    else:
                        with self.assertRaises(ValueError):
                            check_download(response.url, path, "registry.npmjs.org")
            with patch("verify_registry.urlopen") as fetch:
                with self.assertRaises(ValueError):
                    check_download("https://other.example/test.tgz", path, "registry.npmjs.org")
                fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

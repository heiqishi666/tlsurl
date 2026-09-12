"""Reject releases from failed/incomplete runs and tampered artifact bundles."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_release import prepare, verify


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


if __name__ == "__main__":
    unittest.main()

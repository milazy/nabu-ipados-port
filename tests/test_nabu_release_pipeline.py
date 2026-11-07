#!/usr/bin/env python3
"""Offline test coverage: all physical flash/write paths remain unavailable."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("preflight", REPO/"ci/audit_nabu_boot_candidate.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class SourceLockTests(unittest.TestCase):
    def test_refs_are_pinned_and_read_only(self):
        lock = json.loads((REPO/"ci/research_sources.lock.json").read_text())
        self.assertEqual(lock["target"]["apple_build"], "21H16")
        self.assertEqual(lock["sources"][0]["slug"], "nabu")
        self.assertEqual(len(lock["sources"]), 4)
        self.assertTrue(lock["restrictions"]["no_flash"])
        self.assertFalse(lock["status"]["apple_store_qualified"])
        for source in lock["sources"]:
            self.assertEqual(len(source["sha"]), 40)
            self.assertTrue(source["url"].startswith("https://github.com/"))
            self.assertGreater(len(source["required"]), 0)


class BootCandidateTests(unittest.TestCase):
    def test_missing_manifest_never_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            result = preflight.audit(Path(folder)/"missing.json")
            self.assertFalse(result["host_package_complete"])
            self.assertFalse(result["ready_to_flash"])

    def _create_candidate(self, root: Path):
        artifacts = {}
        for key in preflight.REQUIRED:
            data = (b"\xcf\xfa\xed\xfe" + b"X"*64 if key == "kernel" else
                    b"\x00"*82+b"FAT32"+b"\x00"*423+b"\x55\xaa" if key == "uefi_esp" else b"Y"*128)
            file = root / (key+".bin")
            file.write_bytes(data)
            artifacts[key] = {"path": file.name, "sha256": hashlib.sha256(data).hexdigest()}
        # Explicitly non-overlapping synthetic 4KiB GPT, including all protected names.
        partitions = [
            {"name": name, "start_lba": 1024+1000*i, "sectors": 100}
            for i,name in enumerate(("boot","super","userdata","cust","rescue"))]
        manifest = {
            "schema": 1, "target": dict(preflight.TARGET),
            "artifacts": artifacts,
            "storage": {
                "block_size": 4096,
                "partitions": partitions,
                "allocations": [{"purpose": "os", "start_lba": 10000, "sectors": 200}]}}
        path = root/"candidate.json"
        path.write_text(json.dumps(manifest))
        backup = root/"backup.json"
        backup.write_text(json.dumps({
            "result": "PASS", "files": 32390, "bytes": 40374431865,
            "destination": "F:/NABU_IPADOS_COMPLETE_BACKUP_20261107/NABU_IPADOS_LAB"}))
        return path, backup, manifest

    def test_well_formed_synthetic_only_host_complete_never_flash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, backup, _ = self._create_candidate(root)
            with patch.dict(preflight.MIN_BYTES, {k: 1 for k in preflight.MIN_BYTES}):
                result = preflight.audit(path, backup)
            self.assertEqual(result["errors"], [])
            self.assertTrue(result["host_package_complete"])
            self.assertFalse(result["ready_to_flash"])
            self.assertTrue(result["requires_real_device_boot_validation"])

    def test_overlap_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, backup, data = self._create_candidate(root)
            data["storage"]["allocations"][0]["start_lba"] = 1024
            path.write_text(json.dumps(data))
            with patch.dict(preflight.MIN_BYTES, {k: 1 for k in preflight.MIN_BYTES}):
                result = preflight.audit(path, backup)
            self.assertFalse(result["host_package_complete"])
            self.assertTrue(any("overlaps existing" in e for e in result["errors"]))

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, backup, data = self._create_candidate(root)
            data["artifacts"]["kernel"]["sha256"] = "0"*64
            path.write_text(json.dumps(data))
            result = preflight.audit(path, backup)
            self.assertFalse(result["host_package_complete"])
            self.assertTrue(any("hash mismatch" in e for e in result["errors"]))

    def test_relative_path_escape_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, backup, data = self._create_candidate(root)
            data["artifacts"]["kernel"]["path"] = "../some-kernel.macho"
            path.write_text(json.dumps(data))
            result = preflight.audit(path, backup)
            self.assertFalse(result["host_package_complete"])
            self.assertTrue(any("unsafe" in e for e in result["errors"]))

    def test_no_verified_external_backup_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, _, _ = self._create_candidate(root)
            result = preflight.audit(path)
            self.assertFalse(result["host_package_complete"])
            self.assertTrue(any("backup" in e.lower() for e in result["errors"]))

    def test_not_allowed_to_assert_promotion_or_app_store(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, backup, data = self._create_candidate(root)
            data["target"]["native_120hz_qualified"] = True
            data["target"]["apple_store_qualified"] = True
            path.write_text(json.dumps(data))
            result = preflight.audit(path, backup)
            self.assertFalse(result["host_package_complete"])
            self.assertTrue(any("App Store" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()

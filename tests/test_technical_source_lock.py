import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "technical_source_lock", ROOT / "scripts" / "technical_source_lock.py"
)
assert SPEC and SPEC.loader
LOCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK)
SOURCE_LOCK = ROOT / "technical" / "releases" / "v5.0.8.source-lock.json"


class TechnicalSourceLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))

    def _write(self, root: Path, payload: dict) -> Path:
        path = root / "source-lock.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_checked_in_source_lock_is_valid(self) -> None:
        result = LOCK.validate(lock_path=SOURCE_LOCK)
        self.assertTrue(result["validated"])
        self.assertEqual(36152873675, result["run_id"])
        self.assertEqual(1, result["source_attempt"])
        self.assertEqual(2, result["current_attempt"])

    def test_rejects_claim_widening(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["claims"]["customer_evidence_eligible"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write(Path(temporary), payload)
            with self.assertRaisesRegex(LOCK.SourceLockError, "denied claims"):
                LOCK.validate(lock_path=path)

    def test_rejects_attempt_or_chronology_drift(self) -> None:
        mutations = (
            ("current_attempt", 3, "current_attempt"),
            (
                "source_attempt_updated_at",
                "2026-09-25T16:40:00Z",
                "chronology",
            ),
        )
        for field, value, error in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                payload = copy.deepcopy(self.payload)
                payload["release_evidence"][field] = value
                path = self._write(Path(temporary), payload)
                with self.assertRaisesRegex(LOCK.SourceLockError, error):
                    LOCK.validate(lock_path=path)

    def test_rejects_reviewed_robustness_membership_drift(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["sources"]["robustness"]["reviewed_files"].pop(
            "gold/robustness_index.csv"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write(Path(temporary), payload)
            with self.assertRaisesRegex(LOCK.SourceLockError, "membership"):
                LOCK.validate(lock_path=path)

    def test_actions_archive_bytes_are_hash_and_size_bound(self) -> None:
        payload = copy.deepcopy(self.payload)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "intake.actions.zip"
            archive.write_bytes(b"exact-actions-archive")
            identity = payload["sources"]["intake"]["actions_archive"]
            identity["size_bytes"] = archive.stat().st_size
            identity["digest"] = "sha256:" + LOCK._sha256(archive)
            path = self._write(root, payload)
            LOCK.validate(lock_path=path, intake_actions_archive=archive)
            archive.write_bytes(b"mutated-actions-archive")
            with self.assertRaisesRegex(LOCK.SourceLockError, "archive size mismatch"):
                LOCK.validate(lock_path=path, intake_actions_archive=archive)

    def test_rejects_wrong_product_source_map(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_map = Path(temporary) / "source-map.json"
            source_map.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(LOCK.SourceLockError, "size mismatch"):
                LOCK.validate(lock_path=SOURCE_LOCK, product_source_map=source_map)


if __name__ == "__main__":
    unittest.main()

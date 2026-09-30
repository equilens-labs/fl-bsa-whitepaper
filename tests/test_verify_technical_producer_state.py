import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_technical_producer_state",
    ROOT / "scripts" / "verify_technical_producer_state.py",
)
assert SPEC and SPEC.loader
STATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE)
SOURCE_LOCK = ROOT / "technical" / "releases" / "v5.0.8.source-lock.json"


class TechnicalProducerStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
        evidence = self.lock["release_evidence"]
        base = {
            "id": evidence["run_id"],
            "status": "completed",
            "event": evidence["event"],
            "head_branch": evidence["branch"],
            "head_sha": self.lock["product"]["commit"],
            "path": evidence["workflow_path"],
            "repository": {"full_name": "equilens-labs/fl-bsa"},
        }
        self.current = {
            **base,
            "run_attempt": 2,
            "conclusion": "success",
            "run_started_at": evidence["current_attempt_started_at"],
            "updated_at": "2026-09-25T16:51:13Z",
        }
        self.source = {
            **base,
            "run_attempt": 1,
            "conclusion": "failure",
            "run_started_at": evidence["source_attempt_started_at"],
            "updated_at": evidence["source_attempt_updated_at"],
        }
        self.jobs = {
            "jobs": [
                {
                    "id": source["producer_job"]["id"],
                    "name": source["producer_job"]["name"],
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": source["producer_job"]["conclusion"],
                    "started_at": source["producer_job"]["started_at"],
                    "completed_at": source["producer_job"]["completed_at"],
                }
                for source in self.lock["sources"].values()
            ]
        }
        self.artifacts = {
            label: {
                "id": source["actions_archive"]["id"],
                "name": source["actions_archive"]["name"],
                "size_in_bytes": source["actions_archive"]["size_bytes"],
                "digest": source["actions_archive"]["digest"],
                "created_at": source["actions_archive"]["created_at"],
                "expires_at": source["actions_archive"]["expires_at"],
                "expired": False,
                "workflow_run": {
                    "id": self.lock["release_evidence"]["run_id"],
                    "head_branch": self.lock["release_evidence"]["branch"],
                    "head_sha": self.lock["product"]["commit"],
                },
            }
            for label, source in self.lock["sources"].items()
        }

    @staticmethod
    def _write(root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _verify(self, root: Path, **mutations: dict) -> dict:
        payloads = {
            "current": copy.deepcopy(self.current),
            "source": copy.deepcopy(self.source),
            "jobs": copy.deepcopy(self.jobs),
            "intake": copy.deepcopy(self.artifacts["intake"]),
            "robustness": copy.deepcopy(self.artifacts["robustness"]),
            "after": copy.deepcopy(self.current),
        }
        payloads.update(mutations)
        paths = {
            name: self._write(root, f"{name}.json", payload)
            for name, payload in payloads.items()
        }
        return STATE.verify(
            lock_path=SOURCE_LOCK,
            current_run_path=paths["current"],
            source_run_path=paths["source"],
            jobs_path=paths["jobs"],
            intake_artifact_path=paths["intake"],
            robustness_artifact_path=paths["robustness"],
            current_run_after_path=paths["after"],
            now=datetime(2026, 9, 30, tzinfo=timezone.utc),
        )

    def test_accepts_exact_live_state_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self._verify(Path(temporary))
        self.assertTrue(result["verified"])
        self.assertEqual(10872328152, result["intake_artifact_id"])

    def test_rejects_wrong_attempt_job_or_artifact(self) -> None:
        cases = []
        current = copy.deepcopy(self.current)
        current["run_attempt"] = 3
        cases.append(("current", current, "run_attempt"))
        jobs = copy.deepcopy(self.jobs)
        jobs["jobs"][0]["conclusion"] = "failure"
        cases.append(("jobs", jobs, "conclusion"))
        intake = copy.deepcopy(self.artifacts["intake"])
        intake["digest"] = "sha256:" + "0" * 64
        cases.append(("intake", intake, "digest"))
        for key, payload, error in cases:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(STATE.ProducerStateError, error):
                    self._verify(Path(temporary), **{key: payload})

    def test_rejects_expired_artifact_even_if_api_flag_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payloads = {
                "current": self._write(root, "current.json", self.current),
                "source": self._write(root, "source.json", self.source),
                "jobs": self._write(root, "jobs.json", self.jobs),
                "intake": self._write(root, "intake.json", self.artifacts["intake"]),
                "robustness": self._write(
                    root, "robustness.json", self.artifacts["robustness"]
                ),
            }
            with self.assertRaisesRegex(STATE.ProducerStateError, "has expired"):
                STATE.verify(
                    lock_path=SOURCE_LOCK,
                    current_run_path=payloads["current"],
                    source_run_path=payloads["source"],
                    jobs_path=payloads["jobs"],
                    intake_artifact_path=payloads["intake"],
                    robustness_artifact_path=payloads["robustness"],
                    now=datetime(2026, 12, 25, tzinfo=timezone.utc),
                )

    def test_rejects_toctou_run_change(self) -> None:
        after = copy.deepcopy(self.current)
        after["updated_at"] = "2026-09-25T17:00:00Z"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(STATE.ProducerStateError, "changed while"):
                self._verify(Path(temporary), after=after)


if __name__ == "__main__":
    unittest.main()

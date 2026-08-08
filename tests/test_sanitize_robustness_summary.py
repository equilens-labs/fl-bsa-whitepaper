import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "sanitize_robustness_summary.py"
SPEC = importlib.util.spec_from_file_location(
    "sanitize_robustness_summary", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
SANITIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SANITIZER)


class RobustnessSummaryProjectionTests(unittest.TestCase):
    def _source(self) -> bytes:
        payload = {
            "schema_version": "gold.robustness.v1",
            "rows": [
                {
                    "run_dir": f"/mnt/ci-work/run-{index}",
                    "scenario_dir": f"/mnt/ci-work/run-{index}/scenario",
                    "seed": index,
                }
                for index in range(40)
            ],
        }
        return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")

    def test_projection_removes_only_expected_machine_local_fields(self) -> None:
        source = self._source()
        output = SANITIZER.project(
            source,
            expected_source_sha256=hashlib.sha256(source).hexdigest(),
        )
        projected = json.loads(output)

        self.assertEqual(list(range(40)), [row["seed"] for row in projected["rows"]])
        self.assertNotIn("run_dir", output.decode("utf-8"))
        self.assertNotIn("scenario_dir", output.decode("utf-8"))
        self.assertNotIn("/mnt/ci-work/", output.decode("utf-8"))

    def test_projection_rejects_wrong_source_hash_or_field_count(self) -> None:
        source = self._source()
        with self.assertRaisesRegex(SANITIZER.ProjectionError, "SHA-256 mismatch"):
            SANITIZER.project(source, expected_source_sha256="0" * 64)

        payload = json.loads(source)
        payload["rows"].pop()
        short_source = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        with self.assertRaisesRegex(SANITIZER.ProjectionError, "field counts"):
            SANITIZER.project(
                short_source,
                expected_source_sha256=hashlib.sha256(short_source).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()

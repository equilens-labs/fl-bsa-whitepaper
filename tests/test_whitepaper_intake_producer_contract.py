import copy
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "whitepaper-intake-producer-contract.v1.json"
SCRIPT_PATH = ROOT / "scripts" / "whitepaper_intake_producer_contract.py"
SPEC = importlib.util.spec_from_file_location("whitepaper_intake_contract", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def _dispatch_inputs() -> dict[str, str]:
    return {
        "producer_repo": "equilens-labs/fl-bsa",
        "workflow": "wp-evidence-nightly.yml",
        "branch": "main",
        "producer_event": "repository_dispatch",
        "artifact_name": "wp-intake-bundle-v4-3",
        "producer_run_id": "123",
        "producer_run_attempt": "3",
        "artifact_id": "456",
        "artifact_digest": "sha256:" + "a" * 64,
        "persist_intake_pr": "false",
    }


class WhitepaperIntakeProducerContractTests(unittest.TestCase):
    def test_reviewed_authority_matrix_is_executable(self) -> None:
        contract, digest = CONTRACT.load_contract(CONTRACT_PATH)

        self.assertEqual(64, len(digest))
        self.assertEqual(
            {"schedule", "repository_dispatch"},
            CONTRACT.authority_events(
                contract,
                producer_repo="equilens-labs/fl-bsa",
                workflow="wp-evidence-nightly.yml",
                branch="main",
            ),
        )
        self.assertEqual(
            {"repository_dispatch"},
            CONTRACT.authority_events(
                contract,
                producer_repo="equilens-labs/fl-bsa",
                workflow="release-evidence.yml",
                branch="main",
            ),
        )

        for workflow, event in (
            ("wp-evidence-nightly.yml", "schedule"),
            ("wp-evidence-nightly.yml", "repository_dispatch"),
            ("release-evidence.yml", "repository_dispatch"),
        ):
            CONTRACT.validate_authority(
                contract,
                producer_repo="equilens-labs/fl-bsa",
                workflow=workflow,
                branch="main",
                event=event,
            )

    def test_stale_or_unreviewed_authority_is_rejected(self) -> None:
        contract, _ = CONTRACT.load_contract(CONTRACT_PATH)

        for workflow, branch, event in (
            ("wp-evidence-nightly.yml", "main", "workflow_dispatch"),
            ("release-evidence.yml", "main", "workflow_dispatch"),
            ("release-evidence.yml", "main", "schedule"),
            (
                "release-evidence.yml",
                "release/v5.1.0-deadbeef",
                "repository_dispatch",
            ),
        ):
            with self.subTest(workflow=workflow, branch=branch, event=event):
                with self.assertRaises(CONTRACT.ContractError):
                    CONTRACT.validate_authority(
                        contract,
                        producer_repo="equilens-labs/fl-bsa",
                        workflow=workflow,
                        branch=branch,
                        event=event,
                    )

    def test_dispatch_builder_and_validator_share_exact_payload(self) -> None:
        contract, digest = CONTRACT.load_contract(CONTRACT_PATH)
        envelope = CONTRACT.build_dispatch_envelope(
            contract,
            digest,
            **_dispatch_inputs(),
        )

        self.assertEqual("wp-intake-ready", envelope["event_type"])
        payload = envelope["client_payload"]
        self.assertEqual(digest, payload["producer_contract_sha256"])
        self.assertEqual(set(contract["dispatch_payload_fields"]), set(payload))
        self.assertEqual(
            payload,
            CONTRACT.validate_dispatch_payload(contract, digest, payload),
        )

    def test_dispatch_identity_or_policy_drift_is_rejected(self) -> None:
        contract, digest = CONTRACT.load_contract(CONTRACT_PATH)
        envelope = CONTRACT.build_dispatch_envelope(
            contract,
            digest,
            **_dispatch_inputs(),
        )

        for field, value in (
            ("producer_contract_sha256", "9" * 64),
            ("producer_run_id", "latest"),
            ("producer_run_attempt", "0"),
            ("artifact_id", "-1"),
            ("artifact_digest", "sha256:not-a-digest"),
            ("artifact_name", "wp-intake-bundle-v4"),
            ("persist_intake_pr", "true"),
        ):
            with self.subTest(field=field):
                payload = copy.deepcopy(envelope["client_payload"])
                payload[field] = value
                with self.assertRaises(CONTRACT.ContractError):
                    CONTRACT.validate_dispatch_payload(contract, digest, payload)

    def test_contract_cli_builds_payload_the_consumer_cli_accepts(self) -> None:
        inputs = _dispatch_inputs()
        built = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "build-dispatch",
                "--contract",
                str(CONTRACT_PATH),
                "--producer-repo",
                inputs["producer_repo"],
                "--workflow",
                inputs["workflow"],
                "--branch",
                inputs["branch"],
                "--producer-event",
                inputs["producer_event"],
                "--artifact-name",
                inputs["artifact_name"],
                "--producer-run-id",
                inputs["producer_run_id"],
                "--producer-run-attempt",
                inputs["producer_run_attempt"],
                "--artifact-id",
                inputs["artifact_id"],
                "--artifact-digest",
                inputs["artifact_digest"],
                "--persist-intake-pr",
                inputs["persist_intake_pr"],
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, built.returncode, built.stderr)
        envelope = json.loads(built.stdout)

        validated = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "validate-dispatch",
                "--contract",
                str(CONTRACT_PATH),
                "--payload-env",
                "TEST_DISPATCH_PAYLOAD",
            ],
            env={
                **os.environ,
                "TEST_DISPATCH_PAYLOAD": json.dumps(envelope["client_payload"]),
            },
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, validated.returncode, validated.stderr)
        self.assertEqual(
            envelope["client_payload"]["producer_contract_sha256"],
            validated.stdout.strip(),
        )


if __name__ == "__main__":
    unittest.main()

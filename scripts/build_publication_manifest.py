#!/usr/bin/env python3
"""Write a hash-bound manifest for whitepaper PDF and arXiv candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from intake_anchor import AnchorError, validate_anchor, validate_publication_source


SCHEMA_VERSION = "flbsa.whitepaper_publication_candidate.v1"
WHITEPAPER_REPO = "equilens-labs/fl-bsa-whitepaper"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_STATUSES = {
    "candidate_not_published",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnchorError(f"unable to read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AnchorError(f"expected a JSON object in {path}")
    return payload


def _artifact(path: Path, published_name: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AnchorError(f"unable to read publication artifact {path}: {exc}") from exc
    if not payload:
        raise AnchorError(f"publication artifact is empty: {path}")
    return {
        "name": published_name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise AnchorError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _assert_source_checkout(repo_root: Path, whitepaper_commit: str) -> None:
    head = _git(repo_root, "rev-parse", "HEAD")
    if head != whitepaper_commit:
        raise AnchorError(
            f"whitepaper commit {whitepaper_commit} is not the checked-out HEAD {head}"
        )
    tracked_status = _git(
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    if tracked_status:
        raise AnchorError(
            "publication checkout differs from the checked-out commit; "
            "refusing a false source assertion"
        )


def _assert_pdf_marker(pdf_path: Path, pdftotext_command: str) -> None:
    try:
        completed = subprocess.run(
            [pdftotext_command, str(pdf_path), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise AnchorError(f"unable to execute {pdftotext_command}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise AnchorError(f"unable to inspect publication PDF text: {detail}")
    if "DEMO / EVALUATION ONLY" not in completed.stdout:
        raise AnchorError("publication PDF is missing DEMO / EVALUATION ONLY text marker")


def build_manifest(
    *,
    repo_root: Path,
    anchor_path: Path,
    intake_manifest_path: Path,
    whitepaper_commit: str,
    publication_status: str,
    pdf_path: Path,
    arxiv_path: Path,
    compatibility_intake_path: Path,
    pdftotext_command: str = "pdftotext",
) -> dict[str, Any]:
    if not _SHA_RE.fullmatch(whitepaper_commit):
        raise AnchorError(f"invalid whitepaper commit: {whitepaper_commit!r}")
    if publication_status not in _ALLOWED_STATUSES:
        raise AnchorError(f"unsupported publication status: {publication_status!r}")

    _assert_source_checkout(repo_root, whitepaper_commit)
    anchor = validate_anchor(anchor_path, repo_root)
    publication_source = validate_publication_source(
        anchor, repo_root, whitepaper_commit
    )
    intake_manifest = _read_json(intake_manifest_path)
    if intake_manifest.get("schema_version") != "wp-intake.v1":
        raise AnchorError("current intake manifest must use schema wp-intake.v1")
    if intake_manifest.get("commit_sha") != anchor["producer"]["product_sha"]:
        raise AnchorError("current intake does not match the stable-v5 producer commit")
    if hashlib.sha256(intake_manifest_path.read_bytes()).hexdigest() != anchor[
        "consumer"
    ]["manifest_sha256"]:
        raise AnchorError("current intake manifest bytes do not match the stable-v5 anchor")
    producer_stamp = (intake_manifest.get("whitepaper_consumer") or {}).get(
        "producer"
    ) or {}
    for field in ("repo", "workflow", "run_id", "bundle_sha256"):
        if producer_stamp.get(field) != anchor["producer"].get(field):
            raise AnchorError(
                f"current intake producer {field} does not match the stable-v5 anchor"
            )
    _assert_pdf_marker(pdf_path, pdftotext_command)
    compatibility_intake = _artifact(
        compatibility_intake_path, "stable-v5-intake-compatibility.zip"
    )
    if compatibility_intake["sha256"] != anchor["export"]["expected_sha256"]:
        raise AnchorError(
            "compatibility intake ZIP does not match the frozen stable-v5 export digest"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "publication_status": publication_status,
        "claims": {
            "customer_evidence_eligible": False,
            "customer_evidence_disposition": "characterization_only",
            "legal_or_compliance_certification": False,
            "public_marketplace_go_live": False,
            "regulator_approval": False,
        },
        "artifact_profile": {
            "name": "demo_evaluation_only",
            "pdf_text_marker_required": "DEMO / EVALUATION ONLY",
        },
        "whitepaper": {
            "repo": WHITEPAPER_REPO,
            **publication_source,
        },
        "intake_anchor": {
            "path": anchor_path.as_posix(),
            "anchor_id": anchor["anchor_id"],
            "intake_commit": anchor["consumer"]["intake_commit"],
            "producer_repo": anchor["producer"]["repo"],
            "producer_product_sha": anchor["producer"]["product_sha"],
            "producer_run_id": anchor["producer"]["run_id"],
            "producer_bundle_sha256": anchor["producer"]["bundle_sha256"],
            "compatibility_exporter": anchor["export"]["script"],
            "compatibility_exporter_sha256": anchor["export"]["script_sha256"],
            "compatibility_export_sha256": anchor["export"]["expected_sha256"],
            "compatibility_export_disposition": (
                "git_reconstructed_projection_not_original_attested_zip"
            ),
        },
        "artifacts": {
            "pdf": _artifact(pdf_path, "whitepaper.pdf"),
            "arxiv_source": _artifact(
                arxiv_path, "whitepaper_arxiv_source.zip"
            ),
            "compatibility_intake": compatibility_intake,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anchor", default="baselines/stable-v5-characterization.json"
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--intake-manifest", default="intake/manifest.json")
    parser.add_argument("--whitepaper-commit", required=True)
    parser.add_argument(
        "--publication-status",
        choices=sorted(_ALLOWED_STATUSES),
        default="candidate_not_published",
    )
    parser.add_argument("--pdf", default="dist/whitepaper.pdf")
    parser.add_argument("--arxiv", default="dist/whitepaper_arxiv_source.zip")
    parser.add_argument(
        "--compatibility-intake",
        default="dist/stable-v5-intake-compatibility.zip",
    )
    parser.add_argument("--output", default="dist/publication-manifest.json")
    parser.add_argument("--pdftotext", default="pdftotext")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(
            repo_root=Path(args.repo_root),
            anchor_path=Path(args.anchor),
            intake_manifest_path=Path(args.intake_manifest),
            whitepaper_commit=args.whitepaper_commit,
            publication_status=args.publication_status,
            pdf_path=Path(args.pdf),
            arxiv_path=Path(args.arxiv),
            compatibility_intake_path=Path(args.compatibility_intake),
            pdftotext_command=args.pdftotext,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except AnchorError as exc:
        parser.error(str(exc))
    print(f"Wrote publication manifest to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate untracked TeX identity macros for a candidate build."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
PRODUCT_TAG_OBJECT = "3a0ea6e4faea9d61aabcedebab2a838624fb587d"
DOCUMENT_VERSION = "WP-5.0.1-candidate.1"


class IdentityError(ValueError):
    """Raised when a candidate identity would be false or incomplete."""


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise IdentityError(completed.stderr.strip() or "unable to resolve Git identity")
    return completed.stdout.strip()


def _macro(name: str, value: str) -> str:
    if any(char in value for char in "{}\\\n\r"):
        raise IdentityError(f"unsafe TeX identity value for {name}")
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def build(root: Path, companion: Path, output: Path, require_clean: bool) -> dict[str, object]:
    root = root.resolve()
    companion = companion.resolve()
    commit = _git(root, "rev-parse", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain"))
    if require_clean and dirty:
        raise IdentityError("candidate identity requires a clean source checkout")
    if len(commit) != 40:
        raise IdentityError("whitepaper commit is not a full Git SHA")
    if not companion.is_file():
        raise IdentityError(f"companion ZIP is missing: {companion}")
    companion_bytes = companion.read_bytes()
    companion_sha = hashlib.sha256(companion_bytes).hexdigest()
    import zipfile

    try:
        with zipfile.ZipFile(companion) as archive:
            manifest = json.loads(archive.read("MANIFEST.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise IdentityError(f"unable to read companion manifest: {exc}") from exc
    paper = manifest.get("whitepaper") or {}
    product = manifest.get("product") or {}
    if paper.get("commit") != commit:
        raise IdentityError("companion whitepaper commit does not match checkout")
    if bool(paper.get("source_tree_dirty_at_build")) != dirty:
        raise IdentityError("companion dirty-state marker does not match checkout")
    if product.get("commit") != PRODUCT_COMMIT:
        raise IdentityError("companion product commit mismatch")
    if product.get("tag_object") != PRODUCT_TAG_OBJECT:
        raise IdentityError("companion product tag object mismatch")

    values = {
        "DocumentVersion": DOCUMENT_VERSION,
        "PublicationStatus": "CANDIDATE — NOT PUBLISHED",
        "PublicationAsOf": "5 August 2026",
        "ProductReleaseTag": "v5.0.1",
        "ProductCommitRaw": PRODUCT_COMMIT,
        "ProductTagObjectRaw": PRODUCT_TAG_OBJECT,
        "WhitepaperCommitRaw": commit,
        "WhitepaperTreeState": "clean" if not dirty else "dirty-development-build",
        "EvidenceRunRaw": "30765888408",
        "EvidenceRunAttemptRaw": "1",
        "EvidenceArtifactIdRaw": "8838967644",
        "EvidenceBundleShaRaw": "f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026",
        "RuntimeImageDigestRaw": "sha256:550efe26626cd58c88b61bbde4b778f718f34d7fb764695137488b0cef8f09ce",
        "CompanionFilenameRaw": companion.name,
        "CompanionShaRaw": companion_sha,
        "CompanionSizeRaw": str(len(companion_bytes)),
    }
    lines = ["% Auto-generated; deliberately untracked self-identity include."]
    lines.extend(_macro(name, value) for name, value in values.items())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "whitepaper_commit": commit,
        "source_tree_dirty": dirty,
        "companion_sha256": companion_sha,
        "companion_size": len(companion_bytes),
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--companion", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.repo_root,
                args.companion,
                args.output,
                args.require_clean,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

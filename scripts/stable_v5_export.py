#!/usr/bin/env python3
"""Frozen deterministic ZIP writer for the stable-v5 compatibility anchor.

Keep this module byte-stable. A future baseline that needs different export behavior should use
a new exporter path instead of changing this file.
"""

from __future__ import annotations

import io
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any


_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class StableExportError(ValueError):
    """Raised when a deterministic export request is unsafe or incomplete."""


def validate_entries(entries: Any) -> list[dict[str, str]]:
    if not isinstance(entries, list) or not entries:
        raise StableExportError("anchor export.entries must be a non-empty list")
    validated: list[dict[str, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise StableExportError(f"export.entries[{index}] must be an object")
        source = str(entry.get("source") or "")
        target = str(entry.get("target") or "")
        for value, label in ((source, "source"), (target, "target")):
            if (
                not value
                or not _SAFE_PATH_RE.fullmatch(value)
                or value.startswith("/")
                or ".." in Path(value).parts
            ):
                raise StableExportError(f"unsafe export {label}: {value!r}")
        if source != "config" and not source.startswith(("intake/", "config/")):
            raise StableExportError(
                f"export source is outside intake/config: {source!r}"
            )
        validated.append({"source": source.rstrip("/"), "target": target.rstrip("/")})
    return validated


def _git(repo_root: Path, *args: str, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise StableExportError(f"git {' '.join(args)} failed: {stderr}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8").strip()


def _tree_paths(repo_root: Path, commit: str, source: str) -> list[str]:
    output = _git(repo_root, "ls-tree", "-r", "--name-only", commit, "--", source)
    assert isinstance(output, str)
    paths = [line for line in output.splitlines() if line]
    if not paths:
        raise StableExportError(f"no files found for export source {source!r}")
    return paths


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    # Stored members avoid zlib-version sensitivity. The archive is a small
    # compatibility/provenance surface, so cross-runtime byte stability is more
    # important than compression ratio.
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_archive(repo_root: Path, commit: str, entries: Any) -> bytes:
    """Return stable ZIP bytes for the descriptor-selected files at ``commit``."""

    members: dict[str, bytes] = {}
    for entry in validate_entries(entries):
        source = entry["source"]
        target = entry["target"]
        source_paths = _tree_paths(repo_root, commit, source)
        source_is_file = len(source_paths) == 1 and source_paths[0] == source
        for source_path in source_paths:
            if source_is_file:
                target_path = target
            else:
                relative = source_path.removeprefix(source + "/")
                target_path = f"{target}/{relative}" if target else relative
            if target_path in members:
                raise StableExportError(f"duplicate export target: {target_path}")
            blob = _git(repo_root, "show", f"{commit}:{source_path}", binary=True)
            assert isinstance(blob, bytes)
            members[target_path] = blob

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            archive.writestr(_zip_info(name), members[name])
    return buffer.getvalue()

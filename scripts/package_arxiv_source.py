#!/usr/bin/env python3
"""Build the arXiv source ZIP with a strict allowlist and reproducible metadata."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path


_DIRECT_FILES = {".latexmkrc", "main.bbl", "main.tex"}
_SUFFIXES = {
    "bib": {".bib"},
    "figures": {".jpeg", ".jpg", ".pdf", ".png", ".svg"},
    "includes": {".tex"},
    "sections": {".tex"},
}
_CONTROLLED_GENERATED_SHA256 = {
    "includes/publication_profile.local.tex": (
        "1381ff968824d4a04e12dc0922057e3c454b844c5432c74a31836e90721dc131"
    ),
    "main.bbl": "3092100af2dcc070495f554dc1fd1e35aa07ebeb44ca57cebe8b03ca24d22b7f",
}


class PackageError(RuntimeError):
    """Raised when the source tree is outside the publication allowlist."""


def _tracked_paths(repo_root: Path) -> set[str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "-z",
            "--",
            *_DIRECT_FILES,
            *_SUFFIXES,
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PackageError(f"unable to resolve tracked publication sources: {detail}")
    try:
        return {
            value.decode("utf-8")
            for value in completed.stdout.split(b"\0")
            if value
        }
    except UnicodeDecodeError as exc:
        raise PackageError(f"tracked publication path is not UTF-8: {exc}") from exc


def _assert_reviewed_member(path: Path, rel: str, tracked: set[str]) -> None:
    if rel in tracked:
        return
    expected = _CONTROLLED_GENERATED_SHA256.get(rel)
    if expected is None:
        raise PackageError("untracked publication source is forbidden; name redacted")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise PackageError(
            f"controlled generated publication source {rel} has unexpected bytes: "
            f"expected={expected} actual={actual}"
        )


def _collect(repo_root: Path) -> list[tuple[Path, str]]:
    tracked = _tracked_paths(repo_root)
    members: list[tuple[Path, str]] = []
    for name in sorted(_DIRECT_FILES):
        path = repo_root / name
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise PackageError(f"publication source must be a regular file: {name}")
            _assert_reviewed_member(path, name, tracked)
            members.append((path, name))
    if not (repo_root / "main.tex").is_file() or "main.tex" not in tracked:
        raise PackageError("required publication source is missing: main.tex")
    if not (repo_root / "main.bbl").is_file():
        raise PackageError("required generated bibliography is missing: main.bbl")

    for directory, suffixes in sorted(_SUFFIXES.items()):
        root = repo_root / directory
        if root.is_symlink():
            raise PackageError(f"publication source symlinks are forbidden: {root}")
        if not root.is_dir():
            raise PackageError(f"required publication source directory is missing: {directory}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise PackageError("publication source symlinks are forbidden; name redacted")
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            if path.suffix.lower() not in suffixes:
                raise PackageError("unexpected publication source member; name redacted")
            _assert_reviewed_member(path, rel, tracked)
            members.append((path, rel))
    return sorted(members, key=lambda item: item[1])


def build_archive(*, repo_root: Path, output: Path, source_date_epoch: int) -> str:
    if source_date_epoch < 315532800:  # 1980-01-01, the ZIP timestamp floor.
        raise PackageError("SOURCE_DATE_EPOCH must be on or after 1980-01-01")
    members = _collect(repo_root)
    timestamp = time.gmtime(source_date_epoch)[:6]
    output.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    )
    temp_path = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for path, rel in members:
                info = zipfile.ZipInfo(f"arxiv/{rel}", date_time=timestamp)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, path.read_bytes())
        with zipfile.ZipFile(temp_path) as archive:
            expected = [f"arxiv/{rel}" for _path, rel in members]
            if archive.namelist() != expected:
                raise PackageError("arXiv archive member order/content mismatch")
            bad_member = archive.testzip()
            if bad_member is not None:
                raise PackageError(f"arXiv archive CRC validation failed: {bad_member}")
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    return str(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="dist/whitepaper_arxiv_source.zip")
    parser.add_argument("--source-date-epoch", required=True, type=int)
    args = parser.parse_args()
    try:
        result = build_archive(
            repo_root=Path(args.repo_root).resolve(),
            output=Path(args.output).resolve(),
            source_date_epoch=args.source_date_epoch,
        )
    except PackageError as exc:
        parser.error(str(exc))
    print(f"Wrote {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

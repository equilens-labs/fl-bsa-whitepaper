#!/usr/bin/env python3
"""Safely extract one bounded GitHub Actions artifact archive."""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import NoReturn


class ArtifactExtractionError(ValueError):
    """Raised when an Actions archive is unsafe or outside reviewed bounds."""


def _fail(message: str) -> NoReturn:
    raise ArtifactExtractionError(message)


def _target(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    raw_parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in raw_parts)
        or path.as_posix() != name.rstrip("/")
    ):
        _fail(f"unsafe archive member: {name!r}")
    return root.joinpath(*path.parts)


def extract(
    archive_path: Path,
    destination: Path,
    *,
    max_members: int,
    max_uncompressed_bytes: int,
) -> dict[str, int]:
    """Extract regular files and directories after validating the whole archive."""

    if max_members <= 0 or max_uncompressed_bytes <= 0:
        _fail("archive limits must be positive")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(members) > max_members:
                _fail(f"archive has too many members: {len(members)}")
            if len(names) != len(set(names)):
                _fail("archive contains duplicate member names")
            total = 0
            for member in members:
                _target(destination, member.filename)
                file_type = stat.S_IFMT(member.external_attr >> 16)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    _fail(f"archive contains a non-regular member: {member.filename}")
                if member.file_size < 0:
                    _fail(f"archive member has an invalid size: {member.filename}")
                total += member.file_size
                if total > max_uncompressed_bytes:
                    _fail(f"archive expands beyond {max_uncompressed_bytes} bytes")

            destination.mkdir(parents=True, exist_ok=False)
            for member in members:
                target = _target(destination, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    except ArtifactExtractionError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArtifactExtractionError(
            f"unable to extract Actions archive: {exc}"
        ) from exc
    return {"members": len(members), "uncompressed_bytes": total}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--max-members", type=int, default=10_000)
    parser.add_argument("--max-uncompressed-bytes", type=int, default=512 * 1024 * 1024)
    args = parser.parse_args()
    try:
        result = extract(
            args.archive,
            args.destination,
            max_members=args.max_members,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
    except ArtifactExtractionError as exc:
        print(f"artifact extraction failed: {exc}", file=sys.stderr)
        return 2
    print(
        f"Actions artifact extracted: members={result['members']} "
        f"uncompressed_bytes={result['uncompressed_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

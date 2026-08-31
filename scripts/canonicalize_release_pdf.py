#!/usr/bin/env python3
"""Canonicalize a release PDF and prove the protected rewrite is idempotent."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MUTOOL_PATH = Path("/usr/bin/mutool")
MUTOOL_VERSION = "1.23.10"
MUTOOL_CLEAN_ARGUMENTS = ("clean", "-gggg", "-D")
MAX_RELEASE_PDF_BYTES = 64 * 1024 * 1024
MUTOOL_TIMEOUT_SECONDS = 180


class ReleasePdfCanonicalizationError(RuntimeError):
    """Raised when release PDF canonicalization cannot be proved safe and stable."""


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _validate_pdf_stat(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise ReleasePdfCanonicalizationError(
            "release PDF must be one regular non-link file"
        )
    if not 0 < info.st_size <= MAX_RELEASE_PDF_BYTES:
        raise ReleasePdfCanonicalizationError("release PDF has an invalid size")


def _open_pdf(path: Path) -> tuple[int, tuple[int, int, int, int, int, int]]:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_CLOEXEC"):
        raise ReleasePdfCanonicalizationError(
            "release PDF canonicalization requires no-follow file access"
        )
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    except OSError as exc:
        raise ReleasePdfCanonicalizationError(
            "release PDF must be one readable regular non-link file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _validate_pdf_stat(before)
        if os.pread(descriptor, 5, 0) != b"%PDF-":
            raise ReleasePdfCanonicalizationError("release PDF has an invalid header")
        after = os.fstat(descriptor)
        if _stat_identity(after) != _stat_identity(before):
            raise ReleasePdfCanonicalizationError(
                "release PDF changed while it was being opened"
            )
        return descriptor, _stat_identity(before)
    except (OSError, ReleasePdfCanonicalizationError):
        os.close(descriptor)
        raise


def _file_identity(path: Path) -> tuple[int, int, int, int, int, int]:
    descriptor, identity = _open_pdf(path)
    os.close(descriptor)
    return identity


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    try:
        while chunk := os.pread(descriptor, 1024 * 1024, offset):
            digest.update(chunk)
            offset += len(chunk)
    except OSError as exc:
        raise ReleasePdfCanonicalizationError("release PDF could not be hashed") from exc
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    descriptor, _ = _open_pdf(path)
    try:
        return _sha256_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _snapshot_descriptor(descriptor: int, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ReleasePdfCanonicalizationError("release PDF snapshot already exists")
    offset = 0
    try:
        with destination.open("xb") as output:
            while chunk := os.pread(descriptor, 1024 * 1024, offset):
                output.write(chunk)
                offset += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        destination.chmod(0o600)
    except OSError as exc:
        raise ReleasePdfCanonicalizationError(
            "release PDF could not be snapshotted"
        ) from exc
    _file_identity(destination)


def _assert_source_unchanged(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, int, int, int, int, int],
    expected_sha256: str,
) -> None:
    try:
        descriptor_identity = _stat_identity(os.fstat(descriptor))
    except OSError as exc:
        raise ReleasePdfCanonicalizationError(
            "release PDF could not be revalidated"
        ) from exc
    try:
        current_descriptor, path_identity = _open_pdf(path)
    except ReleasePdfCanonicalizationError as exc:
        raise ReleasePdfCanonicalizationError(
            "release PDF changed while it was being canonicalized"
        ) from exc
    try:
        descriptor_sha256 = _sha256_descriptor(descriptor)
        path_sha256 = _sha256_descriptor(current_descriptor)
        descriptor_identity_after = _stat_identity(os.fstat(descriptor))
        path_identity_after = _stat_identity(os.fstat(current_descriptor))
    finally:
        os.close(current_descriptor)
    if (
        descriptor_identity != expected_identity
        or descriptor_identity_after != expected_identity
        or path_identity != expected_identity
        or path_identity_after != expected_identity
        or descriptor_sha256 != expected_sha256
        or path_sha256 != expected_sha256
    ):
        raise ReleasePdfCanonicalizationError(
            "release PDF changed while it was being canonicalized"
        )


def _same_bytes(left: Path, right: Path) -> bool:
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_handle, right.open("rb") as right_handle:
            while True:
                left_chunk = left_handle.read(1024 * 1024)
                right_chunk = right_handle.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError as exc:
        raise ReleasePdfCanonicalizationError(
            "canonical release PDFs could not be compared"
        ) from exc


def _validate_mutool(
    mutool_path: Path,
    *,
    expected_uid: int,
    expected_version: str,
) -> str:
    if not mutool_path.is_absolute():
        raise ReleasePdfCanonicalizationError("mutool path must be absolute")
    try:
        info = mutool_path.lstat()
    except OSError as exc:
        raise ReleasePdfCanonicalizationError("PDF canonicalization dependency is unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or stat.S_IMODE(info.st_mode) & 0o022
        or not info.st_mode & 0o111
    ):
        raise ReleasePdfCanonicalizationError(
            "PDF canonicalization executable is not trusted"
        )
    try:
        result = subprocess.run(  # noqa: S603
            [str(mutool_path), "-v"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=10,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleasePdfCanonicalizationError(
            "PDF canonicalization dependency could not be identified"
        ) from exc
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
    required = f"mutool version {expected_version}"
    if result.returncode != 0 or output != required:
        raise ReleasePdfCanonicalizationError(
            f"PDF canonicalization requires {required}; observed {output!r}"
        )
    return expected_version


def _run_clean(mutool_path: Path, source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ReleasePdfCanonicalizationError("canonical PDF destination already exists")
    try:
        result = subprocess.run(  # noqa: S603
            [str(mutool_path), *MUTOOL_CLEAN_ARGUMENTS, str(source), str(destination)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=MUTOOL_TIMEOUT_SECONDS,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleasePdfCanonicalizationError("release PDF could not be canonicalized") from exc
    if result.returncode != 0:
        raise ReleasePdfCanonicalizationError("release PDF could not be canonicalized")
    _file_identity(destination)


def canonicalize(
    pdf_path: Path,
    *,
    mutool_path: Path = MUTOOL_PATH,
    expected_uid: int = 0,
    expected_version: str = MUTOOL_VERSION,
) -> dict[str, Any]:
    """Replace ``pdf_path`` atomically with one stable protected-clean representation."""

    pdf_path = pdf_path.absolute()
    source_descriptor, source_identity = _open_pdf(pdf_path)
    try:
        version = _validate_mutool(
            mutool_path,
            expected_uid=expected_uid,
            expected_version=expected_version,
        )
        source_sha256 = _sha256_descriptor(source_descriptor)
        with tempfile.TemporaryDirectory(
            prefix=".flbsa-release-pdf-", dir=pdf_path.parent
        ) as temporary:
            temporary_root = Path(temporary)
            source_snapshot = temporary_root / "source.pdf"
            canonical = temporary_root / "canonical.pdf"
            fixed_point = temporary_root / "fixed-point.pdf"
            _snapshot_descriptor(source_descriptor, source_snapshot)
            if _sha256(source_snapshot) != source_sha256:
                raise ReleasePdfCanonicalizationError(
                    "release PDF changed while it was being canonicalized"
                )
            _assert_source_unchanged(
                pdf_path,
                source_descriptor,
                source_identity,
                source_sha256,
            )
            _run_clean(mutool_path, source_snapshot, canonical)
            _run_clean(mutool_path, canonical, fixed_point)
            if not _same_bytes(canonical, fixed_point):
                raise ReleasePdfCanonicalizationError(
                    "release PDF canonicalization did not reach a byte-stable fixed point"
                )
            canonical.chmod(0o644)
            _assert_source_unchanged(
                pdf_path,
                source_descriptor,
                source_identity,
                source_sha256,
            )
            os.replace(canonical, pdf_path)
    except ReleasePdfCanonicalizationError:
        raise
    except OSError as exc:
        raise ReleasePdfCanonicalizationError(
            "canonical release PDF could not replace the rendered source"
        ) from exc
    finally:
        os.close(source_descriptor)

    final_identity = _file_identity(pdf_path)
    return {
        "arguments": list(MUTOOL_CLEAN_ARGUMENTS),
        "mutool_version": version,
        "schema_version": "flbsa.release_pdf_canonicalization.v1",
        "sha256": _sha256(pdf_path),
        "size_bytes": final_identity[3],
        "status": "canonical",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    try:
        result = canonicalize(args.pdf)
    except ReleasePdfCanonicalizationError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

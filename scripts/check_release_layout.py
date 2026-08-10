#!/usr/bin/env python3
"""Reject material horizontal overflow in a compiled release-paper log."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

_MAX_LOG_BYTES = 10 * 1024 * 1024
_OVERFULL_HBOX_RE = re.compile(
    r"Overfull \\hbox \((?P<points>[0-9]+(?:\.[0-9]+)?)pt too wide\)"
)
_OUTPUT_RE = re.compile(
    r"^Output written on main\.pdf \([1-9][0-9]* pages?, [1-9][0-9]* bytes\)\.$",
    re.MULTILINE,
)


class ReleaseLayoutError(ValueError):
    """Raised when the release PDF has a material layout overflow."""


def overfull_hboxes(log_text: str, *, max_overfull_pt: float) -> list[float]:
    """Return horizontal overflows strictly larger than the reviewed tolerance."""

    if not math.isfinite(max_overfull_pt) or max_overfull_pt < 0:
        raise ReleaseLayoutError(
            "maximum overfull tolerance must be finite and non-negative"
        )
    return [
        points
        for match in _OVERFULL_HBOX_RE.finditer(log_text)
        if (points := float(match.group("points"))) > max_overfull_pt
    ]


def validate_release_layout(log_path: Path, *, max_overfull_pt: float) -> None:
    """Require one bounded TeX log with no material horizontal overflow."""

    try:
        size = log_path.stat().st_size
        if size <= 0 or size > _MAX_LOG_BYTES:
            raise ReleaseLayoutError(f"release TeX log has an unsafe size: {size}")
        log_text = log_path.read_text(encoding="utf-8")
    except ReleaseLayoutError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ReleaseLayoutError(f"unable to read release TeX log: {exc}") from exc

    if _OUTPUT_RE.search(log_text) is None:
        raise ReleaseLayoutError("release TeX log does not record a completed main.pdf")
    overflows = overfull_hboxes(log_text, max_overfull_pt=max_overfull_pt)
    if overflows:
        raise ReleaseLayoutError(
            "release PDF has material horizontal overflow: "
            f"count={len(overflows)} largest={max(overflows):.5f}pt "
            f"tolerance={max_overfull_pt:g}pt"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--max-overfull-pt", type=float, default=2.0)
    args = parser.parse_args()
    try:
        validate_release_layout(args.log, max_overfull_pt=args.max_overfull_pt)
    except ReleaseLayoutError as exc:
        parser.error(str(exc))
    print("Release PDF layout overflow check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

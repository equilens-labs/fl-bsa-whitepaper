#!/usr/bin/env python3
"""Reject material horizontal overflow in a compiled release-paper log."""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

_MAX_LOG_BYTES = 10 * 1024 * 1024
_MAX_PDF_BYTES = 50 * 1024 * 1024
_FOOTER_RESERVED_PT = 55.0
_OVERFULL_HBOX_RE = re.compile(
    r"Overfull \\hbox \((?P<points>[0-9]+(?:\.[0-9]+)?)pt too wide\)"
)
_TECHNICAL_FOOTER_RE = re.compile(
    r"WP-[0-9]+\.[0-9]+\.[0-9]+-public\.[1-9][0-9]* "
    r"\| PUBLIC TECHNICAL CHARACTERIZATION"
)
_BARE_PAGE_NUMBER_RE = re.compile(r"(?:[1-9][0-9]*|[ivxlcdm]+)")


class ReleaseLayoutError(ValueError):
    """Raised when the release PDF has a material layout overflow."""


def footer_intrusions_from_bbox_xml(
    xml_text: str, *, reserved_footer_pt: float = _FOOTER_RESERVED_PT
) -> list[str]:
    """Return non-footer text blocks inside the reserved bottom margin."""

    if not math.isfinite(reserved_footer_pt) or reserved_footer_pt <= 0:
        raise ReleaseLayoutError("reserved footer size must be finite and positive")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ReleaseLayoutError(
            f"unable to parse PDF bounding-box XML: {exc}"
        ) from exc

    intrusions: list[str] = []
    pages = [
        element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "page"
    ]
    if not pages:
        raise ReleaseLayoutError("PDF bounding-box XML contains no pages")
    for page_number, page in enumerate(pages, start=1):
        try:
            page_height = float(page.attrib["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ReleaseLayoutError("PDF bounding-box page height is invalid") from exc
        if not math.isfinite(page_height) or page_height <= reserved_footer_pt:
            raise ReleaseLayoutError("PDF bounding-box page height is invalid")
        footer_start = page_height - reserved_footer_pt
        for block in page.iter():
            if block.tag.rsplit("}", 1)[-1] != "block":
                continue
            try:
                y_min = float(block.attrib["yMin"])
                y_max = float(block.attrib["yMax"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ReleaseLayoutError(
                    "PDF bounding-box block position is invalid"
                ) from exc
            if not math.isfinite(y_min) or not math.isfinite(y_max) or y_min > y_max:
                raise ReleaseLayoutError("PDF bounding-box block position is invalid")
            if y_max <= footer_start:
                continue
            words = [
                (word.text or "").strip()
                for word in block.iter()
                if word.tag.rsplit("}", 1)[-1] == "word" and (word.text or "").strip()
            ]
            text = " ".join(words)
            if (
                text
                in {
                    "Equilens",
                    "DEMO / EVALUATION ONLY",
                    f"page {page_number}",
                }
                or _TECHNICAL_FOOTER_RE.fullmatch(text)
                or _BARE_PAGE_NUMBER_RE.fullmatch(text)
            ):
                continue
            intrusions.append(f"page={page_number} yMin={y_min:.2f} text={text!r}")
    return intrusions


def validate_release_pdf_footer(
    pdf_path: Path, *, reserved_footer_pt: float = _FOOTER_RESERVED_PT
) -> None:
    """Reject body or caption text that enters the fixed footer area."""

    try:
        size = pdf_path.stat().st_size
    except OSError as exc:
        raise ReleaseLayoutError(f"unable to inspect release PDF: {exc}") from exc
    if size <= 0 or size > _MAX_PDF_BYTES:
        raise ReleaseLayoutError(f"release PDF has an unsafe size: {size}")
    try:
        result = subprocess.run(
            ["pdftotext", "-bbox-layout", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseLayoutError(
            f"unable to extract release PDF layout: {exc}"
        ) from exc
    intrusions = footer_intrusions_from_bbox_xml(
        result.stdout, reserved_footer_pt=reserved_footer_pt
    )
    if intrusions:
        raise ReleaseLayoutError(
            "release PDF content enters the reserved footer area: "
            + "; ".join(intrusions)
        )


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


def validate_release_layout(
    log_path: Path, *, max_overfull_pt: float, expected_pdf: Path = Path("main.pdf")
) -> None:
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

    expected_output = expected_pdf.as_posix()
    completed_output_re = re.compile(
        rf"^Output written on {re.escape(expected_output)} "
        r"\([1-9][0-9]* pages?, [1-9][0-9]*(?:\n[0-9]+)* bytes\)\.$",
        re.MULTILINE,
    )
    if completed_output_re.search(log_text) is None:
        raise ReleaseLayoutError(
            f"release TeX log does not record a completed {expected_output}"
        )
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
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--max-overfull-pt", type=float, default=2.0)
    args = parser.parse_args()
    try:
        validate_release_layout(
            args.log,
            max_overfull_pt=args.max_overfull_pt,
            expected_pdf=args.pdf or Path("main.pdf"),
        )
        if args.pdf is not None:
            validate_release_pdf_footer(args.pdf)
    except ReleaseLayoutError as exc:
        parser.error(str(exc))
    print("Release PDF layout overflow check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

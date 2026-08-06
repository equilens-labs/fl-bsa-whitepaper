#!/usr/bin/env python3
"""Enforce the candidate PDF's reviewed tag-structure invariants.

This is a narrow Poppler-based regression check, not a PDF/UA validator and not
a substitute for PAC/veraPDF or assistive-technology review.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


class StructureError(RuntimeError):
    """Raised when a reviewed PDF tag invariant is absent."""


def _run_pdfinfo(pdfinfo: str, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            [pdfinfo, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise StructureError(f"unable to execute {pdfinfo}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
        raise StructureError(f"{pdfinfo} {' '.join(args)} failed: {detail}")
    return result


def inspect(
    pdf_path: Path,
    *,
    expected_header_cells: int,
    expected_figures: int,
    pdfinfo: str = "pdfinfo",
) -> dict[str, int | str | bool]:
    if not pdf_path.is_file():
        raise StructureError(f"PDF does not exist: {pdf_path}")

    summary = _run_pdfinfo(pdfinfo, str(pdf_path)).stdout
    tagged = re.search(r"^Tagged:\s+yes\s*$", summary, flags=re.MULTILINE) is not None
    no_suspects = (
        re.search(r"^Suspects:\s+no\s*$", summary, flags=re.MULTILINE) is not None
    )
    if not tagged:
        raise StructureError("candidate PDF is not tagged")
    if not no_suspects:
        raise StructureError("candidate PDF reports structural suspects")

    metadata = _run_pdfinfo(pdfinfo, "-meta", str(pdf_path)).stdout
    if "<rdf:li>en-US</rdf:li>" not in metadata:
        raise StructureError("candidate PDF is missing en-US document-language metadata")
    if "<pdfuaid:part>" in metadata:
        raise StructureError(
            "candidate PDF must not declare formal PDF/UA conformance before external validation"
        )

    structure_result = _run_pdfinfo(pdfinfo, "-struct", str(pdf_path))
    structure = structure_result.stdout
    header_cells = len(re.findall(r"^\s*TH\s+<", structure, flags=re.MULTILINE))
    column_scopes = len(
        re.findall(r"^\s*/Scope\s+/Column\s*$", structure, flags=re.MULTILINE)
    )
    figures = len(re.findall(r"^\s*Figure\s+<", structure, flags=re.MULTILINE))

    if header_cells != expected_header_cells:
        raise StructureError(
            f"expected {expected_header_cells} TH cells, found {header_cells}"
        )
    if column_scopes != expected_header_cells:
        raise StructureError(
            f"expected {expected_header_cells} column-scoped TH cells, found {column_scopes}"
        )
    if figures != expected_figures:
        raise StructureError(f"expected {expected_figures} Figure tags, found {figures}")

    return {
        "status": "verified",
        "tagged": tagged,
        "structural_suspects": False,
        "language": "en-US",
        "pdfua_claimed": False,
        "table_header_cells": header_cells,
        "column_scoped_header_cells": column_scopes,
        "figure_tags": figures,
        "poppler_warning_lines": len(structure_result.stderr.splitlines()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--expected-header-cells", type=int, required=True)
    parser.add_argument("--expected-figures", type=int, required=True)
    parser.add_argument("--pdfinfo", default="pdfinfo")
    args = parser.parse_args()
    try:
        result = inspect(
            args.pdf,
            expected_header_cells=args.expected_header_cells,
            expected_figures=args.expected_figures,
            pdfinfo=args.pdfinfo,
        )
    except StructureError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

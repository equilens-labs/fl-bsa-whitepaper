#!/usr/bin/env python3
"""Reject active, attached, or interactive content in a release PDF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader
from PyPDF2.generic import ArrayObject, DictionaryObject, IndirectObject


class PassivePdfError(RuntimeError):
    """Raised when the release PDF cannot be proved passive."""


# Keep these structural policy sets aligned with the product artifact scanner.
FORBIDDEN_PDF_KEYS = frozenset(
    {
        "/AA",
        "/AcroForm",
        "/AF",
        "/Collection",
        "/EF",
        "/EmbeddedFiles",
        "/JavaScript",
        "/JS",
        "/OpenAction",
        "/RichMediaContent",
        "/XFA",
    }
)
FORBIDDEN_PDF_NAMES = frozenset(
    {
        "/EmbeddedFile",
        "/FileAttachment",
        "/Filespec",
        "/ImportData",
        "/JavaScript",
        "/Launch",
        "/Movie",
        "/RichMedia",
        "/Sound",
        "/SubmitForm",
    }
)
MAX_PDF_OBJECTS = 100_000
MAX_PDF_OBJECT_DEPTH = 128


def _xref_objects(reader: PdfReader) -> set[tuple[int, int]]:
    objects = {
        (int(object_id), int(generation))
        for generation, object_ids in reader.xref.items()
        for object_id in object_ids
        if int(object_id) != 0
    }
    objects.update(
        (int(object_id), 0)
        for object_id in getattr(reader, "xref_objStm", {})
        if int(object_id) != 0
    )
    return objects


def inspect(pdf_path: Path) -> dict[str, int | str]:
    if not pdf_path.is_file():
        raise PassivePdfError(f"PDF does not exist: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception as exc:
        raise PassivePdfError("release PDF could not be parsed safely") from exc
    if reader.is_encrypted:
        raise PassivePdfError("encrypted release PDFs are not inspectable")
    try:
        xref_objects = _xref_objects(reader)
    except Exception as exc:
        raise PassivePdfError("release PDF could not be parsed safely") from exc
    if len(xref_objects) > MAX_PDF_OBJECTS:
        raise PassivePdfError("release PDF object count exceeds the protected limit")

    stack: list[tuple[Any, int]] = [
        (IndirectObject(object_id, generation, reader), 0)
        for object_id, generation in sorted(xref_objects)
    ]
    stack.append((reader.trailer, 0))
    seen_indirect: set[tuple[int, int]] = set()
    seen_direct: set[int] = set()
    object_count = 0

    while stack:
        value, depth = stack.pop()
        if depth > MAX_PDF_OBJECT_DEPTH:
            raise PassivePdfError(
                "release PDF object graph exceeds the protected depth limit"
            )
        if isinstance(value, IndirectObject):
            identity = (value.idnum, value.generation)
            if identity in seen_indirect:
                continue
            seen_indirect.add(identity)
            try:
                value = value.get_object()
            except Exception as exc:
                raise PassivePdfError(
                    "release PDF contains an unreadable indirect object"
                ) from exc

        if isinstance(value, DictionaryObject | ArrayObject):
            direct_identity = id(value)
            if direct_identity in seen_direct:
                continue
            seen_direct.add(direct_identity)
            object_count += 1
            if object_count > MAX_PDF_OBJECTS:
                raise PassivePdfError(
                    "release PDF object count exceeds the protected limit"
                )

        if isinstance(value, DictionaryObject):
            keys = {str(key) for key in value}
            if keys & FORBIDDEN_PDF_KEYS or any(
                str(item) in FORBIDDEN_PDF_NAMES for item in value.values()
            ):
                raise PassivePdfError(
                    "release PDF contains active, attached, or interactive content"
                )
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, ArrayObject):
            stack.extend((item, depth + 1) for item in value)

    return {"status": "verified", "objects_inspected": object_count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.pdf)
    except PassivePdfError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

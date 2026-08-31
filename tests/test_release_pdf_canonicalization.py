import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "canonicalize_release_pdf.py"
SPEC = importlib.util.spec_from_file_location(
    "release_pdf_canonicalization_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
CANONICAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANONICAL)


class ReleasePdfCanonicalizationTests(unittest.TestCase):
    def _fake_mutool(
        self,
        root: Path,
        *,
        version: str,
        mode: str,
        mutate_path: Path | None = None,
    ) -> Path:
        executable = root / "mutool"
        executable.write_text(
            """#!/usr/bin/env python3
import pathlib
import shutil
import sys

if sys.argv[1:] == ["-v"]:
    print("mutool version VERSION")
    raise SystemExit(0)
if sys.argv[1:4] != ["clean", "-gggg", "-D"] or len(sys.argv) != 6:
    raise SystemExit(2)
source = pathlib.Path(sys.argv[4])
destination = pathlib.Path(sys.argv[5])
payload = source.read_bytes()
if "MODE" == "mutate-second" and source.name == "canonical.pdf":
    pathlib.Path(MUTATE_PATH).write_bytes(
        b"%PDF-1.7\\nnewer concurrent output\\n%%EOF\\n"
    )
if "MODE" in {"stable", "mutate-second"}:
    marker = b"\\n% protected-canonical\\n"
    if marker not in payload:
        payload += marker
elif "MODE" == "unstable":
    payload += b"x"
else:
    shutil.copyfile(source, destination)
    raise SystemExit(0)
destination.write_bytes(payload)
""".replace("VERSION", version)
            .replace("MODE", mode)
            .replace("MUTATE_PATH", repr(str(mutate_path))),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable

    def test_canonicalizes_once_and_reaches_a_fixed_point(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "whitepaper.pdf"
            original = b"%PDF-1.7\nsafe aggregate paper\n%%EOF\n"
            pdf.write_bytes(original)
            mutool = self._fake_mutool(root, version="1.23.10", mode="stable")

            first = CANONICAL.canonicalize(
                pdf,
                mutool_path=mutool,
                expected_uid=os.getuid(),
            )
            first_bytes = pdf.read_bytes()
            second = CANONICAL.canonicalize(
                pdf,
                mutool_path=mutool,
                expected_uid=os.getuid(),
            )

            self.assertNotEqual(original, first_bytes)
            self.assertEqual(first_bytes, pdf.read_bytes())
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual("canonical", first["status"])
            self.assertEqual("1.23.10", first["mutool_version"])
            self.assertEqual(["clean", "-gggg", "-D"], first["arguments"])
            self.assertEqual(0o644, pdf.stat().st_mode & 0o777)

    def test_rejects_a_transform_that_is_not_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "whitepaper.pdf"
            original = b"%PDF-1.7\nsafe aggregate paper\n%%EOF\n"
            pdf.write_bytes(original)
            mutool = self._fake_mutool(root, version="1.23.10", mode="unstable")

            with self.assertRaisesRegex(
                CANONICAL.ReleasePdfCanonicalizationError,
                "byte-stable fixed point",
            ):
                CANONICAL.canonicalize(
                    pdf,
                    mutool_path=mutool,
                    expected_uid=os.getuid(),
                )

            self.assertEqual(original, pdf.read_bytes())

    def test_rejects_a_source_change_during_the_second_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "whitepaper.pdf"
            pdf.write_bytes(b"%PDF-1.7\nsafe aggregate paper\n%%EOF\n")
            mutool = self._fake_mutool(
                root,
                version="1.23.10",
                mode="mutate-second",
                mutate_path=pdf,
            )

            with self.assertRaisesRegex(
                CANONICAL.ReleasePdfCanonicalizationError,
                "changed while it was being canonicalized",
            ):
                CANONICAL.canonicalize(
                    pdf,
                    mutool_path=mutool,
                    expected_uid=os.getuid(),
                )

            self.assertEqual(
                b"%PDF-1.7\nnewer concurrent output\n%%EOF\n",
                pdf.read_bytes(),
            )

    def test_rejects_an_unreviewed_mutool_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "whitepaper.pdf"
            original = b"%PDF-1.7\nsafe aggregate paper\n%%EOF\n"
            pdf.write_bytes(original)
            mutool = self._fake_mutool(root, version="9.9.9", mode="stable")

            with self.assertRaisesRegex(
                CANONICAL.ReleasePdfCanonicalizationError,
                "requires mutool version 1.23.10",
            ):
                CANONICAL.canonicalize(
                    pdf,
                    mutool_path=mutool,
                    expected_uid=os.getuid(),
                )

            self.assertEqual(original, pdf.read_bytes())

    def test_rejects_a_linked_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.pdf"
            target.write_bytes(b"%PDF-1.7\nsafe aggregate paper\n%%EOF\n")
            linked = root / "whitepaper.pdf"
            linked.symlink_to(target)
            mutool = self._fake_mutool(root, version="1.23.10", mode="stable")

            with self.assertRaisesRegex(
                CANONICAL.ReleasePdfCanonicalizationError,
                "regular non-link file",
            ):
                CANONICAL.canonicalize(
                    linked,
                    mutool_path=mutool,
                    expected_uid=os.getuid(),
                )

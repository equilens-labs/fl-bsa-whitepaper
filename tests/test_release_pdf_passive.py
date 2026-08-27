import importlib.util
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter
from PyPDF2.generic import DictionaryObject, NameObject, TextStringObject

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_release_pdf_passive.py"
SPEC = importlib.util.spec_from_file_location(
    "release_pdf_passive_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
PASSIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PASSIVE)


class ReleasePdfPassiveTests(unittest.TestCase):
    def _write(self, writer: PdfWriter, path: Path) -> None:
        with path.open("wb") as handle:
            writer.write(handle)

    def test_accepts_plain_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            self._write(writer, path)

            result = PASSIVE.inspect(path)

        self.assertEqual("verified", result["status"])
        self.assertGreater(result["objects_inspected"], 0)

    def test_rejects_catalog_open_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "open-action.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
                {
                    NameObject("/S"): NameObject("/GoTo"),
                    NameObject("/D"): TextStringObject("initial-view-destination"),
                }
            )
            self._write(writer, path)

            with self.assertRaisesRegex(
                PASSIVE.PassivePdfError,
                "active, attached, or interactive",
            ):
                PASSIVE.inspect(path)

    def test_rejects_embedded_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "attachment.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_attachment("hidden.txt", b"blocked")
            self._write(writer, path)

            with self.assertRaisesRegex(
                PASSIVE.PassivePdfError,
                "active, attached, or interactive",
            ):
                PASSIVE.inspect(path)

    def test_rejects_empty_password_encryption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "encrypted.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.encrypt(user_password="")
            self._write(writer, path)

            with self.assertRaisesRegex(
                PASSIVE.PassivePdfError,
                "encrypted release PDFs are not inspectable",
            ):
                PASSIVE.inspect(path)

    def test_fails_closed_on_malformed_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "malformed.pdf"
            path.write_bytes(b"not a PDF")

            with self.assertRaisesRegex(
                PASSIVE.PassivePdfError,
                "could not be parsed safely",
            ):
                PASSIVE.inspect(path)


if __name__ == "__main__":
    unittest.main()

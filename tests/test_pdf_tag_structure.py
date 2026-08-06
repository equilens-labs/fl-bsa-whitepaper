import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    module_path = ROOT / "scripts" / "check_pdf_tag_structure.py"
    spec = importlib.util.spec_from_file_location("pdf_tag_checker_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PDF tag-structure checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _completed(stdout: str, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["pdfinfo"], 0, stdout=stdout, stderr=stderr)


class PdfTagStructureTests(unittest.TestCase):
    def _inspect(self, *, header_cells: int = 26, pdfua_claimed: bool = False):
        summary = "Tagged: yes\nSuspects: no\n"
        metadata = "<rdf:li>en-US</rdf:li>\n"
        if pdfua_claimed:
            metadata += "<pdfuaid:part>1</pdfuaid:part>\n"
        structure = "".join(
            "TH <ID>:\n  /Scope /Column\n" for _ in range(header_cells)
        ) + "".join("Figure <ID>:\n" for _ in range(7))

        def fake_pdfinfo(_command: str, *args: str):
            if args[0] == "-meta":
                return _completed(metadata)
            if args[0] == "-struct":
                return _completed(structure)
            return _completed(summary)

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "candidate.pdf"
            pdf.write_bytes(b"fixture")
            with mock.patch.object(CHECKER, "_run_pdfinfo", side_effect=fake_pdfinfo):
                return CHECKER.inspect(
                    pdf,
                    expected_header_cells=26,
                    expected_figures=7,
                )

    def test_exact_reviewed_structure_passes(self) -> None:
        result = self._inspect()
        self.assertEqual("verified", result["status"])
        self.assertEqual(26, result["table_header_cells"])
        self.assertEqual(26, result["column_scoped_header_cells"])
        self.assertIs(result["pdfua_claimed"], False)

    def test_missing_header_or_unvalidated_pdfua_claim_fails_closed(self) -> None:
        with self.assertRaisesRegex(CHECKER.StructureError, "expected 26 TH cells"):
            self._inspect(header_cells=25)
        with self.assertRaisesRegex(CHECKER.StructureError, "formal PDF/UA"):
            self._inspect(pdfua_claimed=True)


if __name__ == "__main__":
    unittest.main()

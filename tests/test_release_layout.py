import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_release_layout",
    ROOT / "scripts" / "check_release_layout.py",
)
assert SPEC and SPEC.loader
LAYOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAYOUT)


class ReleaseLayoutTests(unittest.TestCase):
    def test_accepts_clean_and_sub_tolerance_layout(self) -> None:
        log = "\n".join(
            (
                "Output written on main.pdf (11 pages).",
                r"Overfull \hbox (0.7421pt too wide) in paragraph at lines 1--2",
                r"Overfull \hbox (1.35002pt too wide) in paragraph at lines 3--4",
            )
        )
        self.assertEqual([], LAYOUT.overfull_hboxes(log, max_overfull_pt=2.0))

    def test_rejects_each_material_overflow(self) -> None:
        log = "\n".join(
            (
                r"Overfull \hbox (42.58508pt too wide) in paragraph at lines 9--10",
                r"Overfull \hbox (190.05319pt too wide) in paragraph at lines 7--8",
            )
        )
        self.assertEqual(
            [42.58508, 190.05319],
            LAYOUT.overfull_hboxes(log, max_overfull_pt=2.0),
        )

    def test_file_validation_rejects_material_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "main.log"
            log.write_text(
                "Output written on main.pdf (11 pages, 437460 bytes).\n"
                r"Overfull \hbox (78.32256pt too wide) in paragraph at lines 15--20",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                LAYOUT.ReleaseLayoutError,
                r"count=1 largest=78\.32256pt tolerance=2pt",
            ):
                LAYOUT.validate_release_layout(log, max_overfull_pt=2.0)

    def test_rejects_missing_completed_pdf_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "main.log"
            log.write_text(
                "This is pdfTeX, but no output completed.\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                LAYOUT.ReleaseLayoutError, "does not record a completed main.pdf"
            ):
                LAYOUT.validate_release_layout(log, max_overfull_pt=2.0)

    def test_rejects_negative_or_nonfinite_tolerance(self) -> None:
        for tolerance in (-0.1, float("nan"), float("inf")):
            with self.subTest(tolerance=tolerance):
                with self.assertRaisesRegex(
                    LAYOUT.ReleaseLayoutError, "must be finite and non-negative"
                ):
                    LAYOUT.overfull_hboxes("", max_overfull_pt=tolerance)


if __name__ == "__main__":
    unittest.main()

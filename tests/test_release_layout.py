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
    def test_footer_bbox_accepts_only_expected_footer_blocks(self) -> None:
        xml = """<?xml version="1.0"?>
        <html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
          <page width="595.28" height="841.89">
            <flow><block xMin="70" yMin="740" xMax="500" yMax="752">
              <line><word>Body</word></line></block></flow>
            <flow><block xMin="72" yMin="800.2" xMax="110" yMax="810.5">
              <line><word>Equilens</word></line></block></flow>
            <flow><block xMin="250" yMin="802.2" xMax="350" yMax="809.3">
              <line><word>DEMO</word><word>/</word><word>EVALUATION</word><word>ONLY</word></line>
            </block></flow>
            <flow><block xMin="500" yMin="800.2" xMax="530" yMax="810.5">
              <line><word>page</word><word>1</word></line></block></flow>
          </page>
        </doc></body></html>"""
        self.assertEqual([], LAYOUT.footer_intrusions_from_bbox_xml(xml))

    def test_footer_bbox_rejects_caption_collision(self) -> None:
        xml = """<?xml version="1.0"?>
        <html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
          <page width="595.28" height="841.89">
            <flow><block xMin="70" yMin="796.98" xMax="480" yMax="805.77">
              <line><word>certification.</word></line></block></flow>
            <flow><block xMin="72" yMin="800.2" xMax="110" yMax="810.5">
              <line><word>Equilens</word></line></block></flow>
          </page>
        </doc></body></html>"""
        self.assertEqual(
            ["page=1 yMin=796.98 text='certification.'"],
            LAYOUT.footer_intrusions_from_bbox_xml(xml),
        )

    def test_footer_bbox_accepts_technical_identity_and_bare_page_number(self) -> None:
        xml = """<?xml version="1.0"?>
        <html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
          <page width="595.28" height="841.89">
            <flow><block xMin="72" yMin="800.2" xMax="420" yMax="810.5">
              <line><word>WP-5.0.8-public.1</word><word>|</word><word>PUBLIC</word>
              <word>TECHNICAL</word><word>CHARACTERIZATION</word></line></block></flow>
            <flow><block xMin="500" yMin="800.2" xMax="530" yMax="810.5">
              <line><word>1</word></line></block></flow>
          </page>
        </doc></body></html>"""
        self.assertEqual([], LAYOUT.footer_intrusions_from_bbox_xml(xml))

    def test_footer_bbox_rejects_unreviewed_technical_footer(self) -> None:
        xml = """<?xml version="1.0"?>
        <html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
          <page width="595.28" height="841.89">
            <flow><block xMin="72" yMin="800.2" xMax="420" yMax="810.5">
              <line><word>WP-5.0.8-public.0</word><word>|</word><word>PUBLIC</word>
              <word>TECHNICAL</word><word>CHARACTERIZATION</word></line></block></flow>
            <flow><block xMin="500" yMin="800.2" xMax="530" yMax="810.5">
              <line><word>2</word></line></block></flow>
          </page>
        </doc></body></html>"""
        self.assertEqual(
            [
                "page=1 yMin=800.20 text='WP-5.0.8-public.0 | PUBLIC TECHNICAL CHARACTERIZATION'",
            ],
            LAYOUT.footer_intrusions_from_bbox_xml(xml),
        )

    def test_footer_bbox_accepts_roman_page_number(self) -> None:
        xml = """<?xml version="1.0"?>
        <html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
          <page width="595.28" height="841.89">
            <flow><block xMin="500" yMin="800.2" xMax="530" yMax="810.5">
              <line><word>ii</word></line></block></flow>
          </page>
        </doc></body></html>"""
        self.assertEqual([], LAYOUT.footer_intrusions_from_bbox_xml(xml))

    def test_footer_bbox_rejects_block_that_straddles_reserved_boundary(self) -> None:
        xml = """<?xml version="1.0"?>
        <html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
          <page width="595.28" height="841.89">
            <flow><block xMin="70" yMin="780.00" xMax="480" yMax="790.00">
              <line><word>straddling</word><word>caption</word></line></block></flow>
          </page>
        </doc></body></html>"""
        self.assertEqual(
            ["page=1 yMin=780.00 text='straddling caption'"],
            LAYOUT.footer_intrusions_from_bbox_xml(xml),
        )

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

    def test_accepts_exact_named_pdf_with_wrapped_byte_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "whitepaper.log"
            log.write_text(
                "Output written on build/technical/v5.0.8/render/whitepaper.pdf "
                "(21 pages, 56624\n0 bytes).\n",
                encoding="utf-8",
            )
            LAYOUT.validate_release_layout(
                log,
                max_overfull_pt=2.0,
                expected_pdf=Path("build/technical/v5.0.8/render/whitepaper.pdf"),
            )

    def test_rejects_completed_marker_for_a_different_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "whitepaper.log"
            log.write_text(
                "Output written on stale.pdf (21 pages, 566240 bytes).\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                LAYOUT.ReleaseLayoutError,
                "does not record a completed expected.pdf",
            ):
                LAYOUT.validate_release_layout(
                    log,
                    max_overfull_pt=2.0,
                    expected_pdf=Path("expected.pdf"),
                )

    def test_rejects_negative_or_nonfinite_tolerance(self) -> None:
        for tolerance in (-0.1, float("nan"), float("inf")):
            with self.subTest(tolerance=tolerance):
                with self.assertRaisesRegex(
                    LAYOUT.ReleaseLayoutError, "must be finite and non-negative"
                ):
                    LAYOUT.overfull_hboxes("", max_overfull_pt=tolerance)


if __name__ == "__main__":
    unittest.main()

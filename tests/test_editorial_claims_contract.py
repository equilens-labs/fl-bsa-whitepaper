import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_preamble_module():
    module_path = ROOT / "scripts" / "gen_tex_preamble_from_manifest.py"
    spec = importlib.util.spec_from_file_location("gen_tex_preamble_from_manifest", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load gen_tex_preamble_from_manifest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EditorialClaimsContractTests(unittest.TestCase):
    def test_section_order_puts_product_context_before_math(self) -> None:
        main_tex = (ROOT / "main.tex").read_text(encoding="utf-8")

        expected_order = (
            r"\input{sections/01_executive_summary}",
            r"\input{sections/04_model_algorithm}",
            r"\input{sections/02_problem_estimands}",
            r"\input{sections/03_methods}",
            r"\input{sections/05_evaluation}",
            r"\input{sections/06_results}",
        )
        positions = [main_tex.index(fragment) for fragment in expected_order]
        self.assertEqual(positions, sorted(positions))

    def test_new_interpretive_claims_stay_fixture_scoped(self) -> None:
        joined = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "main.tex",
                "sections/01_executive_summary.tex",
                "sections/04_model_algorithm.tex",
                "sections/05_evaluation.tex",
                "sections/06_results.tex",
            )
        )

        self.assertIn("generated fixture", joined)
        self.assertIn("internal screen", joined)
        self.assertIn("mechanical control", joined)
        self.assertIn("not a causal counterfactual", joined)
        self.assertIn("not a generic product claim", joined)
        self.assertIn("material utility variation", joined)
        self.assertNotIn("Gate-WP", joined)
        self.assertNotIn("synthetic audit test split", joined)
        self.assertNotIn("localized to the decision labels", joined)

    def test_layout_contract_removes_known_float_and_link_issues(self) -> None:
        main_tex = (ROOT / "main.tex").read_text(encoding="utf-8")
        section_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "sections").glob("*.tex")
        )

        self.assertIn("colorlinks=true", main_tex)
        self.assertNotIn("pdfstandard=UA-1", main_tex)
        self.assertIn("lang=en-US", main_tex)
        self.assertIn("testphase={phase-III,math,table}", main_tex)
        self.assertIn("does not declare", main_tex)
        self.assertIn("round-pad=true", main_tex)
        self.assertNotIn("round-pad=false", main_tex)
        self.assertNotIn(r"\begin{longtable}", section_text)
        self.assertNotIn(r"\begin{table}[t]", section_text)
        self.assertNotIn(r"\begin{figure}[t]", section_text)
        self.assertNotIn(r"\clearpage" + "\n" + r"\section{Limitations", section_text)
        self.assertGreaterEqual(section_text.count("alt={"), 7)

    def test_every_data_table_declares_column_header_semantics(self) -> None:
        main_tex = (ROOT / "main.tex").read_text(encoding="utf-8")
        self.assertIn(
            r"\newcommand{\AccessibleTableHeaderRow}"
            r"{\tagpdfsetup{table-header-rows={1}}}",
            main_tex,
        )

        source_paths = [ROOT / "main.tex"]
        source_paths.extend(sorted((ROOT / "sections").glob("*.tex")))
        source_paths.extend(sorted((ROOT / "includes").glob("table_*.tex")))
        table_count = 0
        for path in source_paths:
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\\begin\{tabular\}", source):
                preceding_line = source[: match.start()].rstrip().splitlines()[-1].strip()
                self.assertEqual(r"\AccessibleTableHeaderRow", preceding_line, path)
                table_count += 1
        self.assertEqual(10, table_count)

        for layout_source in (
            ROOT / "main.tex",
            ROOT / "sections" / "01_executive_summary.tex",
            ROOT / "sections" / "appendix_a_sap.tex",
        ):
            self.assertIn("KeyValueList", layout_source.read_text(encoding="utf-8"))

    def test_oci_digest_display_chunks_only_digest_hex(self) -> None:
        module = _load_preamble_module()
        digest = (
            "ghcr.io/equilens-labs/fl-bsa-runtime@sha256:"
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )

        rendered = module._tex_texttt_breakable(digest)

        self.assertEqual(r"\nolinkurl{" + digest + "}", rendered)
        self.assertNotIn("01234567 89abcdef", rendered)
        self.assertNotIn("fl-bsa-run time", rendered)
        self.assertNotIn("sha 256", rendered)

    def test_plot_generator_contract_for_three_slice_air(self) -> None:
        source = (ROOT / "scripts" / "gen_plots_from_intake.py").read_text(encoding="utf-8")

        self.assertIn("--fairness-slices", source)
        self.assertIn("gender_air_slices.pdf", source)
        self.assertIn("Adverse Impact Ratio (AIR)", source)
        self.assertIn('"CreationDate": None', source)
        self.assertIn('"ModDate": None', source)
        self.assertEqual(5, source.count("_save_pdf(fig, out_path)"))
        self.assertNotIn("fig.suptitle", source)
        self.assertLess(
            source.index("\n    _maybe_set_style()\n"),
            source.index("if not selection_path.exists() or not metrics_path.exists()"),
        )

    def test_regulatory_bib_titles_are_case_protected(self) -> None:
        bib = (ROOT / "bib" / "references.bib").read_text(encoding="utf-8")

        self.assertIn("{{Equal Credit Opportunity Act (Regulation B)}; Final Rule", bib)
        self.assertIn("{{Regulation} ({EU}) 2024/1689", bib)
        self.assertIn("Common Interpretation of the Uniform Guidelines", bib)
        self.assertIn("{Revised Guidance on Model Risk Management}", bib)

    def test_gender_slice_counts_render_as_integers(self) -> None:
        table = (ROOT / "includes" / "table_gender_air_slices.tex").read_text(
            encoding="utf-8"
        )

        self.assertIn(r"\begin{tabular}{lrrSSSl}", table)
        for count in ("1451", "1549", "4837", "5163", "4835", "5165"):
            with self.subTest(count=count):
                self.assertRegex(table, rf"(^| & ){count}( &|\\\\)")
                self.assertNotIn(rf"\num{{{count}}}", table)
        self.assertIsNone(re.search(r"\b\d+\.000\b", table))


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LatexCompatibilityContractTests(unittest.TestCase):
    def test_tagged_description_lists_do_not_pass_enumitem_keys_to_block(self) -> None:
        for relative_path in (
            "sections/appendix_b_metrics_defs.tex",
            "sections/appendix_e_manifest_summary.tex",
        ):
            with self.subTest(path=relative_path):
                source = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertNotIn(r"\begin{description}[", source)
                self.assertIn(r"\setlist[description]", source)
                self.assertIn(r"\begin{description}", source)


if __name__ == "__main__":
    unittest.main()

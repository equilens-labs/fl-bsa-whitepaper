import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LatexCompatibilityContractTests(unittest.TestCase):
    def test_tagged_description_lists_use_only_supported_configuration(self) -> None:
        sources = [ROOT / "main.tex", *sorted((ROOT / "sections").glob("*.tex"))]
        description_count = 0
        for path in sources:
            source = path.read_text(encoding="utf-8")
            description_count += source.count(r"\begin{description}")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(
                    re.search(r"\\begin\s*\{description\}\s*\[", source)
                )
                for setting in re.findall(
                    r"\\setlist\s*\[description[^]]*\]\s*\{([^}]*)\}", source
                ):
                    self.assertIsNone(
                        re.search(r"(?:^|,)\s*(?:style|labelindent\*?)\s*=", setting)
                    )
        self.assertEqual(3, description_count)


if __name__ == "__main__":
    unittest.main()

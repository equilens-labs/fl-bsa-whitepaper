import hashlib
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_verapdf_ua_preflight.py"
SPEC = importlib.util.spec_from_file_location("ua_preflight_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


def _report(*, clause: str = "5", message: str | None = None) -> str:
    failure = message or (
        "The document metadata stream doesn't contain PDF/UA Identification Schema"
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<report>
  <jobs><job>
    <validationReport jobEndStatus="normal"
      profileName="PDF/UA-1 validation profile" isCompliant="false">
      <details passedRules="105" failedRules="1"
        passedChecks="136156" failedChecks="1">
        <rule specification="ISO 14289-1:2014" clause="{clause}"
          testNumber="1" status="failed" failedChecks="1">
          <check status="failed"><errorMessage>{failure}</errorMessage></check>
        </rule>
      </details>
    </validationReport>
  </job></jobs>
  <batchSummary totalJobs="1" failedToParse="0">
    <validationReports compliant="0" nonCompliant="1" failedJobs="0">1</validationReports>
  </batchSummary>
</report>
"""


class PdfAccessibilityContractTests(unittest.TestCase):
    def _verify(self, xml: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.xml"
            path.write_text(xml, encoding="utf-8")
            return PREFLIGHT.verify(path)

    def test_preflight_accepts_only_the_withheld_ua_declaration(self) -> None:
        result = self._verify(_report())
        self.assertEqual("verified", result["status"])
        self.assertEqual(0, result["substantive_rule_failures"])
        self.assertEqual(1, result["permitted_declaration_failures"])

    def test_preflight_rejects_a_substantive_failure(self) -> None:
        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "failed-rule clause"):
            self._verify(_report(clause="7.21.5"))

    def test_pdftex_space_metric_is_source_backed_and_packaged(self) -> None:
        pl = (ROOT / "pdftexspace.pl").read_text(encoding="utf-8")
        tfm = (ROOT / "pdftexspace.tfm").read_bytes()
        packager = (ROOT / "scripts" / "package_arxiv_source.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, pl.count("0.333333"))
        self.assertEqual(
            "5bf34a42c7309ab211e67c67e62372a85cda4878c65b2f55acd142fa509a773c",
            hashlib.sha256(tfm).hexdigest(),
        )
        self.assertIn('"pdftexspace.pl"', packager)
        self.assertIn('"pdftexspace.tfm"', packager)

    def test_semantic_repairs_and_pinned_preflight_are_guarded(self) -> None:
        main = (ROOT / "main.tex").read_text(encoding="utf-8")
        appendix = (ROOT / "sections" / "appendix_f_hyperparams.tex").read_text(
            encoding="utf-8"
        )
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "latex.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(r"\def\@BTnormal", main)
        self.assertIn(r"\tagmcbegin{artifact}", main)
        self.assertIn("pdfversion=1.7", main)
        self.assertIn("math/alt/use=true", main)
        for link_type in ("GoTo", "GoToR", "URI"):
            self.assertIn(
                rf"\socket_assign_plug:nn {{ hyp/link/{link_type}/Contents }} {{ default }}",
                main,
            )
        self.assertIsNone(re.search(r"(?m)^\s*\\maketitle\b", main))
        self.assertIn(r"\MakeCoverTitle", main)
        self.assertIn(r"\subsection*{Branch difference register}", appendix)
        self.assertNotIn(r"\paragraph{Branch difference register.}", appendix)

        image = (
            "ghcr.io/verapdf/cli@sha256:"
            "595d7791a9321975cde6b7f5393beed98d76167ea6c39af191704462a4fa8b9d"
        )
        self.assertIn(image, makefile)
        self.assertIn("$(MAKE) ua-preflight", makefile)
        self.assertIn("make ua-preflight", workflow)


if __name__ == "__main__":
    unittest.main()

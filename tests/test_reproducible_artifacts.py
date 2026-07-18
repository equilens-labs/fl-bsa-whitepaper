import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "package_arxiv_source.py"
SPEC = importlib.util.spec_from_file_location("package_arxiv_source_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class ReproducibleArtifactTests(unittest.TestCase):
    def _commit_sources(self, root: Path) -> None:
        if not (root / "main.bbl").exists():
            (root / "main.bbl").write_text("generated bibliography\n", encoding="utf-8")
        subprocess.run(["git", "init", "-b", "main", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-m", "sources"], check=True)

    def test_arxiv_archive_is_repeatable_and_replaces_stale_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            output = Path(tmp) / "whitepaper_arxiv_source.zip"
            for directory in ("bib", "figures", "includes", "sections"):
                (root / directory).mkdir(parents=True)
            (root / "main.tex").write_text("document\n", encoding="utf-8")
            (root / "bib" / "references.bib").write_text("bib\n", encoding="utf-8")
            (root / "figures" / "plot.pdf").write_bytes(b"pdf")
            (root / "includes" / "generated.tex").write_text("include\n", encoding="utf-8")
            (root / "sections" / "one.tex").write_text("section\n", encoding="utf-8")
            self._commit_sources(root)

            with zipfile.ZipFile(output, "w") as stale:
                stale.writestr("arxiv/deleted-secret.txt", b"must disappear")

            PACKAGE.build_archive(
                repo_root=root, output=output, source_date_epoch=1784332800
            )
            first = output.read_bytes()
            PACKAGE.build_archive(
                repo_root=root, output=output, source_date_epoch=1784332800
            )
            second = output.read_bytes()

            self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(second).digest())
            with zipfile.ZipFile(output) as archive:
                self.assertNotIn("arxiv/deleted-secret.txt", archive.namelist())
                self.assertEqual(
                    archive.namelist(),
                    [
                        "arxiv/bib/references.bib",
                        "arxiv/figures/plot.pdf",
                        "arxiv/includes/generated.tex",
                        "arxiv/main.bbl",
                        "arxiv/main.tex",
                        "arxiv/sections/one.tex",
                    ],
                )
                self.assertIsNone(archive.testzip())

    def test_arxiv_archive_rejects_unreviewed_source_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            for directory in ("bib", "figures", "includes", "sections"):
                (root / directory).mkdir(parents=True)
            (root / "main.tex").write_text("document\n", encoding="utf-8")
            (root / "bib" / "private.log").write_text("blocked\n", encoding="utf-8")
            self._commit_sources(root)
            with self.assertRaisesRegex(PACKAGE.PackageError, "unexpected publication source"):
                PACKAGE.build_archive(
                    repo_root=root,
                    output=Path(tmp) / "out.zip",
                    source_date_epoch=1784332800,
                )

    def test_arxiv_archive_rejects_symlinked_required_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "source"
            external = temp / "external"
            external.mkdir()
            (external / "leaked.bib").write_text("private\n", encoding="utf-8")
            root.mkdir()
            for directory in ("figures", "includes", "sections"):
                (root / directory).mkdir()
            (root / "main.tex").write_text("document\n", encoding="utf-8")
            (root / "bib").symlink_to(external, target_is_directory=True)
            self._commit_sources(root)

            with self.assertRaisesRegex(PACKAGE.PackageError, "symlinks are forbidden"):
                PACKAGE.build_archive(
                    repo_root=root,
                    output=temp / "out.zip",
                    source_date_epoch=1784332800,
                )

    def test_arxiv_archive_rejects_untracked_suffix_allowed_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            for directory in ("bib", "figures", "includes", "sections"):
                (root / directory).mkdir(parents=True)
            (root / "main.tex").write_text("document\n", encoding="utf-8")
            (root / "bib" / "references.bib").write_text("bib\n", encoding="utf-8")
            self._commit_sources(root)
            (root / "sections" / "private.tex").write_text("private\n", encoding="utf-8")

            with self.assertRaisesRegex(PACKAGE.PackageError, "untracked publication source"):
                PACKAGE.build_archive(
                    repo_root=root,
                    output=Path(tmp) / "out.zip",
                    source_date_epoch=1784332800,
                )

    def test_pdf_source_declares_reproducible_metadata_contract(self) -> None:
        main = (ROOT / "main.tex").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for primitive in ("pdfinfoomitdate", "pdftrailerid", "pdfsuppressptexinfo"):
            self.assertIn(primitive, main)
        self.assertIn("SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct HEAD)", makefile)
        self.assertIn("export FORCE_SOURCE_DATE = 1", makefile)
        self.assertIn("export TZ = UTC", makefile)

    def test_workflows_pin_tex_runtime_and_hashed_python_closure(self) -> None:
        image = (
            "ghcr.io/xu-cheng/texlive-full@sha256:"
            "d9bfb267e3e3f5e0820ca86e867ee59ebb133fc29561bb28677d9b5a1a9e84ff"
        )
        for name in ("latex.yml", "pull-wp-intake.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(workflow=name):
                self.assertIn(image, workflow)
                self.assertNotIn("texlive-full:latest", workflow)
                self.assertIn(
                    "python -m pip install --require-hashes "
                    "-r requirements-ci-linux-x86_64.lock",
                    workflow,
                )
                compile_step = workflow.split("- name: Compile LaTeX", 1)[1]
                self.assertIn(
                    'export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"',
                    compile_step,
                )
                self.assertIn("export FORCE_SOURCE_DATE=1", compile_step)
                self.assertIn("export TZ=UTC", compile_step)
                self.assertIn('test "$SOURCE_DATE_EPOCH" -gt 0', compile_step)

        lock = (ROOT / "requirements-ci-linux-x86_64.lock").read_text(
            encoding="utf-8"
        )
        self.assertIn("--only-binary=:all:", lock)
        requirements = [
            line for line in lock.splitlines() if line and not line.startswith(("#", " ", "--"))
        ]
        self.assertGreaterEqual(len(requirements), 15)
        self.assertTrue(all("==" in line and line.endswith("\\") for line in requirements))
        self.assertEqual(len(requirements), lock.count("--hash=sha256:"))


if __name__ == "__main__":
    unittest.main()

import importlib.util
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extract_actions_artifact", ROOT / "scripts" / "extract_actions_artifact.py"
)
assert SPEC and SPEC.loader
EXTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACT)


class ExtractActionsArtifactTests(unittest.TestCase):
    def test_extracts_bounded_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "artifact.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("one/file.txt", b"evidence")
            result = EXTRACT.extract(
                archive,
                root / "expanded",
                max_members=2,
                max_uncompressed_bytes=100,
            )
            self.assertEqual({"members": 1, "uncompressed_bytes": 8}, result)
            self.assertEqual(b"evidence", (root / "expanded/one/file.txt").read_bytes())

    def test_rejects_traversal_duplicate_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases: list[tuple[str, callable]] = []

            def traversal(output: zipfile.ZipFile) -> None:
                output.writestr("../escape", b"x")

            def duplicate(output: zipfile.ZipFile) -> None:
                output.writestr("same", b"x")
                output.writestr("same", b"y")

            def symlink(output: zipfile.ZipFile) -> None:
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                output.writestr(info, b"target")

            cases.extend(
                [
                    ("unsafe archive member", traversal),
                    ("duplicate member", duplicate),
                    ("non-regular member", symlink),
                ]
            )
            for index, (error, writer) in enumerate(cases):
                with self.subTest(error=error):
                    archive = root / f"case-{index}.zip"
                    with zipfile.ZipFile(archive, "w") as output:
                        writer(output)
                    with self.assertRaisesRegex(EXTRACT.ArtifactExtractionError, error):
                        EXTRACT.extract(
                            archive,
                            root / f"expanded-{index}",
                            max_members=10,
                            max_uncompressed_bytes=100,
                        )

    def test_rejects_noncanonical_member_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, name in enumerate(
                ("./member", "directory//member", "/absolute", "windows\\member")
            ):
                with self.subTest(name=name):
                    archive = root / f"noncanonical-{index}.zip"
                    with zipfile.ZipFile(archive, "w") as output:
                        output.writestr(name, b"x")
                    with self.assertRaisesRegex(
                        EXTRACT.ArtifactExtractionError, "unsafe archive member"
                    ):
                        EXTRACT.extract(
                            archive,
                            root / f"noncanonical-output-{index}",
                            max_members=10,
                            max_uncompressed_bytes=100,
                        )

    def test_rejects_member_and_expansion_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "artifact.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("one", b"12345")
                output.writestr("two", b"67890")
            with self.assertRaisesRegex(EXTRACT.ArtifactExtractionError, "too many"):
                EXTRACT.extract(
                    archive,
                    root / "member-limit",
                    max_members=1,
                    max_uncompressed_bytes=100,
                )
            with self.assertRaisesRegex(
                EXTRACT.ArtifactExtractionError, "expands beyond"
            ):
                EXTRACT.extract(
                    archive,
                    root / "size-limit",
                    max_members=10,
                    max_uncompressed_bytes=9,
                )


if __name__ == "__main__":
    unittest.main()

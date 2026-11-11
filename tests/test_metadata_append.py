"""v3.31.40: `key+:` and `pdfmd-options.metadata-append` (entry 3du, point 20): a metadata value that adds to the layers below
instead of replacing them; the layer order itself (global < folders' `.pdfmd/` < the document folder's metadata < the document).
Real builds to LaTeX through pdfmd; the finished `\\author{...}` is what is read back."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Layers(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.folder = self.root / "course" / "LR1"
        write(self.root / "course" / ".pdfmd" / "metadata.yaml", "author: [Course A, Course B]\n")

    def build(self, front: str = "", extra_files: dict | None = None, config: str | None = None, name: str = "d.md"):
        for relative, text in (extra_files or {}).items():
            write(self.folder / relative, text)
        if config is not None:
            write(self.root / "course" / ".pdfmd" / "config.yaml", config)
        write(self.folder / name, f"---\ntitle: T\n{front}---\n\nText.\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "--to", "tex", "-o", "out.tex", "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.folder, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        return done

    def authors(self, done=None, **kwargs) -> list[str]:
        done = done or self.build(**kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        tex = (self.folder / "out.tex").read_text(encoding="utf-8")
        found = re.search(r"\\author\{(.*?)\}\n", tex, re.DOTALL)
        self.assertTrue(found, tex[:600])
        return [part.strip() for part in found.group(1).split("\\and")]

    def test_command_line_append_is_the_top_layer(self):
        write(self.folder / "d.md", "---\nauthor+: Doc\n---\n\nText.\n")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache"),
                       "XDG_DATA_HOME": str(self.root / "data")}
        for args in (("-M", "author+=Charlie"), ("--metadata", "author+:Charlie"),
                     ("-Mauthor+=Charlie",), ("--metadata=author+=Charlie",)):
            with self.subTest(args=args):
                done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "d.md", "--to", "native", "-s",
                                       "-o", "out.native", *args], cwd=self.folder, env=environment,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                result = (self.folder / "out.native").read_text(encoding="utf-8")
                for name in ('Str "Course"', 'Str "A"', 'Str "B"', 'Str "Doc"', 'Str "Charlie"'):
                    self.assertIn(name, result)
                self.assertNotIn('author+', result)
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "d.md", "--to", "native", "-s", "-o", "out.native",
                               "-M", "author=Replacement"], cwd=self.folder, env=environment,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = (self.folder / "out.native").read_text(encoding="utf-8")
        self.assertIn("Replacement", result)
        self.assertNotIn("Course A", result)
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "d.md", "--to", "native", "-s", "-o", "out.native",
                               "-M", "author=First", "-M", "author=Second", "-M", "author+=Third"],
                              cwd=self.folder, env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = (self.folder / "out.native").read_text(encoding="utf-8")
        self.assertLess(result.index('"First"'), result.index('"Second"'))
        self.assertLess(result.index('"Second"'), result.index('"Third"'))

    def test_the_order_is_course_then_documents_folder_then_the_document(self):
        self.assertEqual(self.authors(), ["Course A", "Course B"])
        self.assertEqual(self.authors(extra_files={"metadata.yaml": "author: [Folder X]\n"}), ["Folder X"])
        self.assertEqual(self.authors(front="author: [Doc]\n"), ["Doc"])

    def test_a_plus_key_adds_to_the_layers_below(self):
        self.assertEqual(self.authors(front="author+: [Doc]\n"), ["Course A", "Course B", "Doc"])
        self.assertEqual(self.authors(front="author+: Single\n"), ["Course A", "Course B", "Single"])

    def test_a_plus_key_with_nothing_below_is_just_its_own_names(self):
        (self.root / "course" / ".pdfmd" / "metadata.yaml").unlink()
        self.assertEqual(self.authors(front="author+: [Doc]\n"), ["Doc"])

    def test_both_keys_in_one_place_take_the_plain_one_first(self):
        self.assertEqual(self.authors(front="author: [First]\nauthor+: [Second]\n"), ["First", "Second"])

    def test_a_layer_can_add_to_another(self):
        folder_plus = {"metadata.yaml": "author+: [Folder X]\n"}
        self.assertEqual(self.authors(front="author+: [Doc]\n", extra_files=folder_plus),
                         ["Course A", "Course B", "Folder X", "Doc"])

    def test_the_setting_makes_the_documents_own_value_add(self):
        config = "options:\n  metadata-append: [author]\n"
        self.assertEqual(self.authors(front="author: [Doc]\n", config=config), ["Course A", "Course B", "Doc"])
        self.assertEqual(self.authors(front="author: [Doc]\n", config="options:\n  metadata-append: other\n"), ["Doc"])

    def test_the_setting_can_be_the_documents_own_and_a_value_set_nowhere_below_stays_as_it_is(self):
        self.assertEqual(self.authors(front="pdfmd-options: {metadata-append: author}\nauthor: [Doc]\n"),
                         ["Course A", "Course B", "Doc"])
        (self.root / "course" / ".pdfmd" / "metadata.yaml").unlink()
        self.assertEqual(self.authors(front="pdfmd-options: {metadata-append: author}\nauthor: [Doc]\n"), ["Doc"])

    def test_the_markup_of_a_name_survives(self):
        self.assertEqual(self.authors(front="author+: ['B. Student \\role{conducting}']\n"),
                         ["Course A", "Course B", "B. Student \\role{conducting}"])

    def test_a_build_without_a_plus_key_or_the_setting_adds_nothing(self):
        md = write(self.folder / "plain.md", "---\ntitle: T\nauthor: [X]\n---\n\nText.\n")
        self.assertEqual(pdfmd.metadata_append_args(md, [self.root / "course" / ".pdfmd" / "metadata.yaml"]), [])

    def test_a_mapping_cannot_be_appended_to_and_header_includes_is_left_to_pdfmd(self):
        done = self.build(front="institute+: {name: X}\n", extra_files={"metadata.yaml": "institute: {name: Y}\n"})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("mapping", done.stderr)
        done = self.build(front="header-includes+: ['\\usepackage{x}']\n", name="e.md")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("header-includes", done.stderr)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Source(unittest.TestCase):
    """The assembled source holds the finished value and no `+` key, so a rebuild neither loses nor doubles a name."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.folder = self.root / "course" / "LR1"
        write(self.root / "course" / ".pdfmd" / "metadata.yaml", "author: [Course A]\n")
        write(self.root / "course" / ".pdfmd" / "config.yaml", "options:\n  metadata-append: [author]\n")
        write(self.folder / "metadata.yaml", "author+: [Folder X]\n")
        write(self.folder / "d.md", "---\ntitle: T\nauthor: [Doc]\n---\n\nText.\n")
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")}

    def run_pdfmd(self, cwd: Path, *args: str):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=cwd, capture_output=True, text=True, env=self.env)

    def authors_of(self, cwd: Path, name: str) -> list[str]:
        done = self.run_pdfmd(cwd, name, "--to", "tex", "-o", "o.tex", "--no-stamp", "--no-backup", "--no-auto", "crossref")
        self.assertEqual(done.returncode, 0, done.stderr)
        found = re.search(r"\\author\{(.*?)\}\n", (cwd / "o.tex").read_text(encoding="utf-8"), re.DOTALL)
        return [part.strip() for part in found.group(1).split("\\and")]

    def test_the_source_has_the_finished_names_once_and_a_rebuild_elsewhere_gives_them_once(self):
        expected = ["Course A", "Folder X", "Doc"]
        self.assertEqual(self.authors_of(self.folder, "d.md"), expected)
        done = self.run_pdfmd(self.folder, "d.md", "--assemble-only", "--embed-metadata", "-o", "src.md", "--no-stamp")
        self.assertEqual(done.returncode, 0, done.stderr)
        source = (self.folder / "src.md").read_text(encoding="utf-8")
        self.assertNotIn("author+", source)
        self.assertEqual(pdfmd.front_matter_dict(source)["author"], expected)
        self.assertEqual(pdfmd.front_matter_dict(source)["pdfmd-options"]["metadata-append"], [])
        elsewhere = self.root / "elsewhere"
        write(elsewhere / "src.md", source)
        write(elsewhere / ".pdfmd" / "config.yaml", "options:\n  metadata-append: [author]\n")      # a rebuild under the same folder setting
        write(elsewhere / ".pdfmd" / "metadata.yaml", "author: [Someone Else]\n")
        self.assertEqual(self.authors_of(elsewhere, "src.md"), expected)


if __name__ == "__main__":
    unittest.main()

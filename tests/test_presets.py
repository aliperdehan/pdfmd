"""v3.28.19: the global metadata can be switched off (--no-global-metadata, pdfmd-options.global-metadata, --setup) and
swapped for a preset (presets/NAME.yaml beside the config file: --preset, pdfmd-options.preset, name with or without .yaml)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Presets(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.home = self.root / "home"
        (self.home / "presets").mkdir(parents=True)
        (self.home / "metadata.yaml").write_text("author: Default Author\n", encoding="utf-8")
        (self.home / "presets" / "lab.yaml").write_text("author: Lab Author\n", encoding="utf-8")
        (self.home / "presets" / "course.yml").write_text("author: Course Author\n", encoding="utf-8")
        self.doc = self.root / "doc"
        self.doc.mkdir()
        self.write("d.md", "# A\n\nText.\n")

    def write(self, name: str, text: str, folder: Path | None = None) -> None:
        (folder or self.doc).joinpath(name).write_text(text, encoding="utf-8")

    def run_pdfmd(self, *args: str, config: str | None = None, ok: bool = True) -> subprocess.CompletedProcess:
        if config is not None:
            (self.home / "config.yaml").write_text(config, encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": str(self.home / "config.yaml"), "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.doc, env=env,
                              capture_output=True, text=True, timeout=300)
        if ok:
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def author(self, *args: str, **kwargs) -> str:
        """Whose name the LaTeX output carries."""
        self.run_pdfmd("d.md", "--to", "latex", "-o", "out.tex", *args, **kwargs)
        text = (self.doc / "out.tex").read_text(encoding="utf-8")
        (self.doc / "out.tex").unlink()
        return next((name for name in ("Default Author", "Lab Author", "Course Author") if name in text), "nobody")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
    def test_the_default_is_metadata_yaml(self):
        self.assertEqual(self.author(), "Default Author")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
    def test_a_preset_by_the_command_line_with_or_without_the_suffix(self):
        self.assertEqual(self.author("--preset", "lab"), "Lab Author")
        self.assertEqual(self.author("--preset", "lab.yaml"), "Lab Author")
        self.assertEqual(self.author("--preset", "course"), "Course Author")           # a .yml file
        self.assertEqual(self.author("--preset", "default"), "Default Author")
        self.assertEqual(self.author("--preset", str(self.home / "presets" / "lab.yaml")), "Lab Author")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
    def test_a_preset_by_the_document_the_folder_and_the_config(self):
        self.write("d.md", "---\npdfmd-options:\n  preset: lab.yaml\n---\n\n# A\n\nText.\n")
        self.assertEqual(self.author(), "Lab Author")
        self.write("d.md", "# A\n\nText.\n")
        self.write("metadata.yaml", "pdfmd-options:\n  preset: course\n")
        self.assertEqual(self.author(), "Course Author")
        (self.doc / "metadata.yaml").unlink()
        self.assertEqual(self.author(config="options:\n  preset: lab\n"), "Lab Author")
        self.assertEqual(self.author("--preset", "course"), "Course Author")           # the command line wins
        (self.home / "config.yaml").unlink()

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
    def test_the_global_metadata_can_be_switched_off_and_on_again(self):
        self.assertEqual(self.author("--no-global-metadata"), "nobody")
        self.assertEqual(self.author("--preset", "none"), "nobody")
        self.write("d.md", "---\npdfmd-options:\n  global-metadata: false\n---\n\n# A\n\nText.\n")
        self.assertEqual(self.author(), "nobody")
        self.assertEqual(self.author("--global-metadata"), "Default Author")           # the command line wins
        self.write("d.md", "# A\n\nText.\n")
        self.assertEqual(self.author(config="options:\n  global-metadata: false\n"), "nobody")
        self.assertEqual(self.author("--global-metadata"), "Default Author")
        (self.home / "config.yaml").unlink()

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
    def test_an_unknown_preset_stops_and_names_the_ones_there_are(self):
        done = self.run_pdfmd("d.md", "--to", "latex", "--preset", "nowhere", ok=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("unknown preset 'nowhere'", done.stdout + done.stderr)
        self.assertIn("lab", done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc (the CI native job has none)")
    def test_the_closing_lines_name_the_preset(self):
        done = self.run_pdfmd("d.md", "--to", "latex", "--preset", "lab")
        self.assertIn("preset lab", done.stdout)
        verbose = self.run_pdfmd("d.md", "--to", "latex", "--preset", "lab", "--verbose")
        self.assertIn("(the preset lab of pdfmd --setup)", verbose.stdout)

    def test_presets_lists_them_and_marks_the_one_in_use(self):
        done = self.run_pdfmd("--presets", "--preset", "lab")
        lines = done.stdout.splitlines()
        self.assertTrue(any(line.startswith("* lab") for line in lines), done.stdout)
        self.assertTrue(any(line.startswith("  default") for line in lines), done.stdout)
        self.assertTrue(any(line.startswith("  course") for line in lines), done.stdout)

    def test_setup_edits_a_preset_file(self):
        env = {**os.environ, "PDFMD_CONFIG": str(self.home / "config.yaml"), "PDFMD_NO_PROMPT": "1"}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--setup", "plain", "--preset", "fresh"],
                              cwd=self.doc, env=env, input="1\nNew Author\ns\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("New Author", (self.home / "presets" / "fresh.yaml").read_text(encoding="utf-8"))
        self.assertEqual((self.home / "metadata.yaml").read_text(encoding="utf-8"), "author: Default Author\n")


class Resolution(unittest.TestCase):
    def test_a_path_is_global_metadata_only_beside_the_config(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            old = os.environ.get("PDFMD_CONFIG")
            os.environ["PDFMD_CONFIG"] = str(home / "config.yaml")
            try:
                self.assertTrue(pdfmd.is_global_metadata(home / "metadata.yaml"))
                self.assertTrue(pdfmd.is_global_metadata(home / "presets" / "lab.yaml"))
                self.assertFalse(pdfmd.is_global_metadata(home / "other" / "metadata.yaml"))
                self.assertFalse(pdfmd.is_global_metadata(home / "presets" / "notes.txt"))
            finally:
                if old is None:
                    del os.environ["PDFMD_CONFIG"]
                else:
                    os.environ["PDFMD_CONFIG"] = old


class Esc(unittest.TestCase):
    def test_esc_leaves_the_full_screen_setup(self):
        try:
            from prompt_toolkit.input import create_pipe_input
            from prompt_toolkit.output import DummyOutput
        except ImportError:
            self.skipTest("needs prompt_toolkit")
        from pdfmd_setup import fancy, registry
        settings = registry.settings_for(["metadata"])
        stores: dict = {}
        with create_pipe_input() as pipe:
            pipe.send_text("\x1b")
            self.assertFalse(fancy.run(stores, settings, "config.yaml", input=pipe, output=DummyOutput()))


if __name__ == "__main__":
    unittest.main()

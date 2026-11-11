"""Picture embeds, `![[name.png|300]]` (entry 3ee, v3.32.25): the text transform, the lookup by name, and the whole build."""

from __future__ import annotations

import contextlib
import io
import os
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
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402
from pdfmd_obsidian import embed_images  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")


class Transform(unittest.TestCase):
    @staticmethod
    def found(name):
        return "img/" + name

    def run_on(self, text, **keywords):
        return embed_images(text, self.found, **keywords)

    def test_a_size_is_pixels_times_the_ratio_and_the_picture_is_fitted_to_the_text(self):
        result = self.run_on("A ![[a b.png|300]] z")
        self.assertEqual(result.text, 'A ![](img/a%20b.png){width=225pt data-pdfmd-fit="text-width"} z')
        self.assertEqual(result.count, 1)

    def test_width_and_height_alt_text_and_the_ratio_and_fit_settings(self):
        result = self.run_on("![[a.png|The alt|200x100]]", px_to_pt=0.5, fit="none")
        self.assertEqual(result.text, "![The alt](img/a.png){width=100pt height=50pt}")

    def test_no_size_no_attributes_and_other_text_is_the_alt(self):
        self.assertEqual(self.run_on("![[a.PNG]]").text, "![](img/a.PNG)")
        self.assertEqual(self.run_on("![[a.png|just words]]").text, "![just words](img/a.png)")
        self.assertEqual(self.run_on("![[a.png#section|10]]").text.split("{")[0], "![](img/a.png)")

    def test_a_missing_picture_stays_visible_and_is_reported(self):
        result = embed_images("x\n![[gone.png]]\n", lambda name: None)
        self.assertEqual(result.text, "x\n**[missing image: gone.png]**\n")
        self.assertEqual(result.missing, [(2, "gone.png")])

    def test_code_math_front_matter_comments_and_other_files_are_left_alone(self):
        text = "---\nt: '![[a.png]]'\n---\n\n`![[a.png]]` $![[a.png]]$ <!-- ![[a.png]] -->\n\n```\n![[a.png]]\n```\n\n![[note]] ![[doc.pdf]]\n"
        result = self.run_on(text)
        self.assertEqual(result.text, text)
        self.assertEqual(result.count, 0)


class Lookup(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-embed-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        pdfmd._VAULT_ROOTS.clear()
        pdfmd._EMBED_INDEX.clear()
        pdfmd._FLAVOUR_TOLD.clear()
        self.vault = self.directory / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)

    def put(self, relative, base=None):
        path = (base or self.vault) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        return path

    def note(self, relative="notes/n.md", base=None):
        path = (base or self.vault) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
        return path

    def test_beside_the_document_then_from_the_vault_top_then_by_name_anywhere(self):
        note = self.note()
        beside = self.put("notes/a.png")
        self.assertEqual(pdfmd.find_embedded_image("a.png", note), beside.resolve())
        top = self.put("top.png")
        self.assertEqual(pdfmd.find_embedded_image("top.png", note), top.resolve())
        deep = self.put("x/y/z/deep.png")
        self.assertEqual(pdfmd.find_embedded_image("deep.png", note), deep.resolve())
        self.assertEqual(pdfmd.find_embedded_image("y/z/deep.png", note), deep.resolve())      # a path's tail is enough
        self.assertIsNone(pdfmd.find_embedded_image("nowhere.png", note))

    def test_the_attachment_folder_of_the_vault(self):
        (self.vault / ".obsidian" / "app.json").write_text('{"attachmentFolderPath": "files"}', encoding="utf-8")
        note = self.note()
        shot = self.put("files/shot.png")
        self.put("other/shot.png")
        self.assertEqual(pdfmd.find_embedded_image("shot.png", note), shot.resolve())

    def test_the_nearest_picture_wins_and_a_note_says_which(self):
        note = self.note("a/b/n.md")
        near = self.put("a/pics/p.png")
        self.put("z/pics/p.png")
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            self.assertEqual(pdfmd.find_embedded_image("p.png", note), near.resolve())
        self.assertIn("2 pictures are named p.png", said.getvalue())

    def test_outside_a_vault_it_searches_below_the_documents_folder_only(self):
        base = self.directory / "plain"
        note = self.note("n.md", base)
        below = self.put("sub/deeper/q.png", base)
        self.put("elsewhere/r.png", self.directory)
        self.assertEqual(pdfmd.find_embedded_image("q.png", note), below.resolve())
        self.assertIsNone(pdfmd.find_embedded_image("r.png", note))
        self.assertIsNone(pdfmd.find_embedded_image("q.png", note, "none"))
        self.assertEqual(pdfmd.find_embedded_image("sub/deeper/q.png", note, "none"), below.resolve())

    def test_hidden_and_tool_folders_are_not_searched(self):
        note = self.note()
        self.put(".trash/old.png")
        self.put("node_modules/pkg/n.png")
        self.assertIsNone(pdfmd.find_embedded_image("old.png", note))
        self.assertIsNone(pdfmd.find_embedded_image("n.png", note))


@needs_pandoc(3, 1, 3)
class Build(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-embed-build-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "vault" / ".obsidian").mkdir(parents=True)
        (self.directory / "vault" / "img").mkdir()
        (self.directory / "vault" / "img" / "Pasted image 1.png").write_bytes(PNG)
        (self.directory / "vault" / "notes").mkdir()
        (self.directory / "plain").mkdir()
        (self.directory / "plain" / "pic.png").write_bytes(PNG)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": str(self.directory / "config"),
                    "APPDATA": str(self.directory / "config")}

    def build(self, folder, text, target="html", *arguments):
        place = self.directory / folder
        (place / "n.md").write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "n.md", "-t", target, "--no-stamp", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=place, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        suffix = {"latex": "tex"}.get(target, target)
        return " ".join((place / f"n.{suffix}").read_text(encoding="utf-8").split()), done.stdout + done.stderr

    def test_in_a_vault_the_picture_is_found_by_name_and_sized_in_points(self):
        html, said = self.build("vault/notes", "# N\n\nA ![[Pasted image 1.png|300]] B\n")
        self.assertIn('src="../img/Pasted%20image%201.png"', html)
        self.assertRegex(html, r"width:(225pt|3\.125in)\b")          # 300 px; Pandoc 3.1.3 writes the same length in inches
        self.assertIn("max-width: 100%", html)
        self.assertNotIn("WARN", said)

    def test_outside_a_vault_it_is_pdfmds_own_embed_and_flavour_pandoc_leaves_it_text(self):
        html, _ = self.build("plain", "# N\n\n![[pic.png|Caption|100]]\n")
        self.assertIn('src="pic.png"', html)
        self.assertIn("<figcaption", html)
        html, _ = self.build("plain", "---\npdfmd-options:\n  flavour: pandoc\n---\n\n![[pic.png|100]]\n")
        self.assertIn("[[pic.png|100]]", html)          # as text; Pandoc 3.1.3's Markdown reader drops the `!` before a bracket that is no image
        self.assertNotIn("<img", html)

    def test_a_missing_picture_is_a_placeholder_and_a_warning(self):
        html, said = self.build("plain", "# N\n\n![[nope.png]]\n")
        self.assertIn("[missing image: nope.png]", html)
        self.assertIn("no picture of that name was found", said)

    def test_the_settings_change_the_size_and_the_cap(self):
        html, _ = self.build("plain", "---\npdfmd-options:\n  embed-px-to-pt: 1\n  embed-fit: none\n---\n\n![[pic.png|120]]\n")
        self.assertRegex(html, r"width:(120pt|1\.66667in)\b")        # the same length, as Pandoc 3.1.3 spells it
        self.assertNotIn("max-width", html)

    def test_a_latex_build_keeps_a_wide_picture_within_the_text(self):
        tex, _ = self.build("plain", "# N\n\n![[pic.png|900]]\n", "latex")
        self.assertIn("width=\\ifdim 675pt>\\linewidth \\linewidth\\else 675pt\\fi", tex)
        self.assertIn("{pic.png}", tex)


if __name__ == "__main__":
    unittest.main()

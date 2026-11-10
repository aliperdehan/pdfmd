"""A kit's front matter survives pdfmd's header files (v3.32.30, `headers_as_metadata`). Pandoc puts --include-in-header
files and `header-includes` in one template variable and the files win, so a LaTeX build with any header file of pdfmd's
lost what a Lua filter had put into `header-includes` (apa7's \\authorsnames: \\maketitle stopped in a partial build).
The files now go in as `-M pdfmd-header-file-N` and two filters merge them with whatever the other filters added."""

from __future__ import annotations

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

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

OWN = ROOT / "lib" / "pdfmd_lua"
FILTER = 'function Meta(m)\n  local h = m["header-includes"] or pandoc.MetaList({})\n' \
         '  if pandoc.utils.type(h) ~= "List" then h = pandoc.MetaList({h}) end\n' \
         '  h[#h + 1] = pandoc.MetaBlocks({pandoc.RawBlock("latex", "\\\\usepackage{filteradded}")})\n' \
         '  m["header-includes"] = h\n  return m\nend\n'


class Command(unittest.TestCase):
    def test_header_files_become_metadata(self):
        cmd = ["pandoc", "a.md", "--pdf-engine=lualatex", "--include-in-header", "one.tex", "--lua-filter", "/kit/kit.lua",
               "--include-in-header=two.tex", "-o", "a.pdf"]
        out = pdfmd.headers_as_metadata(cmd)
        self.assertNotIn("--include-in-header", out)
        self.assertFalse([item for item in out if item.startswith("--include-in-header")])
        self.assertIn("pdfmd-header-file-1=one.tex", out)
        self.assertIn("pdfmd-header-file-2=two.tex", out)
        self.assertEqual(out[out.index("--lua-filter") + 1], str(OWN / "header_snap.lua"))     # before the kit's filter
        self.assertEqual(out[-2:], ["--lua-filter", str(OWN / "header_merge.lua")])             # after everything
        self.assertEqual(cmd[3], "--include-in-header")                                         # the caller's list is untouched

    def test_left_alone(self):
        header = ["--include-in-header", "one.tex"]
        for cmd in (
            ["pandoc", "a.md", "--pdf-engine=lualatex", "--lua-filter", "/kit/kit.lua"],                        # no header file
            ["pandoc", "a.md", "--pdf-engine=lualatex", *header],                                              # no filter of anybody else's
            ["pandoc", "a.md", "--pdf-engine=lualatex", *header, "--lua-filter", str(OWN / "calc.lua")],      # only pdfmd's own
            ["pandoc", "a.md", "--pdf-engine=typst", *header, "--lua-filter", "/kit/kit.lua"],                 # not LaTeX
            ["pandoc", "a.md", "--pdf-engine=context", *header, "--lua-filter", "/kit/kit.lua"],
            ["pandoc", "a.md", "-t", "html", *header, "--lua-filter", "/kit/kit.lua"],
        ):
            self.assertEqual(pdfmd.headers_as_metadata(cmd), cmd, cmd)

    def test_latex_targets(self):
        for target in (["-t", "latex"], ["--to=beamer"], ["--pdf-engine=xelatex"]):
            out = pdfmd.headers_as_metadata(["pandoc", "a.md", *target, "-H", "x.tex", "--lua-filter", "/kit/kit.lua"])
            self.assertIn("pdfmd-header-file-1=x.tex", out, target)


@unittest.skipUnless(shutil.which("pandoc"), "Pandoc is not installed")
class Pandoc(unittest.TestCase):
    def build(self, transform: bool) -> str:
        with tempfile.TemporaryDirectory(prefix="pdfmd-header-filters-") as folder:
            root = Path(folder)
            (root / "kit.lua").write_text(FILTER, encoding="utf-8")
            (root / "one.tex").write_text("\\usepackage{fromfile}\n", encoding="utf-8")
            (root / "packages-x.tex").write_text("\\usepackage{lastfile}\n", encoding="utf-8")
            (root / "a.md").write_text("---\nheader-includes: |\n  ```{=latex}\n  \\usepackage{fromyaml}\n  ```\n---\n\nText.\n",
                                       encoding="utf-8")
            cmd = ["pandoc", "a.md", "-s", "-t", "latex", "--lua-filter", "kit.lua",
                   "--include-in-header", "one.tex", "--include-in-header", "packages-x.tex", "-o", "a.tex"]
            if transform:
                cmd = pdfmd.headers_as_metadata(cmd)
            done = subprocess.run(cmd, cwd=root, capture_output=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            return (root / "a.tex").read_text(encoding="utf-8")

    def test_the_filters_header_reaches_the_preamble(self):
        self.assertNotIn("filteradded", self.build(transform=False))          # Pandoc as it is: the files win
        tex = self.build(transform=True)
        self.assertIn("\\usepackage{filteradded}", tex)
        self.assertIn("\\usepackage{fromfile}", tex)
        self.assertLess(tex.index("filteradded"), tex.index("lastfile"))        # in front of the packages header
        self.assertLess(tex.index("fromfile"), tex.index("lastfile"))
        self.assertEqual(tex.count("fromyaml"), 0)                              # pdfmd's header files carry that, not Pandoc

    def test_nothing_is_written_twice(self):
        tex = self.build(transform=True)
        for name in ("filteradded", "fromfile", "lastfile"):
            self.assertEqual(tex.count("\\usepackage{%s}" % name), 1, name)


if __name__ == "__main__":
    unittest.main()

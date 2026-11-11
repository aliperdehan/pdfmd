"""Direct TeX builds use the fresh Biber control file in their output directory."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(all(shutil.which(x) for x in ("pdflatex", "biber", "pdftotext")), "needs TeX, Biber and pdftotext")
class BiberDirect(unittest.TestCase):
    def test_stale_source_control_file_is_not_used(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-biber-") as directory:
            root = Path(directory)
            (root / "paper.tex").write_text(
                "\\documentclass{article}\n\\usepackage[backend=biber]{biblatex}\n"
                "\\addbibresource{references.bib}\n\\begin{document}\n"
                "\\cite{fresh}\\printbibliography\n\\end{document}\n", encoding="utf-8")
            (root / "references.bib").write_text(
                "@book{fresh, author={Example, Alice}, title={Fresh Bibliography}, year={2020}}\n", encoding="utf-8")
            (root / "paper.bcf").write_text("stale control file", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                   "XDG_CONFIG_HOME": str(root / "config"), "XDG_CACHE_HOME": str(root / "cache"),
                   "XDG_DATA_HOME": str(root / "data")}
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "paper.tex", "-e", "pdflatex",
                                     "--engine-fallback", "missing", "--no-stamp"], cwd=root, env=env,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = subprocess.run(["pdftotext", str(root / "paper.pdf"), "-"], capture_output=True, text=True, check=True).stdout
            self.assertIn("Fresh Bibliography", text)
            self.assertEqual((root / "paper.bcf").read_text(encoding="utf-8"), "stale control file")

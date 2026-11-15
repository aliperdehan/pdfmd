"""v3.33.218 on: TeX self-repair (`tex-repair: auto|off`, lib/pdfmd_tex/repair.py). A broken TeX installation (the cases an AI
sandbox shows again and again: no luaotfload, no lmodern.sty, no soul.sty, an unwritable or a corrupt font cache, Biber's stale
unpack cache) is mended for the run only: an engine skipped, a stub on TEXINPUTS, a scratch cache folder, and one NOTE.

The engines here are fakes on PATH that print the real log text of each failure (tests/fixtures/tex-repair/*.txt, taken from
a collection of real logs, Ubuntu 24.04 with TeX Live 2023) and exit as the real one did; a fake `kpsewhich` hides the files
the case is about and asks the real one for everything else. The builds go through pdfmd itself (scripts/pdfmd)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "tex-repair"

PANDOC = shutil.which("pandoc")
KPSEWHICH = shutil.which("kpsewhich")
REAL = {name: shutil.which(name) for name in ("lualatex", "xelatex", "pdflatex")}
GOOD = "---\ntitle: R\n---\n\nGood text.\n"
STRUCK = "---\ntitle: R\n---\n\nSome ~~struck~~ text.\n"

# One script for every fake engine, told what to do by the JSON file FAKE_TEX_SPEC names (inherited through pdfmd and Pandoc):
#   spec[name] = {"fixture": the log text it prints and writes, "ok_if": when it succeeds (a dict, see below),
#                 "delegate": the real engine to run on success (else a blank PDF is written)}
#   ok_if: {"env_set": NAME} | {"env_in": [NAME, text]} | {"env_not": [NAME, value]} | absent: never
# Every run is appended to spec["log"] as one line: the engine name and the environment it saw (TEXINPUTS, TEXMFVAR, TEXMFCACHE).
FAKE_ENGINE = r'''#!{python}
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
spec = json.loads(Path(os.environ["FAKE_TEX_SPEC"]).read_text(encoding="utf-8"))
mine = spec[name]
with open(spec["log"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"engine": name, "args": sys.argv[1:], **{{key: os.environ.get(key, "") for key in
                 ("TEXINPUTS", "TEXMFVAR", "TEXMFCACHE")}}}}) + "\n")
if "--version" in sys.argv[1:]:
    print("This is a fake " + name + ", Version 1")
    sys.exit(0)
args = sys.argv[1:]
output_directory = Path(".")
for index, word in enumerate(args):
    if word.startswith("-output-directory="):
        output_directory = Path(word.split("=", 1)[1])
    elif word == "-output-directory":
        output_directory = Path(args[index + 1])
job = Path(args[-1]).stem
ok_if = mine.get("ok_if") or {{}}
env = os.environ
if "env_set" in ok_if:
    ok = bool(env.get(ok_if["env_set"]))
elif "env_in" in ok_if:
    ok = ok_if["env_in"][1] in env.get(ok_if["env_in"][0], "")
elif "env_not" in ok_if:
    ok = env.get(ok_if["env_not"][0], "") != ok_if["env_not"][1]
else:
    ok = False
if not ok:
    text = Path(mine["fixture"]).read_text(encoding="utf-8")
    sys.stdout.write(text)
    (output_directory / (job + ".log")).write_text(text, encoding="utf-8")
    sys.exit(1)
if mine.get("delegate"):
    os.execv(mine["delegate"], [mine["delegate"], *args])
from pypdf import PdfWriter
writer = PdfWriter()
writer.add_blank_page(200, 200)
with open(output_directory / (job + ".pdf"), "wb") as handle:
    writer.write(handle)
sys.exit(0)
'''

# kpsewhich that does not know the files of FAKE_KPSE_HIDE (comma separated) and answers everything else like the real one
FAKE_KPSEWHICH = r'''#!{python}
import os, sys
hidden = set(filter(None, os.environ.get("FAKE_KPSE_HIDE", "").split(",")))
args = sys.argv[1:]
kept = [word for word in args if word not in hidden]
if len(kept) == len(args):
    os.execv({real!r}, [{real!r}, *args])
if not [word for word in kept if not word.startswith("-")]:
    sys.exit(1)
os.execv({real!r}, [{real!r}, *kept])
'''


def fixture(name: str) -> str:
    return str(FIXTURES / name)


class FakeTeX(unittest.TestCase):
    """A folder with fake engines and a fake kpsewhich on PATH, and pdfmd run with them."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pdfmd-texrepair-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.bin = self.folder / "bin"
        self.bin.mkdir()
        self.work = self.folder / "work"
        self.work.mkdir()
        self.runs = self.folder / "runs.jsonl"
        self.spec: dict = {"log": str(self.runs)}
        self.hide: list[str] = []
        self.environment: dict[str, str] = {}

    def engine(self, name: str, fixture_name: str, **how) -> None:
        """A fake ``name`` that prints the fixture's log and fails, unless ``how`` (ok_if, delegate) lets it succeed."""
        self.spec[name] = {"fixture": fixture(fixture_name), **how}
        path = self.bin / name
        path.write_text(FAKE_ENGINE.format(python=sys.executable), encoding="utf-8")
        path.chmod(0o755)

    def kpsewhich(self, *hidden: str) -> None:
        path = self.bin / "kpsewhich"
        path.write_text(FAKE_KPSEWHICH.format(python=sys.executable, real=KPSEWHICH), encoding="utf-8")
        path.chmod(0o755)
        self.hide = list(hidden)

    def write(self, name: str, text: str) -> Path:
        path = self.work / name
        path.write_text(text, encoding="utf-8")
        return path

    def pdfmd(self, *args: str, env: dict | None = None) -> tuple[int, str]:
        spec_file = self.folder / "spec.json"
        spec_file.write_text(json.dumps(self.spec), encoding="utf-8")
        environment = {**os.environ, "PDFMD_NO_PROMPT": "1", "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
                       "FAKE_TEX_SPEC": str(spec_file), "FAKE_KPSE_HIDE": ",".join(self.hide), **self.environment, **(env or {})}
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args, "--no-backup", "--no-stamp"],
                              capture_output=True, text=True, cwd=self.work, env=environment, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout + done.stderr

    def started(self, name: str | None = None) -> list[dict]:
        """What the fake engines were run with, in order (only ``name``'s when given); `--version` asks are left out."""
        if not self.runs.is_file():
            return []
        rows = [json.loads(line) for line in self.runs.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [row for row in rows if "--version" not in row["args"] and (name is None or row["engine"] == name)]


def needs_tex(*names: str):
    return unittest.skipUnless(PANDOC and KPSEWHICH and os.name != "nt" and all(REAL[name] for name in names),
                               "needs Pandoc, kpsewhich, the TeX engines, and a shell that runs scripts")


@needs_tex("xelatex")
class LuaotfloadMissing(FakeTeX):
    """Remedy 1: LuaTeX's font loader is not installed, so lualatex is skipped up front (no wasted run)."""

    def setUp(self):
        super().setUp()
        self.engine("lualatex", "luaotfload-missing.txt")
        self.engine("xelatex", "luaotfload-missing.txt", ok_if={"env_set": "PATH"}, delegate=REAL["xelatex"])
        self.kpsewhich("luaotfload-main.lua")
        self.write("d.md", GOOD)

    def test_lualatex_is_skipped_and_one_note_says_so(self):
        code, said = self.pdfmd("d.md", "-e", "lualatex,xelatex")
        self.assertEqual(code, 0, said)
        self.assertEqual(self.started("lualatex"), [], said)                       # never started
        self.assertEqual(said.count(": tex-repair: "), 1, said)                   # one NOTE
        self.assertRegex(said, r"NOTE .*tex-repair: luaotfload .*is not installed, so lualatex is skipped")
        self.assertNotIn("lualatex failed", said)
        self.assertIn("(xelatex)", said)
        self.assertTrue((self.work / "d.pdf").is_file())

    def test_off_keeps_the_wasted_run(self):
        self.write("d.md", "---\ntitle: R\npdfmd-options: {tex-repair: off}\n---\n\nGood text.\n")
        code, said = self.pdfmd("d.md", "-e", "lualatex,xelatex")
        self.assertEqual(code, 0, said)
        self.assertEqual(len(self.started("lualatex")), 1, said)                   # as before: it ran and failed
        self.assertIn("lualatex failed", said)
        self.assertNotIn("tex-repair", said)

    def test_strict_counts_the_repair_as_a_warning(self):
        code, said = self.pdfmd("d.md", "-e", "lualatex,xelatex", "--strict")
        self.assertEqual(code, 1, said)
        self.assertIn("--strict: the build printed 1 warning", said)
        self.assertIn("tex-repair", said)
        self.assertTrue((self.work / "d.pdf").is_file())                             # the output is kept

    def test_the_only_engine_is_never_skipped(self):
        code, said = self.pdfmd("d.md", "-e", "lualatex")
        self.assertEqual(code, 1, said)
        self.assertEqual(len(self.started("lualatex")), 1, said)
        self.assertNotIn("tex-repair", said)

    def test_a_healthy_installation_is_left_alone(self):
        self.kpsewhich()                                                             # nothing hidden: luaotfload is there
        self.spec["lualatex"]["ok_if"] = {"env_set": "PATH"}                         # the fake works
        code, said = self.pdfmd("d.md", "-e", "lualatex,xelatex")
        self.assertEqual(code, 0, said)
        self.assertEqual(len(self.started("lualatex")), 1, said)
        self.assertNotIn("tex-repair", said)


STUBS = "pdfmd-tex-stubs"        # the name of the temporary folder the stand-in files are made in


@needs_tex("xelatex")
class LmodernMissing(FakeTeX):
    """Remedy 2: lmodern.sty is not installed. Pandoc's LaTeX template loads it for every engine, so xelatex and lualatex get
    pdfmd's empty stand-in (their fonts come from fontspec) and pdflatex, which needs the real fonts, is skipped."""

    def setUp(self):
        super().setUp()
        works = {"ok_if": {"env_in": ["TEXINPUTS", STUBS]}}
        self.engine("pdflatex", "lmodern-missing.txt", **works)
        self.engine("xelatex", "lmodern-missing.txt", delegate=REAL["xelatex"], **works)
        self.engine("lualatex", "lmodern-missing.txt", **works)
        self.kpsewhich("lmodern.sty")
        self.write("d.md", GOOD)

    def test_xelatex_gets_a_stand_in_and_pdflatex_is_skipped(self):
        code, said = self.pdfmd("d.md", "-e", "pdflatex,xelatex")
        self.assertEqual(code, 0, said)
        self.assertEqual(self.started("pdflatex"), [], said)
        self.assertTrue(self.started("xelatex"), said)                              # (Pandoc runs it more than once)
        for run in self.started("xelatex"):
            self.assertIn(STUBS, run["TEXINPUTS"])
        self.assertEqual(said.count(": tex-repair: "), 1, said)
        self.assertRegex(said, r"NOTE .*tex-repair: lmodern\.sty is not installed")
        self.assertIn("pdflatex is skipped", said)
        self.assertNotIn("failed", said)

    def test_lualatex_gets_the_stand_in_too(self):
        code, said = self.pdfmd("d.md", "-e", "lualatex")                          # the fake succeeds with the stand-in
        self.assertEqual(code, 0, said)
        self.assertIn(STUBS, self.started("lualatex")[0]["TEXINPUTS"])
        self.assertIn("empty stand-in", said)

    def test_off_keeps_the_failure(self):
        self.write("d.md", "---\ntitle: R\npdfmd-options: {tex-repair: off}\n---\n\nGood text.\n")
        code, said = self.pdfmd("d.md", "-e", "pdflatex,xelatex")
        self.assertEqual(code, 1, said)
        self.assertEqual(len(self.started("pdflatex")), 1, said)
        self.assertNotIn(STUBS, self.started("xelatex")[0]["TEXINPUTS"])
        self.assertIn("the LaTeX package lmodern.sty is missing", said)
        self.assertNotIn("tex-repair", said)

    def test_pdflatex_alone_is_not_skipped_and_gets_no_stand_in(self):
        code, said = self.pdfmd("d.md", "-e", "pdflatex")
        self.assertEqual(code, 1, said)
        self.assertEqual(len(self.started("pdflatex")), 1, said)
        self.assertNotIn(STUBS, self.started("pdflatex")[0]["TEXINPUTS"])

    def test_strict_counts_it(self):
        code, said = self.pdfmd("d.md", "-e", "pdflatex,xelatex", "--strict")
        self.assertEqual(code, 1, said)
        self.assertIn("--strict: the build printed 1 warning", said)

    def test_the_stand_in_is_a_package_xelatex_loads(self):
        # the files themselves: a document that loads lmodern, compiled with the stand-in FIRST on the path (a real one is
        # installed here, so the build above never reads the stand-in)
        import pdfmd
        repair = pdfmd.load_package("pdfmd_tex.repair")
        folder = self.folder / "stubs"
        folder.mkdir()
        repair.write_stub(folder, "lmodern.sty")
        (self.work / "s.tex").write_text("\\documentclass{article}\\usepackage{lmodern}\\begin{document}Hi.\\end{document}\n", encoding="utf-8")
        done = subprocess.run([REAL["xelatex"], "-interaction=nonstopmode", "-halt-on-error", "s.tex"], cwd=self.work, capture_output=True,
                              text=True, env={**os.environ, "TEXINPUTS": f"{folder}{os.pathsep}"})
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("pdfmd stub", (self.work / "s.log").read_text(encoding="utf-8", errors="replace"))


@needs_tex("xelatex", "lualatex")
class SoulMissing(FakeTeX):
    """Remedy 3: soul.sty is not installed and the text is struck out. xelatex and pdflatex need soul for that (lualatex has
    lua-ul), so lualatex goes first when the chain is pdfmd's own, and xelatex and pdflatex get a stand-in soul.sty that
    draws the line with ulem's \\sout (plain text and a WARN when ulem is missing too)."""

    def setUp(self):
        super().setUp()
        works = {"ok_if": {"env_in": ["TEXINPUTS", STUBS]}}
        self.engine("xelatex", "soul-missing.txt", delegate=REAL["xelatex"], **works)
        self.engine("pdflatex", "soul-missing.txt", **works)
        self.engine("lualatex", "soul-missing.txt", ok_if={"env_set": "PATH"}, delegate=REAL["lualatex"])
        self.kpsewhich("soul.sty")
        self.write("d.md", STRUCK)

    def test_xelatex_gets_a_stand_in_soul_that_builds(self):
        code, said = self.pdfmd("d.md", "-e", "xelatex")                           # pinned: never reordered
        self.assertEqual(code, 0, said)
        self.assertIn(STUBS, self.started("xelatex")[0]["TEXINPUTS"])
        self.assertEqual(said.count(": tex-repair: "), 1, said)
        self.assertRegex(said, r"NOTE .*tex-repair: soul\.sty is not installed")
        self.assertIn("\\sout", said)
        self.assertEqual(self.started("lualatex"), [])

    def test_a_chain_of_pdfmds_own_starts_with_lualatex(self):
        import pdfmd
        repair = pdfmd.load_package("pdfmd_tex.repair")
        document = self.write("e.md", STRUCK)
        with unittest.mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "FAKE_KPSE_HIDE": "soul.sty"}):
            repair.PROBED.clear()
            repair.NOTED.clear()
            with contextlib.redirect_stderr(io.StringIO()):
                chain = repair.plan(document, [], ["xelatex", "pdflatex", "lualatex"], reorder=True)
        self.assertEqual(chain, ["lualatex", "xelatex", "pdflatex"])

    def test_a_pinned_or_mirrored_chain_keeps_its_order(self):
        import pdfmd
        repair = pdfmd.load_package("pdfmd_tex.repair")
        document = self.write("e.md", STRUCK)
        with unittest.mock.patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "FAKE_KPSE_HIDE": "soul.sty"}):
            repair.PROBED.clear()
            repair.NOTED.clear()
            with contextlib.redirect_stderr(io.StringIO()):
                chain = repair.plan(document, [], ["xelatex", "pdflatex", "lualatex"], reorder=False)
        self.assertEqual(chain, ["xelatex", "pdflatex", "lualatex"])

    def test_a_document_without_struck_text_is_left_alone(self):
        self.write("d.md", GOOD)
        self.spec["xelatex"]["ok_if"] = {"env_set": "PATH"}
        code, said = self.pdfmd("d.md", "-e", "xelatex")
        self.assertEqual(code, 0, said)
        self.assertNotIn(STUBS, self.started("xelatex")[0]["TEXINPUTS"])
        self.assertNotIn("tex-repair", said)

    def test_without_ulem_the_text_is_plain_and_a_warning_says_so(self):
        self.kpsewhich("soul.sty", "ulem.sty")
        code, said = self.pdfmd("d.md", "-e", "xelatex")
        self.assertEqual(code, 0, said)
        self.assertRegex(said, r"WARN .*soul\.sty and ulem\.sty are not installed")
        self.assertIn("struck-out text is printed without its line", said)

    def test_off_keeps_the_failure(self):
        self.write("d.md", "---\ntitle: R\npdfmd-options: {tex-repair: off}\n---\n\nSome ~~struck~~ text.\n")
        code, said = self.pdfmd("d.md", "-e", "xelatex")
        self.assertEqual(code, 1, said)
        self.assertNotIn("tex-repair", said)
        self.assertIn("the LaTeX package soul.sty is missing", said)

    def test_the_stand_in_is_a_package_xelatex_loads(self):
        import pdfmd
        repair = pdfmd.load_package("pdfmd_tex.repair")
        folder = self.folder / "stubs"
        folder.mkdir()
        repair.write_stub(folder, "soul.sty", ulem=True)
        (self.work / "s.tex").write_text("\\documentclass{article}\\usepackage{soul}\\begin{document}Some \\st{struck} and \\emph{kept}.\\end{document}\n", encoding="utf-8")
        done = subprocess.run([REAL["xelatex"], "-interaction=nonstopmode", "-halt-on-error", "s.tex"], cwd=self.work, capture_output=True,
                              text=True, env={**os.environ, "TEXINPUTS": f"{folder}{os.pathsep}"})
        self.assertEqual(done.returncode, 0, done.stdout)
        log = (self.work / "s.log").read_text(encoding="utf-8", errors="replace")
        self.assertIn("pdfmd stub", log)
        self.assertIn("ulem.sty", log)                                             # the line is drawn by ulem
        repair.write_stub(folder, "soul.sty", ulem=False)                          # the plain one loads as well
        done = subprocess.run([REAL["xelatex"], "-interaction=nonstopmode", "-halt-on-error", "s.tex"], cwd=self.work, capture_output=True,
                              text=True, env={**os.environ, "TEXINPUTS": f"{folder}{os.pathsep}"})
        self.assertEqual(done.returncode, 0, done.stdout)


if __name__ == "__main__":
    unittest.main()

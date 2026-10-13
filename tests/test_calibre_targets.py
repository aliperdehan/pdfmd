"""v3.29.0: Calibre as a writer. `-o book.azw3` / `--to mobi` make the ebook through an EPUB 3 and `ebook-convert`; epub, docx,
rtf, txt and fb2 only with `-e calibre`; before v3.29.0 `-o book.azw3` wrote a PDF under that name."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
REAL_CALIBRE = pdfmd.resolve_calibre()


class Decision(unittest.TestCase):
    def test_a_target_only_calibre_writes_is_always_calibres(self):
        for name in pdfmd.CALIBRE_ONLY_FORMATS:
            self.assertEqual(pdfmd.calibre_goal(None, name), name)
            self.assertEqual(pdfmd.calibre_goal("typst", name), name)        # -e typst has nothing to say about an ebook
        self.assertEqual(len(pdfmd.CALIBRE_ONLY_FORMATS), 12)

    def test_a_target_pandoc_writes_too_is_calibres_only_when_e_names_calibre_first(self):
        for name in pdfmd.CALIBRE_SHARED_FORMATS:
            self.assertIsNone(pdfmd.calibre_goal(None, name), name)
            self.assertIsNone(pdfmd.calibre_goal("typst,calibre", name), name)      # Calibre is not first
            self.assertEqual(pdfmd.calibre_goal("calibre", name), name)
            self.assertEqual(pdfmd.calibre_goal("ebook-convert,typst", name), name)
        self.assertEqual(pdfmd.calibre_goal("calibre", "plain"), "txt")
        self.assertEqual(pdfmd.calibre_goal("calibre", "epub3"), "epub")

    def test_pdf_and_everything_else_are_not_this(self):
        self.assertIsNone(pdfmd.calibre_goal("calibre", "pdf"))                  # the PDF route of v3.28.0
        self.assertIsNone(pdfmd.calibre_goal(None, "html"))
        self.assertIsNone(pdfmd.calibre_goal("", "docx"))

    def test_e_calibre_with_a_target_it_cannot_write_says_what_it_can(self):
        with self.assertRaises(SystemExit) as raised:
            pdfmd.calibre_goal("calibre", "latex")
        text = str(raised.exception)
        for word in ("PDF", "epub", "docx", "azw3", "mobi", "not latex"):
            self.assertIn(word, text)

    def test_the_suffixes_name_the_targets(self):
        for name in pdfmd.CALIBRE_ONLY_FORMATS:
            self.assertEqual(pdfmd.format_from_output(Path(f"book.{name}")), name)
        self.assertEqual(pdfmd.format_from_output(Path("BOOK.MOBI")), "mobi")
        self.assertEqual(pdfmd.format_from_output(Path("book.docx")), "docx")           # what it was
        self.assertIsNone(pdfmd.format_from_output(Path("book.unknown")))


class SofficeDecision(unittest.TestCase):
    """v3.29.1: LibreOffice as a writer: `-o letter.doc`; rtf, odt, txt and epub only with `-e soffice` first."""

    def test_doc_is_always_libreoffices(self):
        self.assertEqual(pdfmd.soffice_goal(None, "doc"), "doc")
        self.assertEqual(pdfmd.soffice_goal("typst", "doc"), "doc")
        self.assertEqual(pdfmd.format_from_output(Path("letter.DOC")), "doc")

    def test_the_shared_formats_need_e_soffice_first(self):
        for name in pdfmd.SOFFICE_SHARED_FORMATS:
            self.assertIsNone(pdfmd.soffice_goal(None, name), name)
            self.assertIsNone(pdfmd.soffice_goal("calibre,soffice", name), name)
            for asked in ("soffice", "libreoffice", "office", "soffice,typst"):
                self.assertEqual(pdfmd.soffice_goal(asked, name), name, asked)
        self.assertEqual(pdfmd.soffice_goal("soffice", "plain"), "txt")

    def test_pdf_and_other_targets_are_not_this_and_the_error_lists_what_it_writes(self):
        self.assertIsNone(pdfmd.soffice_goal("soffice", "pdf"))                  # the PDF engine of old
        self.assertIsNone(pdfmd.soffice_goal(None, "docx"))
        with self.assertRaises(SystemExit) as raised:
            pdfmd.soffice_goal("soffice", "latex")
        for word in ("PDF", "rtf", "odt", "epub", "doc", "not latex"):
            self.assertIn(word, str(raised.exception))

    def test_a_job_checks_for_libreoffice_and_one_document_at_a_time(self):
        args = SimpleNamespace(batch=True, report=False, presentation=False, out=None, to=None, engine=None, open=True)
        with self.assertRaises(SystemExit) as raised:
            pdfmd.start_soffice_job(args, "doc", "doc")
        self.assertIn("not with -b", str(raised.exception))
        args.batch = False
        with mock.patch.object(pdfmd, "resolve_soffice", return_value=None), self.assertRaises(SystemExit) as raised:
            pdfmd.start_soffice_job(args, "doc", "doc")
        self.assertIn("doc is written by LibreOffice", str(raised.exception))
        with mock.patch.object(pdfmd, "resolve_soffice", return_value="/x"):
            job = pdfmd.start_soffice_job(args, "doc", "doc")
        self.addCleanup(shutil.rmtree, job["scratch"], ignore_errors=True)
        self.assertEqual((args.to, args.engine, args.open), ("docx", None, False))
        self.assertEqual(args.out, job["scratch"] / "document.docx")


class Job(unittest.TestCase):
    def args(self, **values):
        base = dict(batch=False, report=False, presentation=False, out=None, to=None, engine=None, open=True)
        return SimpleNamespace(**{**base, **values})

    def test_one_document_at_a_time(self):
        for key, flag in (("batch", "-b"), ("report", "-r"), ("presentation", "-p")):
            with self.assertRaises(SystemExit) as raised:
                pdfmd.start_calibre_job(self.args(**{key: True}), "azw3", "azw3")
            self.assertIn(f"not with {flag}", str(raised.exception))

    def test_no_calibre_names_the_target_and_where_to_get_it(self):
        with mock.patch.object(pdfmd, "resolve_calibre", return_value=None), self.assertRaises(SystemExit) as raised:
            pdfmd.start_calibre_job(self.args(), "mobi", "mobi")
        text = str(raised.exception)
        self.assertIn("mobi is written by Calibre", text)
        self.assertIn("brew install --cask calibre", text)

    def test_the_arguments_point_at_a_scratch_epub_and_the_job_remembers_what_was_asked(self):
        arguments = self.args(out=Path("book.azw3"), engine="typst")
        with mock.patch.object(pdfmd, "resolve_calibre", return_value="/opt/calibre/ebook-convert"):
            job = pdfmd.start_calibre_job(arguments, "azw3", "azw3")
        self.addCleanup(shutil.rmtree, job["scratch"], ignore_errors=True)
        self.assertEqual(job["final"], Path("book.azw3"))
        self.assertTrue(job["open"])
        self.assertEqual(arguments.out, job["scratch"] / "document.epub")
        self.assertEqual((arguments.to, arguments.engine, arguments.open), ("epub", None, False))

    def test_a_shared_format_says_pandocs_route_has_more(self):
        said = []
        with mock.patch.object(pdfmd, "resolve_calibre", return_value="/x"), \
                mock.patch("builtins.print", lambda *a, **k: said.append(" ".join(map(str, a)))):
            job = pdfmd.start_calibre_job(self.args(), "docx", "docx")
        self.addCleanup(shutil.rmtree, job["scratch"], ignore_errors=True)
        self.assertTrue(any("docx is made by Calibre from an EPUB" in line for line in said), said)

    def test_the_file_is_named_after_the_document_or_goes_in_the_folder_given(self):
        job = {"goal": "azw3", "final": None, "scratch": Path(tempfile.mkdtemp(prefix="pdfmd-job-")), "open": False}
        self.addCleanup(shutil.rmtree, job["scratch"], ignore_errors=True)
        (job["scratch"] / "document.epub").write_bytes(b"epub")
        folder = Path(tempfile.mkdtemp(prefix="pdfmd-job-out-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        made = []

        def fake(source, output, verbose):
            made.append(output)
            return subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(pdfmd, "run_calibre_convert", fake):
            result = pdfmd.finish_convert_job(job, [(folder / "doc.md", True, None)], False)
            self.assertEqual(made[-1], folder / "doc.azw3")
            self.assertEqual(result[0].output, folder / "doc.azw3")
            self.assertEqual(result[0].engine, "calibre")
            pdfmd.finish_convert_job({**job, "final": folder}, [(folder / "doc.md", True, None)], False)
            self.assertEqual(made[-1], folder / "doc.azw3")
            pdfmd.finish_convert_job({**job, "final": folder / "mine"}, [(folder / "doc.md", True, None)], False)
            self.assertEqual(made[-1], folder / "mine.azw3")                       # no suffix: the format's
            failed = pdfmd.finish_convert_job(job, [(folder / "doc.md", False, "Pandoc failed")], False)
            self.assertEqual(failed, [(folder / "doc.md", False, "Pandoc failed")])    # a failed build stays as it was


class Math(unittest.TestCase):
    """v3.29.1: what becomes of the math in an ebook (the EPUB has MathML, which a Kindle does not draw)."""

    def job(self, goal, *, pictures=None, options=None):
        args = SimpleNamespace(batch=False, report=False, presentation=False, out=None, to=None, engine=None, open=False)
        with mock.patch.object(pdfmd, "resolve_calibre", return_value="/x"), \
                mock.patch.object(pdfmd, "math_pictures_possible", return_value=pictures), \
                mock.patch("builtins.print"):
            job = pdfmd.start_calibre_job(args, goal, goal, options if options is not None else [])
        self.addCleanup(shutil.rmtree, job["scratch"], ignore_errors=True)
        self.addCleanup(pdfmd.EBOOK_MATH.clear)
        return dict(pdfmd.EBOOK_MATH)

    def test_the_lists_are_targets_and_do_not_overlap(self):
        everything = set(pdfmd.CALIBRE_ONLY_FORMATS) | set(pdfmd.CALIBRE_SHARED_FORMATS)
        self.assertTrue(set(pdfmd.CALIBRE_MATH_PICTURES) <= everything)
        self.assertTrue(set(pdfmd.CALIBRE_MATH_TEXT) <= everything)
        self.assertFalse(set(pdfmd.CALIBRE_MATH_PICTURES) & set(pdfmd.CALIBRE_MATH_TEXT))
        self.assertTrue({"epub", "htmlz"}.isdisjoint(set(pdfmd.CALIBRE_MATH_PICTURES) | set(pdfmd.CALIBRE_MATH_TEXT)))

    def test_kindle_kobo_and_word_get_pictures_when_latex_can_draw_them(self):
        for goal in ("azw3", "mobi", "kepub", "docx"):
            self.assertEqual(self.job(goal)["mode"], "images", goal)

    def test_with_no_latex_they_get_text_and_the_reason(self):
        state = self.job("mobi", pictures="there is no LaTeX engine (lualatex, xelatex or pdflatex)")
        self.assertEqual(state["mode"], "text")
        self.assertIn("no LaTeX engine", state["why"])

    def test_the_plain_formats_get_text(self):
        for goal in ("pdb", "txtz", "fb2", "rtf"):
            self.assertEqual(self.job(goal)["mode"], "text", goal)

    def test_epub_and_htmlz_keep_their_mathml(self):
        for goal in ("epub", "htmlz"):
            self.assertIsNone(self.job(goal)["mode"], goal)

    def test_a_math_option_of_yours_is_kept(self):
        self.assertIsNone(self.job("mobi", options=["--mathml"])["mode"])
        self.assertIsNone(self.job("pdb", options=["--math-method=mathml"])["mode"])

    def test_the_filter_arguments_follow_the_mode(self):
        self.job("pdb")
        text = pdfmd.ebook_filter_args()
        self.assertIn("pdfmd-ebook-math=text", text)
        self.assertIn("pdfmd-ebook=pdb", text)
        self.assertEqual(text[-2], "--lua-filter")
        pdfmd.EBOOK_MATH.update({"mode": "images"})
        self.assertEqual(pdfmd.ebook_filter_args()[0], "--lua-filter")                # the pictures only need their titles cleaned


EBOOK_LUA = ROOT / "pdfmd_lua" / "ebook.lua"


@unittest.skipUnless(PANDOC, "needs Pandoc")
class EbookFilter(unittest.TestCase):
    def run_pandoc(self, text: str, *meta: str) -> tuple[str, str]:
        folder = Path(tempfile.mkdtemp(prefix="pdfmd-ebook-lua-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        out = folder / "o.epub"
        done = subprocess.run([PANDOC, "-f", "markdown", "-t", "epub", "-o", str(out), *pdfmd.html_math_args("mathml"),
                               "--lua-filter", str(EBOOK_LUA), *meta],
                              input=text, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        with zipfile.ZipFile(out) as archive:
            pages = "".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xhtml"))
        return pages, done.stderr

    def test_text_mode_writes_each_formula_as_text_and_says_so_once(self):
        pages, said = self.run_pandoc("Is $x^2$ and $\\frac{a}{b}$ and $x^2$.\n", "-M", "pdfmd-ebook-math=text",
                                      "-M", "pdfmd-ebook=pdb")
        self.assertNotIn("<math", pages)
        self.assertIn("<em>x</em><sup>2</sup>", pages)                               # the simple one as text with a superscript
        self.assertIn("$\\frac{a}{b}$", pages)                                       # the rest as its TeX
        self.assertEqual(said.count("WARN  pdb has no math: 3 formulas are text"), 1, said)

    def test_text_mode_names_why_when_pictures_were_wanted(self):
        _, said = self.run_pandoc("Is $x$.\n", "-M", "pdfmd-ebook-math=text", "-M", "pdfmd-ebook=mobi", "-M",
                                  "pdfmd-ebook-why=there is no LaTeX engine")
        self.assertIn("WARN  mobi has no math: 1 formula is text (the simple ones with their superscripts, the rest as TeX) - "
                      "there is no LaTeX engine", said)

    def test_without_the_mode_the_mathml_stays(self):
        pages, said = self.run_pandoc("Is $x^2$.\n")
        self.assertIn("<math", pages)
        self.assertNotIn("WARN  ", said)                                            # (Pandoc 3.1 adds a note on a missing title)

    def test_a_picture_title_that_names_the_cache_is_dropped_the_description_stays(self):
        pages, _ = self.run_pandoc('![LaTeX: x^2](data.svg "pdfmd:svg=/some/cache/x.svg;dp=1.5")\n\n![kept](data.svg "A title")\n')
        self.assertNotIn("pdfmd:svg", pages)
        self.assertIn("LaTeX: x^2", pages)
        self.assertIn('title="A title"', pages)


STUB = """#!{python}
import json, shutil, sys
log = {log!r}
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if {fail!r}:
    sys.stderr.write("ebook-convert stub: refused")
    sys.exit(1)
shutil.copyfile(sys.argv[1], sys.argv[2])
"""


SOFFICE_STUB = """#!{python}
import json, shutil, sys
from pathlib import Path
log = {log!r}
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if {fail!r}:
    sys.stderr.write("soffice stub: refused")
    sys.exit(1)
args = sys.argv[1:]
target = args[args.index("--convert-to") + 1].split(":")[0]
outdir = Path(args[args.index("--outdir") + 1])
source = Path(args[-1])
shutil.copyfile(source, outdir / (source.stem + "." + target))
"""


@unittest.skipUnless(PANDOC and sys.platform != "win32", "needs Pandoc and a POSIX shell for the stand-in ebook-convert")
class Build(unittest.TestCase):
    """The whole of pdfmd with a stand-in for ebook-convert that copies the EPUB it is given and logs its arguments."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calibre-target-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.log = self.directory / "calls.log"
        (self.directory / "d.md").write_text("---\ntitle: T\n---\n\n# H\n\nText with $x^2$.\n", encoding="utf-8")

    def stub(self, fail: bool = False) -> dict:
        folder = self.directory / "bin"
        folder.mkdir(exist_ok=True)
        script = folder / "ebook-convert"
        script.write_text(STUB.format(python=sys.executable, log=str(self.log), fail=fail), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return {**os.environ, "PATH": str(folder) + os.pathsep + os.environ.get("PATH", ""), "PDFMD_NO_PROMPT": "1"}

    def run_pdfmd(self, *args: str, fail: bool = False, text: str | None = None) -> subprocess.CompletedProcess:
        if text is not None:
            (self.directory / "d.md").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *args, "--no-stamp"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env=self.stub(fail))

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def test_a_suffix_makes_an_ebook_not_a_pdf_with_that_name(self):
        # the bug: `-o d.azw3` wrote a PDF named d.azw3
        done = self.run_pdfmd("-o", "d.azw3")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("OK    d.md > d.azw3  (calibre)", done.stdout)
        made = (self.directory / "d.azw3").read_bytes()
        self.assertTrue(made.startswith(b"PK"), made[:8])                           # the stand-in copied an EPUB (a zip)
        self.assertNotIn(b"%PDF", made[:8])
        (call,) = self.calls()
        self.assertTrue(call[0].endswith("document.epub"), call)
        self.assertTrue(call[1].endswith(".azw3"), call)
        self.assertFalse(Path(call[0]).parent.exists())                              # the scratch folder is gone

    def test_to_names_the_target_and_the_file_goes_beside_the_document(self):
        done = self.run_pdfmd("--to", "mobi")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "d.mobi").is_file())
        self.assertIn("OK    d.md > d.mobi  (calibre)", done.stdout)

    def test_e_calibre_takes_a_shared_format_with_a_note(self):
        done = self.run_pdfmd("-e", "calibre", "-o", "d.docx")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("docx is made by Calibre from an EPUB", done.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertTrue((self.directory / "d.docx").read_bytes().startswith(b"PK"))

    def test_without_e_calibre_pandoc_writes_a_shared_format(self):
        done = self.run_pdfmd("-o", "d.docx")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.calls(), [])
        self.assertNotIn("calibre", done.stdout)

    def test_a_pdf_engine_in_the_front_matter_is_a_pdf_setting(self):
        done = self.run_pdfmd("-o", "d.docx", text="---\ntitle: T\npdf-engine: calibre\n---\n\nText.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.calls(), [])

    def test_e_calibre_with_another_target_stops_and_lists_what_calibre_writes(self):
        done = self.run_pdfmd("-e", "calibre", "-o", "d.tex")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("-e calibre writes PDF", done.stdout + done.stderr)
        self.assertFalse((self.directory / "d.tex").exists())
        self.assertEqual(self.calls(), [])

    def test_a_failure_of_ebook_convert_is_reported_and_leaves_no_file(self):
        done = self.run_pdfmd("-o", "d.azw3", fail=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("FAIL  d.md", done.stdout)
        self.assertIn("ebook-convert failed", done.stdout)
        self.assertFalse((self.directory / "d.azw3").exists())

    def test_a_batch_is_refused_not_built_as_pdf(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-b", ".", "--to", "azw3", "--no-stamp"],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory, env=self.stub())
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("one document at a time", done.stdout + done.stderr)
        self.assertFalse(list(self.directory.glob("*.pdf")))
        self.assertEqual(self.calls(), [])

    def epub_pages(self, name: str) -> str:
        with zipfile.ZipFile(self.directory / name) as archive:
            return "".join(archive.read(item).decode("utf-8") for item in archive.namelist() if item.endswith(".xhtml"))

    def test_the_math_of_a_plain_format_is_text_with_one_warning(self):
        done = self.run_pdfmd("-o", "d.pdb")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((done.stdout + done.stderr).count("WARN  pdb has no math: 1 formula is text"), 1)
        self.assertNotIn("<math", self.epub_pages("d.pdb"))
        self.assertIn("<em>x</em><sup>2</sup>", self.epub_pages("d.pdb"))

    def test_an_epub_through_calibre_keeps_its_mathml(self):
        done = self.run_pdfmd("-e", "calibre", "-o", "d.epub")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("<math", self.epub_pages("d.epub"))

    @unittest.skipIf(pdfmd.math_pictures_possible() is not None, "needs LaTeX and pdftocairo to draw the formulas")
    def test_a_kindle_target_gets_the_formulas_as_pictures_without_this_machines_paths(self):
        done = self.run_pdfmd("-o", "d.mobi")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pages = self.epub_pages("d.mobi")
        self.assertNotIn("<math", pages)
        self.assertIn("LaTeX: x^2", pages)                                           # the description
        self.assertNotIn("pdfmd:", pages)                                            # not the cache path
        self.assertNotIn(str(Path.home()), pages)
        with zipfile.ZipFile(self.directory / "d.mobi") as archive:
            self.assertTrue([name for name in archive.namelist() if name.endswith((".svg", ".svgz", ".png"))])

    def test_an_engine_that_is_not_calibre_is_said_to_be_ignored(self):
        done = self.run_pdfmd("-e", "typst", "-o", "d.azw3")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("--engine is ignored for --to azw3: Calibre writes it", done.stderr)


@unittest.skipUnless(PANDOC and sys.platform != "win32", "needs Pandoc and a POSIX shell for the stand-in soffice")
class SofficeBuild(unittest.TestCase):
    """The whole of pdfmd with a stand-in for soffice that copies the Word file it is given and logs its arguments."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-soffice-target-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.log = self.directory / "calls.log"
        (self.directory / "d.md").write_text("---\ntitle: T\n---\n\n# H\n\nText.\n", encoding="utf-8")

    def run_pdfmd(self, *args: str, fail: bool = False) -> subprocess.CompletedProcess:
        folder = self.directory / "bin"
        folder.mkdir(exist_ok=True)
        script = folder / "soffice"
        script.write_text(SOFFICE_STUB.format(python=sys.executable, log=str(self.log), fail=fail), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        environment = {**os.environ, "PATH": str(folder) + os.pathsep + os.environ.get("PATH", ""), "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *args, "--no-stamp"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env=environment)

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def test_doc_is_made_from_the_word_file_pandoc_writes(self):
        done = self.run_pdfmd("-o", "d.doc")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("OK    d.md > d.doc  (soffice)", done.stdout)
        self.assertTrue((self.directory / "d.doc").read_bytes().startswith(b"PK"))            # the stand-in copied the .docx
        (call,) = self.calls()
        self.assertEqual(call[call.index("--convert-to") + 1], "doc")
        self.assertTrue(call[-1].endswith("document.docx"), call)
        self.assertFalse(Path(call[-1]).parent.exists())                                      # the scratch folder is gone

    def test_rtf_is_libreoffices_only_with_e_soffice(self):
        done = self.run_pdfmd("-e", "soffice", "-o", "d.rtf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("rtf is made by LibreOffice from the Word file", done.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.log.unlink()
        again = self.run_pdfmd("-o", "d.rtf")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(self.calls(), [])                                                    # Pandoc's own rtf

    def test_txt_goes_with_its_filter_name(self):
        done = self.run_pdfmd("-e", "soffice", "--to", "txt")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (call,) = self.calls()
        self.assertEqual(call[call.index("--convert-to") + 1], "txt:Text")
        self.assertTrue((self.directory / "d.txt").is_file())

    def test_a_pdf_engine_in_the_front_matter_does_not_move_an_rtf(self):
        (self.directory / "d.md").write_text("---\ntitle: T\npdf-engine: soffice\n---\n\nText.\n", encoding="utf-8")
        done = self.run_pdfmd("-o", "d.rtf")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.calls(), [])

    def test_e_soffice_with_another_target_stops_and_a_failure_leaves_no_file(self):
        done = self.run_pdfmd("-e", "soffice", "-o", "d.tex")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("-e soffice writes PDF", done.stdout + done.stderr)
        failed = self.run_pdfmd("-o", "d.doc", fail=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("soffice failed", failed.stdout)
        self.assertFalse((self.directory / "d.doc").exists())


@unittest.skipUnless(PANDOC and REAL_CALIBRE, "needs Pandoc and Calibre's ebook-convert")
class RealCalibre(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calibre-real-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        (self.directory / "d.md").write_text("---\ntitle: Real\nauthor: A. Writer\n---\n\n# Head\n\nA distinctive zebra "
                                             "sentence.\n\n- item alpha\n- item beta\n", encoding="utf-8")

    def make(self, name: str) -> bytes:
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-o", name, "--no-stamp"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return (self.directory / name).read_bytes()

    def test_azw3_and_mobi_are_palm_databases_not_pdfs(self):
        for name in ("d.azw3", "d.mobi"):
            data = self.make(name)
            self.assertEqual(data[60:68], b"BOOKMOBI", name)

    def test_kepub_is_a_zip(self):
        self.assertTrue(self.make("d.kepub").startswith(b"PK"))

    def test_the_words_are_in_the_ebook(self):
        data = self.make("d.azw3")
        back = self.directory / "back.txt"
        (self.directory / "x.azw3").write_bytes(data)
        done = subprocess.run([REAL_CALIBRE, str(self.directory / "x.azw3"), str(back)], capture_output=True, text=True,
                              env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        self.assertIn("zebra", back.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

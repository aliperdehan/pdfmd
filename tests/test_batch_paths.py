"""Several explicit inputs use the same batch pipeline as a folder (v3.33.140)."""

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402
import pdfmd_batch  # noqa: E402


class Selection(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-batch-paths-")
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)

    def source(self, name, text="# Example\n"):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def collect(self, paths, recursive=False, include_never=False):
        return pdfmd_batch.collect_inputs(pdfmd, paths, recursive, include_never)

    def test_source_likeness_covers_accepted_markdown_and_markup(self):
        markdown, markup, html, office = pdfmd_batch.SOURCE_LIKENESS
        self.assertTrue({".md", ".markdown", ".mdown", ".mkd"} <= markdown)
        self.assertTrue({".txt", ".rst", ".org", ".adoc", ".textile", ".tex", ".typ", ".typst"} <= markup)
        self.assertTrue({".html", ".htm"} <= html)
        self.assertTrue({".docx", ".odt", ".rtf", ".epub", ".pptx"} <= office)

    def test_explicit_formats_use_existing_extension_tables(self):
        names = ("letter.markdown", "source.rst", "source.org", "source.tex", "source.typst", "source.html",
                 "source.txt", "source.docx", "source.odt", "source.epub", "source.ipynb", "source.wiki")
        files = [self.source(name) for name in names]
        self.assertEqual(self.collect(files), [path.resolve() for path in files])

    def test_folder_scan_is_still_md_only_and_recursive_is_optional(self):
        a = self.source("dir/a.md")
        self.source("dir/other.rst")
        nested = self.source("dir/nested/b.md")
        self.assertEqual(self.collect([a.parent]), [a.resolve()])
        self.assertEqual(self.collect([a.parent], recursive=True), [a.resolve(), nested.resolve()])

    def test_resolved_duplicates_and_folder_overlap_are_built_once(self):
        a = self.source("dir/a.md")
        b = self.source("dir/b.md")
        self.assertEqual(self.collect([a, a.parent, a.parent / "../dir/a.md"]), [a.resolve(), b.resolve()])

    @unittest.skipIf(os.name == "nt", "symlinks need a privilege on Windows")
    def test_symlink_is_the_same_input(self):
        a = self.source("a.md")
        link = self.folder / "link.md"
        link.symlink_to(a)
        self.assertEqual(self.collect([a, link]), [a.resolve()])

    def test_priority_never_only_excludes_folder_discovery(self):
        a = self.source("dir/a.md", "---\npdfmd-options: {priority: never}\n---\nA\n")
        b = self.source("dir/b.md")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.collect([a.parent]), [b.resolve()])
            self.assertEqual(self.collect([a, a.parent]), [a.resolve(), b.resolve()])
            self.assertEqual(self.collect([a.parent], include_never=True), [a.resolve(), b.resolve()])

    def test_missing_input_is_an_error(self):
        with self.assertRaisesRegex(SystemExit, "no such file or directory"):
            self.collect([self.folder / "missing.md"])

    def test_non_pandoc_routes_and_pictures_are_skipped(self):
        a = self.source("a.md")
        skipped = [self.source("old" + suffix) for suffix in (".pdf", ".png", ".doc", ".mobi", ".qmd", ".ansi")]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.collect([a, *skipped]), [a.resolve()])
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        for path in skipped:
            self.assertIn(path.name, output.getvalue())

    def test_output_name_hint_needs_two_paths_in_the_same_folder(self):
        a = self.source("a.md")
        pdf = self.source("a.pdf")
        elsewhere = self.source("other/b.pdf")
        for paths, hint in (([a, pdf], True), ([a, elsewhere], False), ([a, pdf, elsewhere], False)):
            with self.subTest(paths=paths), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.collect(paths), [a.resolve()])
            self.assertEqual("to name the output, use -o NAME.pdf" in output.getvalue(), hint)


class Checkout(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-batch-cli-")
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)
        self.work = self.folder / "work"
        self.work.mkdir()
        self.environment = dict(os.environ, PDFMD_CONFIG="", PDFMD_NO_PROMPT="1",
                                XDG_CONFIG_HOME=str(self.folder / "config"),
                                XDG_CACHE_HOME=str(self.folder / "cache"),
                                XDG_DATA_HOME=str(self.folder / "data"))
        self.names = ("04 Motivation letter (RU).md", "05 Достижения [RU].md")
        for name in self.names:
            (self.work / name).write_text("# Example\n\nSome text.\n", encoding="utf-8")

    def run_pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), *map(str, arguments)],
                              cwd=self.work, env=self.environment, stdin=subprocess.DEVNULL,
                              capture_output=True, encoding="utf-8", timeout=180)

    def assert_built(self, done, count, folder=None, suffix=".pdf"):
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sum(line.startswith("OK    ") for line in done.stdout.splitlines()), count, done.stdout)
        self.assertEqual(len(list((folder or self.work).glob("*" + suffix))), count, done.stdout)

    def test_explicit_files_with_source_attachments(self):
        done = self.run_pdfmd("-b", *self.names, "-e", "inkmd", "--attach-source")
        self.assert_built(done, 2)
        for name in self.names:
            attached = pdfmd.read_pdf_attachments(self.work / Path(name).with_suffix(".pdf"))
            self.assertIn(pdfmd.ATTACH_MANIFEST, attached)

    def test_plain_files_implicitly_batch_without_pandoc(self):
        self.environment["PATH"] = str(self.folder / "empty-path")
        self.assert_built(self.run_pdfmd(*self.names), 2)

    def test_mixed_file_and_folder_and_duplicate(self):
        directory = self.work / "dir"
        directory.mkdir()
        (directory / "b.md").write_text("# B\n", encoding="utf-8")
        a = self.work / "a.md"
        a.write_text("# A\n", encoding="utf-8")
        done = self.run_pdfmd("-b", a, directory, directory / "b.md", "-e", "inkmd", "-o", "out")
        self.assert_built(done, 2, self.work / "out")

    def test_expanded_glob_skips_outputs_and_pictures_in_one_note(self):
        # The shell expands * before pdfmd runs: a folder, sources, earlier PDFs and pictures.
        for path in self.work.iterdir():
            path.unlink()
        for name in ("a.md", "b.md"):
            (self.work / name).write_text("# Test\n", encoding="utf-8")
        self.assertEqual(self.run_pdfmd("a.md", "-e", "inkmd").returncode, 0)
        (self.work / "picture.png").write_bytes(b"picture")
        outputs = self.work / "earlier outputs"
        outputs.mkdir()
        (outputs / "old.pdf").write_bytes(b"old output")
        for prefix in (("-b",), ()):
            with self.subTest(prefix=prefix):
                done = self.run_pdfmd(*prefix, *sorted(self.work.iterdir()), "-e", "inkmd")
                self.assert_built(done, 2)
                notes = [line for line in done.stdout.splitlines() if line.startswith("NOTE  skipped non-input paths:")]
                self.assertEqual(len(notes), 1, done.stdout)
                self.assertIn("a.pdf", notes[0])
                self.assertIn("picture.png", notes[0])
                self.assertEqual((outputs / "old.pdf").read_bytes(), b"old output")

    def test_nothing_buildable_fails_clearly(self):
        (self.work / "old.pdf").write_bytes(b"old")
        (self.work / "picture.png").write_bytes(b"image")
        done = self.run_pdfmd("-b", "old.pdf", "picture.png")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("No buildable input files", done.stderr)
        self.assertEqual(done.stdout.count("NOTE  skipped non-input paths:"), 1)

    def test_pdfs_alone_in_a_list_are_skipped_before_the_pdf_reader(self):
        for name in ("a.pdf", "b.pdf"):
            (self.work / name).write_bytes(b"earlier output")
        done = self.run_pdfmd("a.pdf", "b.pdf")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("No buildable input files", done.stderr)
        self.assertEqual(done.stdout.count("NOTE  skipped non-input paths:"), 1)
        self.assertNotIn("batchocr", done.stdout + done.stderr)

    def test_two_paths_skip_the_pdf_and_explain_output_naming(self):
        (self.work / "out.pdf").write_bytes(b"earlier output")
        done = self.run_pdfmd(self.names[0], "out.pdf", "-e", "inkmd")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("to name the output, use -o NAME.pdf", done.stdout)
        self.assertEqual((self.work / "out.pdf").read_bytes(), b"earlier output")

    def test_single_pdf_still_uses_the_pdf_reader(self):
        (self.work / "old.pdf").write_bytes(b"old output")
        self.environment["PDFMD_BATCHOCR"] = str(self.folder / "no-batchocr")
        done = self.run_pdfmd("old.pdf", "--extract")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("batchocr", done.stdout + done.stderr)
        self.assertNotIn("skipped non-input", done.stdout + done.stderr)

    def run_compat(self, command, *arguments):
        code = "import sys; sys.path.insert(0, sys.argv.pop(1)); import pdfmd; pdfmd.%s_main()" % command
        return subprocess.run([sys.executable, "-c", code, str(ROOT), *map(str, arguments)],
                              cwd=self.work, env=self.environment, stdin=subprocess.DEVNULL,
                              capture_output=True, encoding="utf-8", timeout=180)

    def test_mdpdf_trailing_pdf_is_still_the_output(self):
        done = self.run_compat("mdpdf", self.names[0], "named.pdf", "-e", "inkmd")
        self.assert_built(done, 1)
        self.assertTrue((self.work / "named.pdf").is_file())
        self.assertNotIn("skipped non-input", done.stdout + done.stderr)

    def test_other_compat_input_and_output_options_keep_their_meaning(self):
        for command, inputs in (("md2pdf", ("-i", self.names[0])), ("inkmd", (self.names[0],)),
                                ("pan_tec", (self.names[0],))):
            with self.subTest(command=command):
                done = self.run_compat(command, *inputs, "-o", command + ".pdf", "-e", "inkmd")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue((self.work / (command + ".pdf")).is_file())
        self.assert_built(self.run_compat("batchmd", *self.names, "-e", "inkmd", "-o", "batch"),
                          2, self.work / "batch")

    def test_no_files_in_folder_is_an_error(self):
        (self.work / "empty").mkdir()
        done = self.run_pdfmd("-b", "empty")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("No buildable input files", done.stderr)

    def test_one_file_keeps_single_mode_output(self):
        done = self.run_pdfmd(self.names[0], "-e", "inkmd", "-o", "named.pdf")
        self.assert_built(done, 1)
        self.assertTrue((self.work / "named.pdf").is_file())

    def test_batch_output_file_is_refused_and_existing_dotted_directory_is_allowed(self):
        for prefix in (("-b",), ()):
            with self.subTest(prefix=prefix):
                done = self.run_pdfmd(*prefix, *self.names, "-e", "inkmd", "-o", "one.pdf")
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("-o", done.stderr)
                self.assertIn("directory", done.stderr)
                self.assertFalse((self.work / "one.pdf").exists())
        output = self.work / "out.pdf"
        output.mkdir()
        self.assert_built(self.run_pdfmd(*self.names, "-e", "inkmd", "-o", output), 2, output)

    def test_single_document_options_use_batch_refusals(self):
        for flags, message in ((("--watch",), "only supports single-file mode"),
                               (("--section", "intro"), "take one document")):
            for prefix in (("-b",), ()):
                with self.subTest(prefix=prefix, flags=flags):
                    if flags == ("--watch",) and not shutil.which("pandoc"):
                        self.skipTest("needs Pandoc")
                    done = self.run_pdfmd(*prefix, *self.names, *flags)
                    self.assertNotEqual(done.returncode, 0)
                    self.assertIn(message, done.stderr)
        self.assertEqual(list(self.work.glob("*.pdf")), [])

    def test_same_pdf_destination_prefers_markdown(self):
        for stem in ("a", "Документ с пробелом"):
            with self.subTest(stem=stem):
                md, html = stem + ".md", stem + ".html"
                (self.work / md).write_text("# Source\n", encoding="utf-8")
                (self.work / html).write_text("<p>Old output</p>", encoding="utf-8")
                done = self.run_pdfmd(html, md, "-e", "inkmd")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(sum(line.startswith("OK    ") for line in done.stdout.splitlines()), 1)
                self.assertIn(f"NOTE  skipped (same output as {md}): {html}", done.stdout)
                self.assertNotIn("skipped non-input paths", done.stdout)
                self.assertTrue((self.work / (stem + ".pdf")).is_file())

    def test_collision_and_non_input_have_separate_notes(self):
        (self.work / "a.md").write_text("# Source\n", encoding="utf-8")
        (self.work / "a.html").write_text("<p>Old</p>", encoding="utf-8")
        (self.work / "image.png").write_bytes(b"image")
        done = self.run_pdfmd("a.html", "a.md", "image.png", "-e", "inkmd")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("NOTE  skipped non-input paths: image.png", done.stdout)
        self.assertIn("NOTE  skipped (same output as a.md): a.html", done.stdout)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_same_destination_prefers_html_to_docx(self):
        (self.work / "a.html").write_text("<p>HTML source</p>", encoding="utf-8")
        (self.work / "a.docx").write_bytes(b"not a docx")
        done = self.run_pdfmd("a.docx", "a.html", "--to", "latex")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sum(line.startswith("OK    ") for line in done.stdout.splitlines()), 1)
        self.assertIn("NOTE  skipped (same output as a.html): a.docx", done.stdout)
        self.assertIn("HTML source", (self.work / "a.tex").read_text(encoding="utf-8"))

    def test_same_destination_in_output_folder_uses_name_tiebreak(self):
        for folder in ("z", "a"):
            (self.work / folder).mkdir()
            (self.work / folder / "same.md").write_text("# Source\n", encoding="utf-8")
        done = self.run_pdfmd("z/same.md", "a/same.md", "-e", "inkmd", "-o", "out")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sum(line.startswith("OK    ") for line in done.stdout.splitlines()), 1)
        # (display_path() writes the system's separator: `a\same.md` on Windows)
        self.assertIn("NOTE  skipped (same output as a/same.md): z/same.md".replace("/", os.sep), done.stdout)
        self.assertTrue((self.work / "out/same.pdf").is_file())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_rebuild_glob_skips_built_outputs_but_keeps_independent_html(self):
        independent = self.work / "independent.html"
        for prefix in ((), ("-b",)):
            with self.subTest(prefix=prefix):
                self.assert_built(self.run_pdfmd(*prefix, *self.names, "--to", "html"), 2, suffix=".html")
                independent.write_text("<p>Independent</p>", encoding="utf-8")
                done = self.run_pdfmd(*prefix, *sorted(self.work.iterdir()), "--to", "html", "-o", "out")
                # Outputs in the source folder are not outputs in the selected destination.
                self.assertNotIn("built outputs:", done.stdout)
                done = self.run_pdfmd(*prefix, *sorted(p for p in self.work.iterdir() if p.is_file()), "--to", "html")
                self.assertIn("built outputs:", done.stdout)
                for name in self.names:
                    self.assertIn(Path(name).with_suffix(".html").name, done.stdout)
                # The independent HTML remains an input and hits the ordinary self-output protection.
                self.assertIn("independent.html is the source itself", done.stdout + done.stderr)
                independent.unlink()
                done = self.run_pdfmd(*prefix, *sorted(p for p in self.work.iterdir() if p.is_file()), "--to", "html")
                self.assert_built(done, 2, suffix=".html")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_rebuild_respects_no_rewrite(self):
        self.assert_built(self.run_pdfmd(*self.names, "--to", "html"), 2, suffix=".html")
        done = self.run_pdfmd("-b", *sorted(self.work.iterdir()), "--to", "html", "--no-rewrite")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("built outputs:", done.stdout)
        for name in self.names:
            self.assertTrue((self.work / (Path(name).stem + " (1).html")).is_file())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_glob_outputs_in_named_directory_and_compound_extension(self):
        out = self.work / "out"
        out.mkdir()
        for name in self.names:
            (out / Path(name).with_suffix(".gfm.md")).write_text("old", encoding="utf-8")
        done = self.run_pdfmd(*self.names, *sorted(out.iterdir()), "--to", "gfm", "-o", out)
        self.assert_built(done, 2, out, ".gfm.md")
        self.assertIn("built outputs:", done.stdout)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_workers_cover_explicit_files_and_folders_with_pandoc(self):
        directory = self.work / "dir"
        directory.mkdir()
        (directory / "third.md").write_text("# Third\n", encoding="utf-8")
        done = self.run_pdfmd("-b", *self.names, directory, "-j", "2", "--to", "html", "-o", "out")
        self.assert_built(done, 3, self.work / "out", ".html")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_non_markdown_pandoc_input_is_built(self):
        (self.work / "other.rst").write_text("Other\n=====\n\nSome text.\n", encoding="utf-8")
        self.assert_built(self.run_pdfmd(self.names[0], "other.rst", "--to", "html"), 2, suffix=".html")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_report_still_merges_several_files(self):
        done = self.run_pdfmd("-r", *self.names, "--to", "html", "-o", "report.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.work / "report.html").is_file())
        self.assertEqual(len(list(self.work.glob("*.html"))), 1)


class CodePageStreams(unittest.TestCase):
    """A stream in a Windows code page (a pipe, or a console that is not UTF-8, before Python 3.15) never ends a run."""

    def code_page_stream(self, errors="strict"):
        raw = io.BytesIO()
        return raw, io.TextIOWrapper(raw, encoding="cp1252", errors=errors, write_through=True)

    def test_a_strict_stream_prints_a_question_mark_for_what_it_lacks(self):
        import pdfmd_view
        raw, stream = self.code_page_stream()
        with self.assertRaises(UnicodeEncodeError):
            stream.write("NATIVE  Документ.md via inkmd\n")
        raw, stream = self.code_page_stream()
        pdfmd_view.tolerant_streams([stream])
        self.assertEqual((stream.encoding, stream.errors), ("cp1252", "replace"))
        tee = pdfmd._WarningTee(stream, [])                    # the wrapper a build prints through
        print("NATIVE  Документ.md via inkmd — é", file=tee)
        self.assertEqual(raw.getvalue().decode("cp1252").rstrip("\r\n"), "NATIVE  ????????.md via inkmd — é")

    def test_a_chosen_error_handler_and_a_plain_text_buffer_are_left_alone(self):
        import pdfmd_view
        _, stream = self.code_page_stream("backslashreplace")
        text = io.StringIO()
        pdfmd_view.tolerant_streams([stream, text, None])
        self.assertEqual(stream.errors, "backslashreplace")
        closed = self.code_page_stream()[1]
        closed.close()
        pdfmd_view.tolerant_streams([closed])                  # no exception

    def test_a_build_with_cp1252_output_names_a_cyrillic_file(self):
        folder = Path(tempfile.mkdtemp(prefix="pdfmd-codepage-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "work").mkdir()
        (folder / "work" / "Документ с пробелом.md").write_text("# Example\n\nSome text.\n", encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1", "PYTHONIOENCODING": "cp1252",
                       "XDG_CONFIG_HOME": str(folder / "config"), "XDG_CACHE_HOME": str(folder / "cache"),
                       "XDG_DATA_HOME": str(folder / "data")}
        for jobs in ((), ("-b", "-j", "2")):
            with self.subTest(jobs=jobs):
                done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), *jobs, "Документ с пробелом.md",
                                       "-e", "inkmd"], cwd=folder / "work", env=environment, stdin=subprocess.DEVNULL,
                                      capture_output=True, encoding="cp1252", errors="replace", timeout=180)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertNotIn("UnicodeEncodeError", done.stdout + done.stderr)
                self.assertIn("NATIVE  ???????? ? ????????.md via inkmd", done.stdout)
                self.assertTrue((folder / "work" / "Документ с пробелом.pdf").is_file())


if __name__ == "__main__":
    unittest.main()

"""Finding a document by name: what always worked, and what v3.21.0 adds.

find_markdown() keeps its exact rules first; only when they fail does it try
aliases, titles, starts of names and looser spellings. The first class of test
guards the first half (a shared dependency must not change what a name used to
mean); the rest covers the second.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class LookupCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        self._previous = (Path.cwd(), pdfmd.FUZZY_LOOKUP)
        os.chdir(self.root)
        pdfmd.FUZZY_LOOKUP = True
        pdfmd._LOOKUP_ANNOUNCED.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._previous[0])
        pdfmd.FUZZY_LOOKUP = self._previous[1]

    def write(self, name: str, text: str = "text\n") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def find(self, name: str):
        """(path, stdout, stderr) of find_markdown(Path(name))."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            path = pdfmd.find_markdown(Path(name))
        return path, out.getvalue(), err.getvalue()


class ExistingLookupUnchanged(LookupCase):
    def test_exact_stem_and_extension(self):
        report = self.write("report.md")
        for name in ("report", "report.md", "REPORT", "Report.MD"):
            # On a case-insensitive filesystem (macOS, Windows) the path comes back as typed.
            self.assertTrue(os.path.samefile(self.find(name)[0], report), name)

    def test_dots_in_the_name(self):
        notes = self.write("prelab5.5.md")
        self.write("prelab5.md")
        self.assertEqual(self.find("prelab5.5")[0], notes)

    def test_latin_name_for_a_cyrillic_file(self):
        tea = self.write("чай.md")
        path, out, err = self.find("chai")
        self.assertEqual(path, tea)
        self.assertEqual((out, err), ("", ""))   # the old spelling rules stay silent

    def test_probnyy_prefix(self):
        trial = self.write("Пробный отчёт.md")
        self.assertEqual(self.find("отчёт")[0], trial)

    def test_wildcard(self):
        scrutiny = self.write("CAS001_cassirer_scrutiny.md")
        self.assertEqual(self.find("*scrutiny")[0], scrutiny)

    def test_an_exact_file_beats_every_guess(self):
        self.write("An Important Document.md")
        short = self.write("animp.md")
        path, out, err = self.find("animp")
        self.assertEqual(path, short)
        self.assertEqual((out, err), ("", ""))

    def test_a_missing_name_is_still_an_error_that_lists_the_files(self):
        self.write("alpha.md")
        with self.assertRaisesRegex(FileNotFoundError, "Could not find Markdown file for 'zzz'. Available: alpha"):
            self.find("zzz")

    def test_the_switch_restores_the_old_behaviour(self):
        self.write("An Important Document.md")
        pdfmd.FUZZY_LOOKUP = False
        with self.assertRaises(FileNotFoundError):
            self.find("animportantdocument")


class FuzzyLookup(LookupCase):
    def test_spaces_underscores_case_and_hyphens_are_not_part_of_a_name(self):
        document = self.write("An Important Document.md")
        for name in ("animportantdocument", "an_important_document", "AN-IMPORTANT-DOCUMENT", "an.important.document"):
            self._reset()
            path, out, err = self.find(name)
            self.assertEqual(path, document, name)
            self.assertTrue(out.startswith("AUTO MD"), out)   # announced, but not a guess
            self.assertEqual(err, "")

    def _reset(self):
        pdfmd._LOOKUP_ANNOUNCED.clear()

    def test_the_start_of_a_name_works_with_a_warning(self):
        document = self.write("An Important Document.md")
        path, out, err = self.find("animp")
        self.assertEqual(path, document)
        self.assertIn("WARN", err)
        self.assertIn("the start of its alias or file name", err)
        self.assertIn("--no-auto lookup", err)

    def test_a_start_shorter_than_three_characters_is_not_a_guess_worth_making(self):
        self.write("An Important Document.md")
        with self.assertRaises(FileNotFoundError):
            self.find("an")

    def test_title_and_the_start_of_a_title(self):
        document = self.write("doc.md", "---\ntitle: Glucose in our body\n---\ntext\n")
        path, out, err = self.find("glucoseinourbody")
        self.assertEqual((path, err), (document, ""))
        self._reset()
        path, out, err = self.find("glucose")
        self.assertEqual(path, document)
        self.assertIn("the start of its title", err)

    def test_a_word_inside_a_title(self):
        document = self.write("doc.md", "---\ntitle: Glucose in our body\n---\ntext\n")
        path, out, err = self.find("body")
        self.assertEqual(path, document)
        self.assertIn("the start of a word", err)

    def test_percent_title_line(self):
        document = self.write("n.md", "% Soil moisture\n\ntext\n")
        self.assertEqual(self.find("soilmoisture")[0], document)

    def test_an_alias_names_a_document_whatever_its_file_is_called(self):
        document = self.write("x.md", "---\npdfmd-options:\n  alias: [doc1, first]\n---\ntext\n")
        for name in ("doc1", "first", "DOC_1"):
            self._reset()
            self.assertEqual(self.find(name)[0], document, name)

    def test_a_bare_pdfmd_title_is_an_alias_too(self):
        document = self.write("x.md", "---\npdfmd-title: doc7\n---\ntext\n")
        self.assertEqual(self.find("doc7")[0], document)

    def test_an_alias_beats_a_title_and_a_file_name_beats_an_alias(self):
        titled = self.write("a.md", "---\ntitle: Notes\n---\n")
        aliased = self.write("b.md", "---\npdfmd-options:\n  alias: notes\n---\n")
        self.assertEqual(self.find("notes")[0], aliased)
        named = self.write("notes.md")
        self.assertEqual(self.find("notes")[0], named)
        self.assertNotEqual(titled, named)

    def test_two_equally_good_documents_are_an_error_that_names_both(self):
        self.write("a.md", "---\ntitle: Yield\n---\n")
        self.write("b.md", "---\ntitle: yield!\n---\n")
        with self.assertRaisesRegex(LookupError_, "a.md.*b.md"):
            self.find("yield")

    def test_ambiguity_is_a_file_not_found_error_so_old_handlers_still_catch_it(self):
        self.assertTrue(issubclass(pdfmd.LookupAmbiguous, FileNotFoundError))

    def test_hidden_files_are_not_candidates(self):
        self.write(".glucose.pdfmd-part-x.md")
        with self.assertRaises(FileNotFoundError):
            self.find("glucose")

    def test_a_folder_beside_the_name_is_searched(self):
        document = self.write("sub/An Important Document.md")
        self.assertEqual(self.find("sub/animportant")[0], document)

    def test_nothing_is_announced_twice(self):
        self.write("An Important Document.md")
        first = self.find("animp")
        second = self.find("animp")
        self.assertIn("WARN", first[2])
        self.assertEqual(second[2], "")


class Scripts(LookupCase):
    def test_latin_finds_cyrillic_and_back(self):
        glucose = self.write("a.md", "---\ntitle: Глюкоза\n---\n")
        for name in ("glyukoza", "glukoza", "GLUKOZA"):
            self._clear()
            self.assertEqual(self.find(name)[0], glucose, name)
        self._clear()
        self.assertEqual(self.find("Глюкоза")[0], glucose)

    def _clear(self):
        pdfmd._LOOKUP_ANNOUNCED.clear()

    def test_yo_and_ye_are_one_letter(self):
        document = self.write("a.md", "---\ntitle: Ёлка\n---\n")
        self.assertEqual(self.find("елка")[0], document)

    def test_turkish_letters_with_and_without_their_marks(self):
        document = self.write("Şekerler ve Tatlılar.md")
        for name in ("sekerler", "şekerler", "ŞEKERLER", "sekerlervetatlilar"):
            self._clear()
            self.assertEqual(self.find(name)[0], document, name)

    def test_kazakh_titles_in_latin_letters(self):
        history = self.write("kz.md", "---\ntitle: Қазақстан тарихы\n---\n")
        for name in ("Qazaqstan tarihy", "qazaqstan-tarihi", "kazakstan tarihi", "qazaq"):
            self._clear()
            self.assertEqual(self.find(name)[0], history, name)

    def test_kazakh_u_and_y_and_i_vowels(self):
        # у ұ ү are all u; ы і и й are all i; a Latin y or w may be either.
        for title, query in (("Ұлт", "ult"), ("Үй", "uy"), ("Қыз", "kiz"), ("Қыз", "qyz"),
                             ("Күн", "kun"), ("Тұз", "tuz"), ("Ауыл", "awyl"), ("Ауыл", "auil")):
            with self.subTest(title=title, query=query):
                self._clear()
                for item in self.root.glob("*.md"):
                    item.unlink()
                document = self.write("d.md", f"---\ntitle: {title}\n---\n")
                self.assertEqual(self.find(query)[0], document)

    def test_keys(self):
        self.assertEqual(pdfmd.lookup_key("An Important_Document.v2"), "animportantdocumentv2")
        self.assertEqual(pdfmd.lookup_key("Глюкоза"), pdfmd.lookup_key("glyukoza"))
        self.assertEqual(pdfmd.lookup_key("Şeker"), pdfmd.lookup_key("sheker"))
        self.assertEqual(pdfmd.lookup_key("Қазақ"), "qazaq")
        self.assertEqual(pdfmd.lookup_key("zzz"), "zzz")
        self.assertEqual(pdfmd.lookup_key("   "), "")


LookupError_ = pdfmd.LookupAmbiguous

if __name__ == "__main__":
    unittest.main()

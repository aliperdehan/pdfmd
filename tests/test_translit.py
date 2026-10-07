"""Romanization packs: finding 命運.md by `mingyun`, Τύχη.md by `tyche`, ... (pdfmd_unicode/translit.py)."""

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

# never read or write the real user's config and state while testing
import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402
from pdfmd_unicode import translit  # noqa: E402


def packs(*names):
    return frozenset(names)


class Tables(unittest.TestCase):
    def test_greek_is_the_scholarly_latinization(self):
        for greek, latin in (("Τύχη", "tyche"), ("Ἀνάγκη", "ananke"), ("μοῖρα", "moira"), ("Ἀριστοτέλης", "aristoteles"),
                             ("Οὐρανός", "ouranos"), ("αὐτός", "autos"), ("φιλοσοφία", "philosophia")):
            self.assertEqual(translit.romanize(greek, packs("greek")), latin, greek)

    def test_other_alphabets(self):
        self.assertEqual(translit.romanize("Մովսես", packs("armenian")), "movses")
        self.assertEqual(translit.romanize("საქართველო", packs("georgian")), "sakartvelo")
        self.assertEqual(translit.romanize("גורל", packs("hebrew")), "gvrl")          # consonants only
        self.assertEqual(translit.romanize("القدر", packs("arabic")), "alqdr")
        self.assertEqual(translit.romanize("پژوهش", packs("arabic")), "pzhwhsh")      # Persian letters

    def test_hangul_romanized_with_the_usual_liaison(self):
        self.assertEqual(translit.romanize("한국어", packs("hangul")), "hangugeo")
        self.assertEqual(translit.romanize("운명", packs("hangul")), "unmyeong")
        self.assertEqual(translit.romanize("서울 abc", packs("hangul")), "seoul abc")

    def test_kana_by_hepburn(self):
        self.assertEqual(translit.romanize("きょうと", packs("kana")), "kyouto")
        self.assertEqual(translit.romanize("トウキョウ", packs("kana")), "toukyou")
        self.assertEqual(translit.romanize("がっこう", packs("kana")), "gakkou")
        self.assertEqual(translit.romanize("しゃしん", packs("kana")), "shashin")
        self.assertEqual(translit.romanize("まっちゃ", packs("kana")), "matcha")
        self.assertEqual(translit.romanize("ファイル", packs("kana")), "fairu")

    def test_only_enabled_scripts_are_touched(self):
        self.assertEqual(translit.romanize("Τύχη 命運 abc", packs("greek")), "tyche 命運 abc")
        self.assertEqual(translit.romanize("Τύχη", packs()), "Τύχη")
        self.assertEqual(translit.romanize("plain ascii", packs("greek", "han")), "plain ascii")

    def test_han_needs_a_library_and_uses_it(self):
        real = translit._han_library
        try:
            translit._han_library = lambda: None
            self.assertFalse(translit.available("han"))
            self.assertEqual(translit.romanize("命運", packs("han")), "命運")
            translit._han_library = lambda: (lambda text: " ".join({"命": "ming", "運": "yun"}[c] for c in text))
            self.assertTrue(translit.available("han"))
            self.assertEqual(translit.romanize("a 命運 b", packs("han")), "a ming yun b")
        finally:
            translit._han_library = real


class Lookup(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name).resolve()
        self._previous = (Path.cwd(), pdfmd.FUZZY_LOOKUP)
        os.chdir(self.root)
        pdfmd.FUZZY_LOOKUP = True
        pdfmd._LOOKUP_ANNOUNCED.clear()
        self.addCleanup(self._restore)
        for name in ("Τύχη.md", "운명.md", "Глюкоза.md", "plain.md"):
            (self.root / name).write_text("# " + name + "\n\ntext\n", encoding="utf-8")

    def _restore(self):
        os.chdir(self._previous[0])
        pdfmd.FUZZY_LOOKUP = self._previous[1]
        pdfmd.set_translit(None)

    def find(self, name: str):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return pdfmd.find_markdown(Path(name))

    def test_cyrillic_is_on_by_default_and_the_rest_is_off(self):
        self.assertEqual(self.find("glyukoza").name, "Глюкоза.md")
        with self.assertRaises(FileNotFoundError):
            self.find("tyche")
        with self.assertRaises(FileNotFoundError):
            self.find("unmyeong")

    def test_a_pack_makes_its_script_findable(self):
        self.assertEqual(pdfmd.set_translit("greek, hangul"), [])
        self.assertEqual(self.find("tyche").name, "Τύχη.md")
        self.assertEqual(self.find("Tyche").name, "Τύχη.md")
        self.assertEqual(self.find("unmyeong").name, "운명.md")
        self.assertEqual(self.find("glyukoza").name, "Глюкоза.md")

    def test_none_turns_cyrillic_off_too(self):
        pdfmd.set_translit("none")
        with self.assertRaises(FileNotFoundError):
            self.find("glyukoza")
        self.assertEqual(self.find("Глюкоза").name, "Глюкоза.md")  # the real name still works

    def test_bad_and_unavailable_packs_are_reported(self):
        self.assertTrue(any("unknown" in problem for problem in pdfmd.set_translit("klingon")))
        real = translit._han_library
        try:
            translit._han_library = lambda: None
            problems = pdfmd.set_translit("han")
            self.assertTrue(any("pypinyin" in problem for problem in problems), problems)
            self.assertNotIn("han", pdfmd.TRANSLIT_PACKS)
        finally:
            translit._han_library = real

    def test_existing_keys_do_not_change(self):
        self.assertEqual(pdfmd.lookup_key("Қазақ"), "qazaq")
        self.assertEqual(pdfmd.lookup_key("Глюкоза"), pdfmd.lookup_key("glyukoza"))
        self.assertEqual(pdfmd.lookup_key("phone", True), pdfmd.lookup_key("fone", True))  # ph ~ f (Greek φ)


if __name__ == "__main__":
    unittest.main()

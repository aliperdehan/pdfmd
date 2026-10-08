"""`pdfmd --install ocr:LANG`: Tesseract language files, pinned and kept in pdfmd's own folder."""

from __future__ import annotations

import hashlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
from pdfmd_unicode import tessdata  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class TessdataCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)

    def pinned(self, payloads: dict[str, bytes]):
        """A catalog and an opener that serve `payloads` (code -> bytes)."""
        catalog = {code: (blob_sha1(data), len(data)) for code, data in payloads.items()}

        def opener(request, timeout=None):
            code = request.full_url.rsplit("/", 1)[1].removesuffix(".traineddata")
            return FakeResponse(payloads[code])
        return mock.patch.dict(tessdata.LANGUAGES, catalog, clear=True), opener

    def test_names_codes_and_aliases_resolve(self):
        self.assertEqual(tessdata.resolve(["ru", "Kazakh", "chi_sim", "rus"]), ["rus", "kaz", "chi_sim"])
        with self.assertRaises(tessdata.UnknownLanguage):
            tessdata.resolve(["klingon"])

    def test_install_adds_english_and_osd_and_checks_the_pin(self):
        payloads = {"rus": b"r" * 50, "eng": b"e" * 40, "osd": b"o" * 30}
        patch, opener = self.pinned(payloads)
        with patch:
            failed = tessdata.install(["rus"], self.root, log=lambda text: None, opener=opener)
            self.assertEqual(failed, [])
            self.assertEqual(tessdata.installed(self.root), ["eng", "osd", "rus"])
            self.assertTrue(tessdata.covers(self.root, ["rus", "eng"]))
            self.assertFalse(tessdata.covers(self.root, ["deu"]))
            tessdata.uninstall(["rus"], self.root, log=lambda text: None)
            self.assertEqual(tessdata.installed(self.root), ["eng", "osd"])

    def test_a_download_that_does_not_match_is_refused_and_leaves_nothing(self):
        patch, opener = self.pinned({"rus": b"r" * 50, "eng": b"e" * 40, "osd": b"o" * 30})
        with patch:
            def tampered(request, timeout=None):
                return FakeResponse(b"x" * 50)
            failed = tessdata.install(["rus"], self.root, log=lambda text: None, opener=tampered)
        self.assertIn("rus", failed)
        self.assertFalse((self.root / "rus.traineddata").exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_batchocr_gets_the_folder_only_when_it_has_every_language_asked_for(self):
        payloads = {"rus": b"r" * 50, "eng": b"e" * 40, "osd": b"o" * 30}
        patch, opener = self.pinned(payloads)
        with patch, mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root), "LOCALAPPDATA": str(self.root)}), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TESSDATA_PREFIX", None)
            tessdata.install(["rus"], pdfmd.tessdata_directory(), log=lambda text: None, opener=opener)
            env = pdfmd.tessdata_environment(["--lang", "eng+rus"])
            self.assertEqual(env["TESSDATA_PREFIX"], str(pdfmd.tessdata_directory()))
            self.assertIsNotNone(pdfmd.tessdata_environment(["--lang=rus"]))
            self.assertIsNone(pdfmd.tessdata_environment(["--lang", "deu"]))
            os.environ["TESSDATA_PREFIX"] = "/mine"
            self.assertIsNone(pdfmd.tessdata_environment(["--lang", "rus"]))

    def test_the_catalog_is_well_formed(self):
        for code, (sha1, size) in tessdata.LANGUAGES.items():
            self.assertRegex(sha1, r"^[0-9a-f]{40}$", code)
            self.assertGreater(size, 0)
        self.assertIn("eng", tessdata.LANGUAGES)
        self.assertIn("osd", tessdata.LANGUAGES)

    def test_install_kind_accepts_ocr_languages(self):
        self.assertEqual(pdfmd.install_kind("ocr:rus,kaz"), "ocr:rus,kaz")
        self.assertEqual(pdfmd.uninstall_kind("ocr:rus"), "ocr:rus")


if __name__ == "__main__":
    unittest.main()

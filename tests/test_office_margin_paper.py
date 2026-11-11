"""A margin-only Office override preserves the reference document's paper and orientation."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402,F401  (adds lib/ to sys.path for pdfmd_office)
from pdfmd_office import docx, patch_reference, spec_from_metadata  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"


def page(data, kind):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = ET.fromstring(archive.read("word/document.xml" if kind == "docx" else "styles.xml"))
    return xml.find(".//" + (W + "pgSz" if kind == "docx" else STYLE + "page-layout-properties")).attrib


def dimensions(data, kind):
    attributes = page(data, kind)
    keys = (W + "w", W + "h", W + "orient") if kind == "docx" else (FO + "page-width", FO + "page-height", STYLE + "print-orientation")
    return {key: attributes.get(key) for key in keys}


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class MarginPaper(unittest.TestCase):
    def references(self):
        return {"docx": docx.default_reference(), "odt": subprocess.run(
            ["pandoc", "--print-default-data-file", "reference.odt"], capture_output=True, check=True).stdout}

    def test_patch_preserves_a4_portrait_and_landscape_with_margin_only(self):
        for kind, reference in self.references().items():
            for landscape in (False, True):
                with self.subTest(kind=kind, landscape=landscape):
                    template = patch_reference(kind, reference, spec_from_metadata(
                        {"papersize": "a4", "classoption": ["landscape"] if landscape else []}), False)
                    patched = patch_reference(kind, template, spec_from_metadata({}, {"margin": "2cm"}), False)
                    self.assertEqual(dimensions(patched, kind), dimensions(template, kind))
                    with zipfile.ZipFile(io.BytesIO(patched)) as archive:
                        text = archive.read("word/document.xml" if kind == "docx" else "styles.xml").decode()
                    self.assertIn('w:top="1134"' if kind == "docx" else 'fo:margin-top="0.7875in"', text)
                    explicit = patch_reference(kind, template, spec_from_metadata({}, {"papersize": "legal", "margin": "2cm"}), False)
                    self.assertNotEqual(dimensions(explicit, kind), dimensions(template, kind))

    def test_checkout_margin_keeps_the_template_page(self):
        for kind, reference in self.references().items():
            for landscape in (False, True):
                with self.subTest(kind=kind, landscape=landscape), tempfile.TemporaryDirectory() as scratch:
                    folder = Path(scratch)
                    template = patch_reference(kind, reference, spec_from_metadata(
                        {"papersize": "a4", "classoption": ["landscape"] if landscape else []}), False)
                    (folder / f"reference.{kind}").write_bytes(template)
                    (folder / "document.md").write_text(
                        "---\npdfmd-options:\n  office: {margin: 2cm}\n---\n\nHello.\n", encoding="utf-8")
                    env = {**os.environ, "XDG_CONFIG_HOME": str(folder / "config"),
                           "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "data"),
                           "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
                    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "document.md",
                                           "-o", f"output.{kind}", "--no-stamp", "--no-backup"], cwd=folder, env=env,
                                          stdin=subprocess.DEVNULL, capture_output=True, text=True)
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(dimensions((folder / f"output.{kind}").read_bytes(), kind), dimensions(template, kind))

"""PDF rewrites preserve the types of the engine's document information."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd

try:
    import pypdf
    from pypdf.generic import NameObject, TextStringObject
except ImportError:
    pypdf = None


@unittest.skipUnless(pypdf, 'needs pypdf')
class InfoNames(unittest.TestCase):
    def rewrite(self, route, header=None, indirect=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'engine.pdf'
            writer = pypdf.PdfWriter()
            if header:
                writer.pdf_header = header
            writer.add_blank_page(200, 200)
            writer.add_metadata({'/Author': 'Unknown', '/Title': 'Original', '/Subject': '/False'})
            value = NameObject('/False')
            writer._info[NameObject('/Trapped')] = writer._add_object(value) if indirect else value
            writer.write(path)
            if route == 'stamp':
                with patch.object(pdfmd, 'stamp_summary', return_value='test stamp'):
                    pdfmd.stamp_pdf_metadata_posthoc(path, {**pdfmd.DEFAULT_STAMP_OPTIONS, 'pdf_metadata': True}, [], False)
                self.assertIn('/PdfmdVersions', pypdf.PdfReader(path).metadata)
            elif route == 'polish':
                with patch.object(pdfmd, 'POLISH_CLI', {'info': {'/Title': 'Changed'}}):
                    pdfmd.polish_pdf(path, [])
                self.assertEqual(pypdf.PdfReader(path).metadata.title, 'Changed')
            elif route == 'calibre':
                pdfmd.pdfmd_bridge.drop_calibre_author(path, False)
                self.assertNotIn('/Author', pypdf.PdfReader(path).metadata)
            elif route == 'attachments':
                pdfmd.write_pdf_attachments(path, {'note.txt': b'note'})
                self.assertIn('note.txt', pypdf.PdfReader(path).attachments)
            elif route == 'hybrid':
                self.assertTrue(pdfmd.attach_hybrid(path, b'ODF fixture', 'odt'))
                self.assertIn('Original.odt', pypdf.PdfReader(path).attachments)
            reader = pypdf.PdfReader(path)
            if header:
                self.assertEqual(reader.pdf_header, header)
            info = reader.metadata
            self.assertIsInstance(info['/Trapped'], NameObject)
            self.assertEqual(info['/Trapped'], '/False')
            self.assertIsInstance(info['/Subject'], TextStringObject)

    def test_stamp(self):
        self.rewrite('stamp')

    def test_polish(self):
        self.rewrite('polish')

    def test_calibre_author_removal(self):
        self.rewrite('calibre')

    def test_attachments(self):
        self.rewrite('attachments')

    def test_hybrid(self):
        self.rewrite('hybrid')

    def test_indirect_names(self):
        self.rewrite('calibre', indirect=True)

    def test_header_versions(self):
        for route in ('stamp', 'polish', 'calibre', 'attachments', 'hybrid'):
            with self.subTest(route=route):
                self.rewrite(route, header='%PDF-1.7')

    def test_older_pypdf_header_interfaces(self):
        from types import SimpleNamespace
        helper = pdfmd.load_package('pdfmd_polish.info')
        for writer in (SimpleNamespace(_header=b'%PDF-1.3'), SimpleNamespace()):
            with self.subTest(writer=writer), patch.object(pdfmd.pypdf, 'PdfWriter', return_value=writer):
                self.assertIs(helper.clone_pdf(SimpleNamespace(pdf_header='%PDF-1.7')), writer)
                if hasattr(writer, '_header'):
                    self.assertEqual(writer._header, b'%PDF-1.7')
                self.assertIs(helper.clone_pdf(SimpleNamespace()), writer)

    def test_stamp_and_polish_through_pdfmd(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'doc.md').write_text('# Document\n\nText.\n')
            env = {**os.environ, 'PDFMD_CONFIG': '', 'PDFMD_NO_PROMPT': '1',
                   **{'XDG_' + key + '_HOME': str(folder / key.lower()) for key in ('CONFIG', 'CACHE', 'DATA')}}
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), 'doc.md', '-e', 'inkmd',
                                   '--stamp', '--pdf-title', 'Rewritten', '--no-backup'], cwd=folder, env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            info = pypdf.PdfReader(folder / 'doc.pdf').metadata
            self.assertEqual(info.title, 'Rewritten')
            self.assertIn('/PdfmdVersions', info)

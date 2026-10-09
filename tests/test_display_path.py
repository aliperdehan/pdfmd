import os
import tempfile
import unittest
from pathlib import Path

import pdfmd


class DisplayPath(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()).resolve()
        self.outside = Path(tempfile.mkdtemp()).resolve()
        self.before = os.getcwd()
        os.chdir(self.folder)

    def tearDown(self):
        os.chdir(self.before)

    def test_a_file_under_the_working_folder_is_relative(self):
        (self.folder / "metadata").mkdir()
        (self.folder / "metadata" / "preamble.tex").write_text("x", encoding="utf-8")
        self.assertEqual(pdfmd.display_path(self.folder / "metadata" / "preamble.tex"),
                         os.path.join("metadata", "preamble.tex"))

    def test_a_symlink_is_shown_where_it_sits_not_where_it_leads(self):
        target = self.outside / "genchem-metadata.yaml"
        target.write_text("x", encoding="utf-8")
        (self.folder / "metadata").mkdir()
        link = self.folder / "metadata" / "metadata.yaml"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available")
        self.assertEqual(pdfmd.display_path(link), os.path.join("metadata", "metadata.yaml"))

    def test_a_working_folder_spelled_another_way_still_gives_a_relative_path(self):
        # Windows: the working folder in 8.3 short form (RUNNER~1) while the file's folder resolves to the long one.
        # A symlink to the folder is the same mismatch, which a Unix machine can make.
        (self.folder / "doc.md").write_text("x", encoding="utf-8")
        link = self.outside / "alias"
        try:
            link.symlink_to(self.folder, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available")
        original = pdfmd.Path.cwd
        pdfmd.Path.cwd = classmethod(lambda cls: link)
        try:
            self.assertEqual(pdfmd.display_path(self.folder / "doc.md"), "doc.md")
        finally:
            pdfmd.Path.cwd = original

    def test_a_file_elsewhere_stays_absolute(self):
        other = self.outside / "a.md"
        other.write_text("x", encoding="utf-8")
        self.assertEqual(pdfmd.display_path(other), str(other))


if __name__ == "__main__":
    unittest.main()

"""LibreOffice's throwaway profile is named by a real file URL (file:///C:/...); file://C:\... makes it fail on Windows."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_images import svg  # noqa: E402


class SofficeProfile(unittest.TestCase):
    def test_the_profile_is_a_file_url(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            seen = []

            def run(command, **_):
                seen.append(command)
                return mock.Mock(stdout="", stderr="")

            with mock.patch("pdfmd_images.svg.subprocess.run", run):
                svg._run("soffice", scratch / "a.svg", scratch / "out.pdf", scratch, lambda name: None, lambda: "soffice")
            [option] = [part for part in seen[0] if part.startswith("-env:UserInstallation=")]
            self.assertEqual(option, "-env:UserInstallation=" + (scratch / "profile").as_uri())
            self.assertTrue(option.startswith("-env:UserInstallation=file:///"), option)


if __name__ == "__main__":
    unittest.main()

"""Tools that a Windows installer leaves off PATH (Tesseract, LibreOffice, Graphviz, Mermaid, Poppler): found by the config's
`options.<tool>-path`, else PATH, else the usual install folders, and used all the same. A fake Program Files tree built in a
temporary folder stands for the installs, with `sys.platform` set to win32, so the tests run the same on every system."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class ToolLocations(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.config: dict = {}
        environment = {"ProgramFiles": str(self.root / "pf"), "ProgramW6432": str(self.root / "pf64"),
                       "ProgramFiles(x86)": str(self.root / "pf86"), "LOCALAPPDATA": str(self.root / "local"),
                       "APPDATA": str(self.root / "roaming"), "PDFMD_NO_APP_PATHS": "1", "PATH": str(self.root / "bin")}
        for patcher in (mock.patch.dict(os.environ, environment), mock.patch.object(pdfmd.sys, "platform", "win32"),
                        mock.patch.object(pdfmd, "which", lambda name: self.on_path.get(name)),
                        mock.patch.object(pdfmd, "config_options", lambda *args: self.config),
                        mock.patch.dict(pdfmd.TOOLS_FOUND, clear=True), mock.patch.object(pdfmd, "TOOL_WARNED", set())):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.on_path: dict[str, str] = {}

    def make(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def test_each_tool_is_found_in_its_install_folder(self):
        wanted = {"tesseract": self.make("pf", "Tesseract-OCR", "tesseract.exe"),
                  "soffice": self.make("pf86", "LibreOffice", "program", "soffice.exe"),
                  "dot": self.make("local", "Programs", "Graphviz", "bin", "dot.exe"),
                  "poppler": self.make("pf64", "poppler-24.08.0", "Library", "bin", "pdftotext.exe"),
                  "mmdc": self.make("roaming", "npm", "mmdc.cmd")}
        for name, file in wanted.items():
            self.assertEqual(pdfmd.locate_tool(name), (str(file), "probe"), name)
        self.assertEqual(pdfmd.resolve_soffice(), str(wanted["soffice"]))

    def test_pandoc_typst_and_chrome_are_found_in_their_install_folders(self):
        wanted = {"pandoc": self.make("local", "Pandoc", "pandoc.exe"),
                  "typst": self.make("local", "Microsoft", "WinGet", "Packages", "Typst.Typst_x", "typst-x86_64-pc-windows-msvc",
                                     "typst.exe"),
                  "chrome": self.make("pf86", "Google", "Chrome", "Application", "chrome.exe")}
        for name, file in wanted.items():
            self.assertEqual(pdfmd.locate_tool(name), (str(file), "probe"), name)
        self.make("local", "Microsoft", "WinGet", "Links", "typst.exe")
        self.assertEqual(pdfmd.locate_tool("typst")[1], "probe")

    def test_a_named_chrome_is_the_browser_the_engines_use(self):
        chrome = self.make("mine", "chrome.exe")
        self.config = {"chrome-path": str(chrome.parent)}
        pdfmd.use_found_tools()
        self.assertEqual(os.environ["PDFMD_BROWSER"], str(chrome))
        self.assertNotIn(str(chrome.parent), os.environ["PATH"].split(os.pathsep))      # a browser's folder is not for PATH

    def test_a_tool_on_path_is_used_before_a_folder(self):
        self.make("pf", "Graphviz", "bin", "dot.exe")
        self.on_path["dot"] = "elsewhere/dot"
        self.assertEqual(pdfmd.locate_tool("dot"), ("elsewhere/dot", "path"))

    def test_the_config_comes_before_path_and_takes_a_file_or_a_folder(self):
        file = self.make("mine", "bin", "dot.exe")
        self.on_path["dot"] = "elsewhere/dot"
        self.config = {"dot-path": str(file)}
        self.assertEqual(pdfmd.locate_tool("dot"), (str(file), "key"))
        self.config = {"dot-path": str(file.parent)}
        self.assertEqual(pdfmd.locate_tool("dot"), (str(file), "key"))

    def test_poppler_is_named_by_its_folder_only(self):
        file = self.make("mine", "poppler", "pdftotext.exe")
        self.config = {"poppler-path": str(file.parent)}
        self.assertEqual(pdfmd.locate_tool("poppler"), (str(file), "key"))
        self.config = {"poppler-path": str(file)}
        with redirect_stderr(io.StringIO()):
            self.assertEqual(pdfmd.locate_tool("poppler"), (None, ""))

    def test_a_stale_path_is_said_once_and_passed_over(self):
        self.config = {"tesseract-path": str(self.root / "gone")}
        self.on_path["tesseract"] = "elsewhere/tesseract"
        shown = io.StringIO()
        with redirect_stderr(shown):
            self.assertEqual(pdfmd.locate_tool("tesseract"), ("elsewhere/tesseract", "path"))
            pdfmd.locate_tool("tesseract")
        self.assertEqual(shown.getvalue().count("WARN  config: options.tesseract-path"), 1, shown.getvalue())

    def test_nothing_is_probed_off_windows(self):
        self.make("pf", "Tesseract-OCR", "tesseract.exe")
        with mock.patch.object(pdfmd.sys, "platform", "linux"):
            self.assertEqual(pdfmd.locate_tool("tesseract"), (None, ""))

    def test_the_registry_probe_can_be_switched_off(self):
        with mock.patch.dict(os.environ, {"PDFMD_NO_APP_PATHS": "1"}):
            self.assertIsNone(pdfmd.app_path_file("soffice"))

    def test_a_found_folder_goes_on_path_behind_a_probe_and_in_front_of_a_key(self):
        probed = self.make("pf", "Tesseract-OCR", "tesseract.exe")
        named = self.make("mine", "dot.exe")
        soffice = self.make("pf", "LibreOffice", "program", "soffice.exe")
        self.config = {"dot-path": str(named.parent)}
        pdfmd.use_found_tools()
        entries = os.environ["PATH"].split(os.pathsep)
        self.assertEqual(entries[0], str(named.parent))
        self.assertEqual(entries[-1], str(probed.parent))
        self.assertNotIn(str(soffice.parent), entries)         # LibreOffice's folder has a python.exe and DLLs of its own
        self.assertEqual(pdfmd.TOOLS_FOUND["soffice"], (str(soffice), "probe"))

    def test_the_doctor_says_where_a_tool_was_found(self):
        probed = self.make("pf", "Tesseract-OCR", "tesseract.exe")
        self.config = {"dot-path": str(self.make("mine", "dot.exe").parent)}
        pdfmd.use_found_tools()          # the folders are on PATH now: the notes still say how they were found
        self.assertEqual(pdfmd.tool_note("tesseract"),
                         f"found at {probed.parent}, not on PATH (pdfmd uses it anyway)")
        self.assertEqual(pdfmd.tool_note("dot"), "set by options.dot-path")
        self.assertEqual(pdfmd.tool_note("d2"), "")


if __name__ == "__main__":
    unittest.main()

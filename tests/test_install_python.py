"""v3.28.26: `pdfmd --install` falls back to pdfmd's own Python folder when the Python is managed by the system (PEP 668), and
the doctor says a romanization pack that is installed is ready."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

MANAGED = "error: externally-managed-environment\n\n× This environment is externally managed\n"


class Folder(unittest.TestCase):
    def test_one_folder_per_python_version_beside_the_tools(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"XDG_DATA_HOME": home}):
            if sys.platform == "win32":
                self.skipTest("uses XDG_DATA_HOME")
            self.assertEqual(pdfmd.own_python_folder(),
                             Path(home) / "pdfmd" / "python" / f"{sys.version_info[0]}.{sys.version_info[1]}")

    def test_the_folder_is_on_the_path_at_start_up_and_behind_the_pythons_own(self):
        if sys.platform == "win32":
            self.skipTest("uses XDG_DATA_HOME")
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home) / "pdfmd" / "python" / f"{sys.version_info[0]}.{sys.version_info[1]}"
            folder.mkdir(parents=True)
            code = ("import sys; sys.path.insert(0, %r); import pdfmd; "
                    "print(sys.path.index(%r) > len(sys.path) - 3 if %r in sys.path else 'absent')"
                    % (str(ROOT), str(folder), str(folder)))
            done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                  env={**os.environ, "XDG_DATA_HOME": home, "PDFMD_CONFIG": ""})
            self.assertEqual(done.stdout.strip(), "True", done.stdout + done.stderr)


class Install(unittest.TestCase):
    def run_install(self, results):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"XDG_DATA_HOME": home}), \
                mock.patch.object(pdfmd.subprocess, "run", side_effect=results) as runner, \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            before = list(sys.path)
            try:
                ok = pdfmd.install_extra("tui")
            finally:
                sys.path[:] = before
            return ok, runner.call_args_list, out.getvalue(), Path(home)

    def test_a_system_managed_python_gets_the_packages_in_pdfmds_folder(self):
        if sys.platform == "win32":
            self.skipTest("uses XDG_DATA_HOME")
        ok, calls, out, home = self.run_install([subprocess.CompletedProcess([], 1, stderr=MANAGED),
                                                 subprocess.CompletedProcess([], 0)])
        self.assertTrue(ok)
        self.assertEqual(len(calls), 2)
        second = calls[1].args[0]
        self.assertIn("--target", second)
        self.assertEqual(Path(second[second.index("--target") + 1]).parent.parent, home / "pdfmd")
        self.assertIn("--upgrade", second)
        self.assertIn("PEP 668", out)

    def test_an_ordinary_python_is_installed_into_as_before(self):
        ok, calls, out, _ = self.run_install([subprocess.CompletedProcess([], 0, stderr="")])
        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--target", calls[0].args[0])

    def test_another_failure_is_not_retried(self):
        ok, calls, _, _ = self.run_install([subprocess.CompletedProcess([], 1, stderr="ERROR: no network")])
        self.assertFalse(ok)
        self.assertEqual(len(calls), 1)


class MathLauncher(unittest.TestCase):
    @unittest.skipIf(sys.version_info < (3, 11), "pymd2pdf needs Python 3.11")
    def test_math_install_restores_pdfmd_launchers_even_when_pip_fails(self):
        # RECORD includes the launcher outside site-packages; Windows wheels use
        # an exe, older installers can also leave an md2pdf-script.py companion.
        import importlib.metadata
        for status in (0, 1):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                names = ('md2pdf', 'md2pdf.exe', 'md2pdf-script.py')
                originals = {}
                for name in names:
                    target = root / name
                    data = b'#!/usr/bin/env python3\nfrom pdfmd import md2pdf_main\n' if name != 'md2pdf.exe' else b'MZ\x00pdfmd launcher'
                    target.write_bytes(data)
                    target.chmod(0o751)
                    originals[target] = (data, target.stat().st_mode)
                other = root / 'other'
                other.write_bytes(b'unrelated')
                dist = mock.Mock(files=[Path('../bin') / name for name in (*names, 'other')])
                dist.locate_file.side_effect = lambda file: root / file.name

                def pip(command, **kwargs):
                    self.assertIn('pymd2pdf>=0.6,<0.7', command)
                    for target in originals:
                        target.write_bytes(b'competing pymd2pdf launcher')
                        target.chmod(0o644)
                    return subprocess.CompletedProcess(command, status, stderr='')

                with mock.patch.object(importlib.metadata, 'distribution', return_value=dist), \
                        mock.patch.object(pdfmd.subprocess, 'run', side_effect=pip) as installer, \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(pdfmd.install_extra('math'), status == 0)
                installer.assert_called_once()
                for target, (data, mode) in originals.items():
                    self.assertEqual(target.read_bytes(), data)
                    self.assertEqual(target.stat().st_mode, mode)
                self.assertEqual(other.read_bytes(), b'unrelated')

    def test_a_checkout_without_distribution_records_does_not_guess_a_scripts_folder(self):
        import importlib.metadata
        with mock.patch.object(importlib.metadata, 'distribution', side_effect=importlib.metadata.PackageNotFoundError), \
                mock.patch.object(pdfmd.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stderr='')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(pdfmd.install_extra('math'))


class Doctor(unittest.TestCase):
    def test_packs_that_are_installed_are_said_to_be_ready(self):
        module = pdfmd.unicode_module()
        if module is None:
            self.skipTest("needs pdfmd_unicode")
        out = io.StringIO()
        with mock.patch.object(module.translit, "available", return_value=True), contextlib.redirect_stdout(out):
            pdfmd.doctor_report()
        line = next(item for item in out.getvalue().splitlines() if "name lookup in other scripts" in item)
        self.assertIn("ready, off until you turn them on: --translit all", line)
        self.assertNotIn("pdfmd --install translit", line)


if __name__ == "__main__":
    unittest.main()

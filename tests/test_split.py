"""v3.33.5: the split's deferred re-exports (SPLIT.md, step 6). A package that pdfmd.py does not load at start is reached
through a stand-in (`deferred`) or `DEFERRED_NAMES`; it loads on first use and gets pdfmd as its `core`."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

PACKAGE = "pdfmd_split_probe"


class Deferred(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        package = Path(folder.name) / PACKAGE
        package.mkdir()
        (package / "__init__.py").write_text("LOADED_INIT = True\n", encoding="utf-8")
        (package / "role.py").write_text(textwrap.dedent("""\
            core = None
            TABLE = {"a": 1}

            def where(value):
                return core, value
        """), encoding="utf-8")
        sys.path.insert(0, folder.name)
        self.addCleanup(sys.path.remove, folder.name)
        self.addCleanup(self.forget)
        self.addCleanup(pdfmd.DEFERRED_NAMES.pop, "TABLE", None)

    def forget(self):
        for name in (f"{PACKAGE}.role", PACKAGE):
            sys.modules.pop(name, None)

    def test_the_stand_in_loads_on_the_first_call_and_binds_core(self):
        stand_in = pdfmd.deferred(f"{PACKAGE}.role", "where")
        self.assertNotIn(f"{PACKAGE}.role", sys.modules)
        self.assertEqual(stand_in.__name__, "where")
        self.assertEqual(stand_in(7), (pdfmd, 7))
        self.assertIs(sys.modules[f"{PACKAGE}.role"].core, pdfmd)

    def test_a_deferred_name_is_the_package_s_own_object(self):
        pdfmd.DEFERRED_NAMES["TABLE"] = f"{PACKAGE}.role"
        self.assertIs(pdfmd.TABLE, sys.modules[f"{PACKAGE}.role"].TABLE)

    def test_an_unknown_name_is_still_an_attribute_error(self):
        self.assertFalse(hasattr(pdfmd, "no_such_name_anywhere"))


class Start(unittest.TestCase):
    def test_the_heavy_packages_do_not_load_at_start(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import pdfmd; "
                "print(' '.join(name for name in ('pdfmd_serve', 'pdfmd_office', 'http.server', 'ssl') if name in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()

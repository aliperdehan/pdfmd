"""v3.33.187j: the tools of the split (SPLIT.md), on synthetic sources, so they do not depend on what pdfmd.py holds today.

`scripts/split_spec.py` finds a move's section by its key under SPLIT.md's `## Phase 2:` heading (phase 1's sections share
six keys with phase 2's) and reports what the move needs: what runs when a module loads, cached functions, test patches of
every kind, pdfmd.py's own `__file__`, the state the moved code writes."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import split_spec  # noqa: E402

SPLIT = textwrap.dedent("""\
    # Splitting pdfmd.py

    ## Phase 1: the packages, in order

    #### 23. `pdfmd_routing` (new package): 2 definitions; done in 3.33.25

    Definitions: `old_one`, `old_two`.

    Tests: `test_old`.

    ## Phase 2: the moves, in order

    ### Wave 3

    #### 29. `pdfmd_routing` (existing package): 1 definitions, 1 constants, ~91 lines

    Definitions: `new_one`.

    Constants that move with it: `NEW_CONSTANT`.

    Tests: `test_new`, `test_other`.

    #### 30. `pdfmd_tex.inputs` (existing package): 1 definitions, 0 constants, ~10 lines

    Definitions: `dotted_one`.

    ## Numbers

    #### 99. `pdfmd_tex` (a heading outside both phases)

    Definitions: `elsewhere`.
""")


class SectionLookup(unittest.TestCase):
    def test_phase_2_is_the_default_and_phase_1_is_asked_for(self):
        self.assertEqual(split_spec.section("pdfmd_routing", SPLIT), (["new_one"], ["NEW_CONSTANT"], ["test_new", "test_other"]))
        self.assertEqual(split_spec.section("pdfmd_routing", SPLIT, phase=1), (["old_one", "old_two"], [], ["test_old"]))

    def test_a_dotted_key_is_its_own_section(self):
        self.assertEqual(split_spec.section("pdfmd_tex.inputs", SPLIT)[0], ["dotted_one"])
        with self.assertRaises(SystemExit):                      # `pdfmd_tex` alone is outside the phase-2 part
            split_spec.section("pdfmd_tex", SPLIT)

    def test_without_a_phase_2_heading_the_whole_text_is_read(self):
        whole = SPLIT.replace("## Phase 2: the moves, in order", "## Later moves")
        with self.assertRaises(SystemExit):                      # two `pdfmd_routing` sections: refused, not guessed
            split_spec.section("pdfmd_routing", whole)
        self.assertEqual(split_spec.section("pdfmd_tex", whole)[0], ["elsewhere"])
        with self.assertRaises(SystemExit):                      # an explicit phase never falls back to the whole text
            split_spec.section("pdfmd_tex", whole, phase=2)

    def test_two_sections_of_one_key_in_one_phase_are_refused(self):
        twice = SPLIT.replace("#### 30. `pdfmd_tex.inputs`", "#### 30. `pdfmd_routing`")
        with self.assertRaises(SystemExit):
            split_spec.section("pdfmd_routing", twice)


PDFMD = textwrap.dedent('''\
    from __future__ import annotations
    import functools
    import os
    from pathlib import Path

    BUILD = {}
    FLAG_CLI = None
    LIMIT = 3
    TWICE = LIMIT * 2


    def timed(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            BUILD["calls"] = BUILD.get("calls", 0) + 1
            return function(*args, **kwargs)
        return wrapper


    @timed
    def stays():
        return helper(1)


    def helper(value, default=TWICE, separator=os.sep):
        global FLAG_CLI
        FLAG_CLI = value
        return Path(__file__).parent, default, separator


    @functools.lru_cache(maxsize=None)
    def cached():
        return 1


    if helper:
        pass
''')

PROBE_SPLIT = textwrap.dedent("""\
    ## Phase 2: the moves

    #### 1. `pdfmd_probe` (new package): 3 definitions, 1 constants, ~30 lines

    Definitions: `timed`, `helper`, `cached`.

    Constants that move with it: `LIMIT`.

    Tests: `test_probe`.
""")

PROBE_TEST = textwrap.dedent("""\
    from unittest import mock
    import pdfmd

    def test_it():
        with mock.patch.object(pdfmd, "helper"), mock.patch.dict(pdfmd.BUILD, {}), mock.patch.dict(pdfmd.os.environ, {}):
            pdfmd.cached.cache_clear()
        pdfmd.FLAG_CLI = 2
""")


class Report(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "pdfmd.py").write_text(PDFMD, encoding="utf-8")
        (self.root / "SPLIT.md").write_text(PROBE_SPLIT, encoding="utf-8")
        (self.root / "lib").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_probe.py").write_text(PROBE_TEST, encoding="utf-8")

    def report(self) -> dict[str, str]:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "split_spec.py"), "pdfmd_probe", "--root", str(self.root)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        parts = {}
        for block in done.stdout.split("\n## ")[1:]:
            title, _, body = block.partition("\n")
            parts[title] = body
        return parts

    def test_what_the_move_needs(self):
        parts = self.report()
        self.assertIn("lib/pdfmd_probe/__init__.py (a new package", parts["Where the code goes"])
        self.assertIn("- BUILD", parts["Read as core.NAME (pdfmd names that stay)"])
        self.assertIn("- FLAG_CLI", next(body for title, body in parts.items() if title.startswith("Written by the moved code")))
        self.assertIn("- os\n", parts["Imported by the package itself"] + "\n")
        eager = parts["Read when a module loads (core cannot serve these)"]
        self.assertIn("TWICE (STAYS", eager)                                   # helper's default argument
        self.assertNotIn("os", eager)                                          # a module the package imports itself
        staying = next(body for title, body in parts.items() if title.startswith("Moved names that code staying"))
        self.assertIn("(stays): timed", staying)                               # a decorator of code that stays
        self.assertIn("(TWICE): LIMIT", staying)                               # a constant built from a moved one
        self.assertIn("(If): helper", next(body for title, body in parts.items() if title.startswith("Module-level statements")))
        cached = next(body for title, body in parts.items() if title.startswith("Cached functions"))
        self.assertIn("cached (cached): tests/test_probe.py:6", cached)
        self.assertIn("helper: __file__", next(body for title, body in parts.items() if title.startswith("pdfmd.py itself")))
        patched = parts["Patched or set by tests"]
        self.assertIn("helper (moved): test_probe.py:5 patch.object", patched)
        self.assertIn("BUILD (used by the moved code: always as core.BUILD): test_probe.py:5 patch.dict", patched)
        self.assertIn("FLAG_CLI (used by the moved code", patched)
        self.assertNotIn("- os ", patched)                                     # pdfmd.os.environ is os's own dictionary
        self.assertIn("test_probe test_packaging", parts["Tests to run (from tests/)"])
        self.assertIn("test_split", parts["Tests to run (from tests/)"])


if __name__ == "__main__":
    unittest.main()

"""v3.33.187j, v3.33.187k: the tools of the split (SPLIT.md), on synthetic sources, so they do not depend on what pdfmd.py holds.

`scripts/split_spec.py` finds a move's section by its key under SPLIT.md's `## Phase 2:` heading (phase 1's sections share
six keys with phase 2's) and reports what the move needs: what runs when a module loads, cached functions, test patches of
every kind, pdfmd.py's own `__file__`, the state the moved code writes."""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
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


class StateGuard(unittest.TestCase):
    def test_moved_last_writer_still_protects_state(self):
        from tests import test_split
        tree = ast.parse((ROOT / "pdfmd.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                node.names = [name for name in node.names if name != "SOFFICE_TIMEOUT_NOW"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "writer.py"
            path.write_text("def correct():\n    core.SOFFICE_TIMEOUT_NOW = 0\n"
                            "def moved():\n    global SOFFICE_TIMEOUT_NOW\n    SOFFICE_TIMEOUT_NOW = 0\n")
            guard = test_split.SafetyNet("test_no_code_in_lib_binds_a_bare_state_name")
            guard.tree = tree
            with unittest.mock.patch.object(test_split, "lib_sources", return_value=[path]), \
                 unittest.mock.patch.object(test_split, "ROOT", Path(folder)):
                with self.assertRaisesRegex(AssertionError, "SOFFICE_TIMEOUT_NOW"):
                    guard.test_no_code_in_lib_binds_a_bare_state_name()


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


MOVER_PDFMD = textwrap.dedent('''\
    """A synthetic pdfmd.py."""
    from __future__ import annotations

    import os
    import sys
    from pathlib import Path
    from shutil import which

    from pdfmd_other import imported_helper

    COUNT = 0
    LAST = None
    STATE = None
    LIMIT = 5


    def display_path(path):
        return str(path)


    def weight(item):
        return len(item)


    def deferred(module, name):
        return None


    DEFERRED_NAMES = {}
    DEFERRED_NAMES.update(OLD="pdfmd_old")


    def names(module, listed):
        pass


    names("pdfmd_older", "earlier_moved")


    # The comment block right above a moved function moves with it.
    def counter(paths, items):
        global COUNT, LAST
        COUNT += 1
        for LAST in items:
            pass
        label = "путь: " + display_path(paths[0])
        note = f"«{display_path(paths[-1])}» — {weight(label)}"
        ordered = sorted(items, key=lambda item: weight(item))
        shadowed = [display_path for display_path in items]
        keyed = sorted(items, key=lambda weight: weight)
        return (label, note, ordered, shadowed, keyed, os.sep, Path(__file__), sys.modules[__name__], which("x"),
                earlier_moved())


    def outer():
        def inner():
            global STATE
            STATE = 1
            del STATE
        total = 0

        def bump():
            nonlocal total
            total += LIMIT
        return inner, bump, imported_helper()


    class Holder:
        def method(self):
            return display_path(self) + patched_helper()


    def patched_helper():
        return "real"


    def caller():
        return patched_helper()


    def stays():
        return counter([], [])
''')

MOVER_TEST = textwrap.dedent("""\
    from unittest import mock
    import pdfmd

    def test_it():
        with mock.patch.object(pdfmd, "patched_helper"), mock.patch.object(pdfmd, "which"):
            pdfmd.caller()
""")


def mover_tree(root: Path, pdfmd: str, definitions: str, test: str = MOVER_TEST) -> None:
    (root / "pdfmd.py").write_text(pdfmd, encoding="utf-8")
    (root / "SPLIT.md").write_text(f"## Phase 2: the moves\n\n#### 1. `pdfmd_probe` (new package)\n\nDefinitions: {definitions}.\n\n"
                                   "Tests: `test_probe`.\n", encoding="utf-8")
    (root / "lib").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_probe.py").write_text(test, encoding="utf-8")


@unittest.skipUnless(sys.version_info >= (3, 12), "scripts/split_move.py needs Python 3.12 (names inside f-strings)")
class Mover(unittest.TestCase):
    """v3.33.187k: `scripts/split_move.py` moves a section by itself and refuses what needs a decision."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def move(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "split_move.py"), "pdfmd_probe", "--root", str(self.root),
                               *extra], capture_output=True, text=True, encoding="utf-8")

    def test_conditional_redefinitions_and_deletions_are_refused(self):
        for tail in ("if True:\n    def f():\n        return 2\n", "del f\n"):
            with self.subTest(tail=tail):
                self.root = Path(tempfile.mkdtemp(dir=self.root))
                code = "def f():\n    return 1\n" + tail
                mover_tree(self.root, code, "`f`", test="")
                done = self.move()
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn("f:", done.stdout)
                self.assertEqual((self.root / "pdfmd.py").read_text(), code)
                self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_rebound_export_is_refused(self):
        code = "def names(*args):\n    pass\nnames('other', 'x')\ndef f():\n    global f\n    f = lambda: 2\n    return 1\n"
        mover_tree(self.root, code, "`f`", test="import pdfmd\nx = pdfmd.f\n")
        done = self.move()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("f: moved code rebinds", done.stdout)
        self.assertEqual((self.root / "pdfmd.py").read_text(), code)
        self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_global_definition_and_mapping_bindings_are_refused(self):
        for binding in ("    def STATE():\n        return 3\n", "    class STATE:\n        pass\n",
                        "    match {}:\n        case {**STATE}:\n            pass\n"):
            with self.subTest(binding=binding):
                self.root = Path(tempfile.mkdtemp(dir=self.root))
                code = "STATE = None\ndef f():\n    global STATE\n" + binding + "    return STATE()\n"
                mover_tree(self.root, code, "`f`", test="")
                done = self.move()
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn("binds the state STATE", done.stdout)
                self.assertEqual((self.root / "pdfmd.py").read_text(), code)
                self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_class_read_before_assignment_is_refused(self):
        code = "LIMIT = 5\ndef f():\n    class C:\n        LIMIT = LIMIT\n    return C.LIMIT\n"
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("f: ambiguous class-body read of LIMIT", done.stdout)
        self.assertEqual((self.root / "pdfmd.py").read_text(), code)
        self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_overwritten_import_is_read_through_core(self):
        code = "from os import sep\nsep = 'custom'\ndef f():\n    return sep\n"
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        module = (self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text()
        self.assertIn("return core.sep", module)
        self.assertNotIn("from os import sep", module)
        from types import SimpleNamespace
        namespace = {}
        exec(module.replace("from pdfmd_base import core", ""), {"core": SimpleNamespace(sep="custom")}, namespace)
        self.assertEqual(namespace["f"](), "custom")

    def test_incompatible_destination_dependency_is_refused(self):
        code = "from pathlib import Path\ndef f():\n    return Path('x')\n"
        mover_tree(self.root, code, "`f`", test="")
        package = self.root / "lib" / "pdfmd_probe"
        package.mkdir()
        target = package / "__init__.py"
        original = "Path = lambda value: 'wrong'\n"
        target.write_text(original)
        done = self.move()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("incompatible dependency binding Path", done.stdout)
        self.assertEqual(target.read_text(), original)
        self.assertEqual((self.root / "pdfmd.py").read_text(), code)

    def test_cached_function_attributes_require_real_binding(self):
        code = ("def names(*args):\n    pass\nnames('other', 'x')\n"
                "from functools import lru_cache\n@lru_cache(maxsize=None)\ndef f():\n    return 3\n"
                "def stays():\n    f.cache_clear()\n    return f.cache_info()\n")
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("f: staying code needs the real object", done.stdout)
        self.assertEqual((self.root / "pdfmd.py").read_text(), code)
        self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())
        done = self.move("--import-at-start")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        namespace = {}
        exec((self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text(), namespace)
        self.assertEqual(namespace["f"](), 3)
        namespace["f"].cache_clear()
        self.assertEqual(namespace["f"].cache_info().currsize, 0)
        self.assertIn("from pdfmd_probe import f", (self.root / "pdfmd.py").read_text())

    def test_patch_only_users_receive_exports(self):
        code = "def names(*args):\n    pass\nnames('other', 'x')\ndef f():\n    return 1\n"
        mover_tree(self.root, code, "`f`", test="from unittest.mock import patch\nimport pdfmd\nwith patch.object(pdfmd, 'f'):\n    pass\n")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('names("pdfmd_probe", "f")', (self.root / "pdfmd.py").read_text())

    def test_conditional_scope_locals_are_not_module_names(self):
        code = ("if True:\n    def local():\n        list = 3\n    class C:\n        dict = 4\n"
                "    value = lambda: (tuple := 1)\n    values = [set for set in []]\n"
                "def f():\n    return list(), dict(), tuple(), set()\n")
        bound = set(split_spec.nested_bindings(ast.parse(code).body[0]))
        self.assertEqual(bound, {"local", "C", "value", "values"})
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        module = (self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text()
        self.assertNotIn("from pdfmd_base import core", module)
        namespace = {}
        exec(module, namespace)
        self.assertEqual(namespace["f"](), ([], {}, (), set()))

    def test_module_self_expression_respects_parameters(self):
        code = "def f(sys, __name__):\n    return sys.modules[__name__]\n"
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        module = (self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text()
        self.assertIn("return sys.modules[__name__]", module)
        from types import SimpleNamespace
        value = object()
        namespace = {}
        exec(module, namespace)
        self.assertIs(namespace["f"](SimpleNamespace(modules={"custom": value}), "custom"), value)

    def test_comprehension_attribute_target_owner_stays_global(self):
        code = "BOX = None\ndef f():\n    return [BOX.value for BOX.value in [1, 2]]\n"
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        module = (self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text()
        self.assertIn("[core.BOX.value for core.BOX.value in [1, 2]]", module)
        from types import SimpleNamespace
        namespace = {"core": SimpleNamespace(BOX=SimpleNamespace())}
        exec(module.replace("from pdfmd_base import core", ""), namespace)
        self.assertEqual(namespace["f"](), [1, 2])

    def test_quoted_annotations_are_refused(self):
        code = 'from pathlib import Path\ndef f(x: "Path"):\n    return x\n'
        mover_tree(self.root, code, "`f`", test="")
        done = self.move()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("f: quoted annotation 'Path'", done.stdout)
        self.assertEqual((self.root / "pdfmd.py").read_text(), code)
        self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_a_move(self):
        mover_tree(self.root, MOVER_PDFMD, "`counter`, `outer`, `Holder`, `patched_helper`, `caller`")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("comments carried (check they belong to the definition): counter: 1 comment lines", done.stdout)
        module = (self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text(encoding="utf-8")
        pdfmd = (self.root / "pdfmd.py").read_text(encoding="utf-8")
        ast.parse(module)
        ast.parse(pdfmd)
        for expected in (
            "import os\n", "from pathlib import Path\n", "from pdfmd_base import core\n",
            "# The comment block right above a moved function moves with it.\ndef counter(paths, items):\n",
            "    core.COUNT += 1\n", "    for core.LAST in items:\n",
            'label = "путь: " + core.display_path(paths[0])',                       # columns are UTF-8 bytes
            'note = f"«{core.display_path(paths[-1])}» — {core.weight(label)}"',
            "key=lambda item: core.weight(item))", "[display_path for display_path in items]", "key=lambda weight: weight)",
            "Path(core.__file__), core, core.which(\"x\"),", "core.earlier_moved())",
            "        core.STATE = 1\n        del core.STATE\n", "        nonlocal total\n        total += core.LIMIT\n",
            "core.imported_helper()", "return core.display_path(self) + core.patched_helper()",
            "def caller():\n    return core.patched_helper()",
        ):
            self.assertIn(expected, module)
        self.assertNotIn("global", module)
        self.assertNotIn("import sys", module)                     # sys was read only as sys.modules[__name__]
        self.assertNotIn("import which", module)                   # tests patch pdfmd.which: core.which
        self.assertNotIn("def counter", pdfmd)
        self.assertNotIn("The comment block right above", pdfmd)
        self.assertIn('names("pdfmd_older", "earlier_moved")\nnames("pdfmd_probe", "patched_helper caller")\n'
                      'counter = deferred("pdfmd_probe", "counter")\n', pdfmd)
        self.assertIn('LIMIT = 5\n\n\ndef display_path', pdfmd)
        self.assertIn('names("pdfmd_older", "earlier_moved")\n', pdfmd)
        self.assertNotIn("\n\n\n\n", pdfmd)                       # two blank lines where the blocks left, never more

    def test_an_existing_module_is_appended_to(self):
        mover_tree(self.root, MOVER_PDFMD, "`counter`, `patched_helper`")
        package = self.root / "lib" / "pdfmd_probe"
        package.mkdir()
        (package / "__init__.py").write_text('"""Already here."""\nfrom __future__ import annotations\n\nimport re\n\n\n'
                                             'def present():\n    return re\n', encoding="utf-8")
        done = self.move()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        module = (package / "__init__.py").read_text(encoding="utf-8")
        self.assertTrue(module.startswith('"""Already here."""\nfrom __future__ import annotations\n\nimport re\n'
                                          'from pathlib import Path\nimport os\nfrom pdfmd_base import core\n\n\ndef present():'),
                        module)
        self.assertIn("    return re\n\n\n# The comment block right above", module)
        (package / "__init__.py").write_text("def caller():\n    pass\n", encoding="utf-8")
        mover_tree(self.root, MOVER_PDFMD, "`caller`")
        done = self.move()
        self.assertEqual(done.returncode, 2)
        self.assertIn("already binds caller", done.stdout)

    def test_what_staying_code_needs_at_start_can_be_imported_plainly(self):
        code = ("from __future__ import annotations\n\n\ndef names(module, listed):\n    pass\n\n\nnames('pdfmd_x', 'y')\n\n\n"
                "SHARED = {}\n\n\ndef deco(function):\n    return function\n\n\n# about the staying one\n@deco\n"
                "def stays():\n    return SHARED\n")
        mover_tree(self.root, code, "`SHARED`, `deco`", test="")
        self.assertEqual(self.move().returncode, 2)                          # a decorator and a dictionary: a decision
        done = self.move("--import-at-start")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pdfmd = (self.root / "pdfmd.py").read_text(encoding="utf-8")
        self.assertIn("names('pdfmd_x', 'y')\n\n\nfrom pdfmd_probe import deco, SHARED  # noqa: E402\n\n"
                      "# about the staying one\n@deco\n", pdfmd)
        self.assertNotIn('names("pdfmd_probe"', pdfmd)                      # bound in pdfmd.py: never a table entry too
        module = (self.root / "lib" / "pdfmd_probe" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("import core", module)                            # nothing in it reads core

    def test_a_dry_run_writes_nothing(self):
        mover_tree(self.root, MOVER_PDFMD, "`counter`, `outer`, `Holder`, `patched_helper`, `caller`")
        done = self.move("--dry-run")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.root / "pdfmd.py").read_text(encoding="utf-8"), MOVER_PDFMD)
        self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_what_it_refuses(self):
        head = "from __future__ import annotations\nLIMIT = 1\nSTATE = None\n\n\ndef deco(function):\n    return function\n\n\n"
        cases = {
            "a decorator": ("@deco\ndef moved():\n    pass\n", "reads deco when the module loads"),
            "a default argument": ("def moved(limit=LIMIT):\n    return limit\n", "reads LIMIT when the module loads"),
            "a class body": ("class moved:\n    size = LIMIT\n", "reads LIMIT when the module loads"),
            "a local core": ("def moved():\n    core = 1\n    return core + LIMIT\n", "named `core`"),
            "a walrus on state": ("def moved():\n    global STATE\n    if (STATE := 2):\n        pass\n", "cannot spell"),
            "globals()": ("def moved():\n    return globals()\n", "uses globals"),
            "a constant staying code reads": ("moved = 3\n\n\ndef stays():\n    return moved\n", "not a function"),
            "state staying code rebinds": ("moved = 3\n\n\ndef stays():\n    global moved\n    moved = 4\n", "rebinds it with `global`"),
            "a name bound in a try": ("try:\n    moved = 1\nexcept ImportError:\n    moved = None\n", "module-level statement"),
        }
        for case, (code, reason) in cases.items():
            with self.subTest(case):
                mover_tree(self.root, head + code, "`moved`", test="")
                done = self.move()
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn(reason, done.stdout)
                self.assertEqual((self.root / "pdfmd.py").read_text(encoding="utf-8"), head + code)
                self.assertFalse((self.root / "lib" / "pdfmd_probe").exists())

    def test_the_self_check_catches_a_wrong_text(self):
        mover_tree(self.root, MOVER_PDFMD, "`counter`, `outer`, `Holder`, `patched_helper`, `caller`")
        sys.path.insert(0, str(ROOT / "scripts"))
        self.addCleanup(sys.path.remove, str(ROOT / "scripts"))
        import split_move
        plan, source, tree = split_move.plan_move("pdfmd_probe", self.root, None, None)
        self.assertEqual(plan.refused, [])
        original = split_move.rewritten_block
        with unittest.mock.patch.object(split_move, "rewritten_block",
                                        lambda *a: original(*a).replace("core.weight(item)", "weight(item)")):
            written = split_move.apply(plan, source, tree, self.root, self.root)
        self.assertEqual(written, [])
        self.assertTrue(any("self-check failed" in reason for reason in plan.refused), plan.refused)
        self.assertEqual((self.root / "pdfmd.py").read_text(encoding="utf-8"), MOVER_PDFMD)


if __name__ == "__main__":
    unittest.main()

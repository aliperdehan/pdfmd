"""v3.33.5: the split's deferred re-exports (SPLIT.md, step 6). A package that pdfmd.py does not load at start is reached
through a stand-in (`deferred`) or `DEFERRED_NAMES`; it loads on first use and gets pdfmd as its `core`.

v3.33.188: one `core` for every package (lib/pdfmd_base): `SharedCore`.

v3.33.187i: the safety net for phase 2's moves (`SafetyNet`): every `core.NAME` in lib/ names something pdfmd has, every
table entry and stand-in names something its module has, no name is both a pdfmd global and a table entry, and no code in
lib/ binds a bare name that is one of pdfmd's state names (a `global X` lost in a move makes `X = ...` a silent local).

v3.33.189: the names table (phase 2's `names("pdfmd_x.role", "a b c")` lines, pdfmd_base.names_into): `names()` fills
`DEFERRED_NAMES` and refuses what it cannot serve, a table entry read once is kept in pdfmd's globals (later reads never
load anything), a patch of one is undone whether or not it had been read, `.cache_clear()` still reaches the real function;
the table read from the source (as `scripts/split_move.py` reads it) is the table pdfmd has, each name in it once, and no
module rebinds a name it serves (pdfmd would keep the first object)."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_base  # noqa: E402

PACKAGE = "pdfmd_split_probe"


class Deferred(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        package = Path(folder.name) / PACKAGE
        package.mkdir()
        (package / "__init__.py").write_text("LOADED_INIT = True\n", encoding="utf-8")
        (package / "role.py").write_text(textwrap.dedent("""\
            import functools
            from pdfmd_base import core
            TABLE = {"a": 1}

            def where(value):
                return core, value

            @functools.lru_cache(maxsize=None)
            def cached():
                return object()
        """), encoding="utf-8")
        sys.path.insert(0, folder.name)
        self.addCleanup(sys.path.remove, folder.name)
        self.addCleanup(self.forget)
        for name in ("TABLE", "cached"):
            self.addCleanup(pdfmd.DEFERRED_NAMES.pop, name, None)
            self.addCleanup(vars(pdfmd).pop, name, None)     # a table entry once read is kept in pdfmd's globals (3.33.189)

    def forget(self):
        for name in (f"{PACKAGE}.role", PACKAGE):
            sys.modules.pop(name, None)

    def test_the_stand_in_loads_on_the_first_call_and_binds_core(self):
        stand_in = pdfmd.deferred(f"{PACKAGE}.role", "where")
        self.assertNotIn(f"{PACKAGE}.role", sys.modules)
        self.assertEqual(stand_in.__name__, "where")
        self.assertEqual(stand_in(7), (pdfmd_base.core, 7))
        self.assertEqual(Path(pdfmd_base.bound().__file__).resolve(), ROOT / "pdfmd.py")   # the copy loaded first

    def test_a_deferred_name_is_the_package_s_own_object(self):
        pdfmd.DEFERRED_NAMES["TABLE"] = f"{PACKAGE}.role"
        self.assertIs(pdfmd.TABLE, sys.modules[f"{PACKAGE}.role"].TABLE)

    def test_an_unknown_name_is_still_an_attribute_error(self):
        self.assertFalse(hasattr(pdfmd, "no_such_name_anywhere"))
        self.assertNotIn("no_such_name_anywhere", vars(pdfmd))

    # ---- the names table (3.33.189) ----
    def test_names_fills_the_table_and_refuses_what_it_cannot_serve(self):
        table: dict[str, str] = {}
        names = pdfmd_base.names_into(table)
        names("pdfmd_x.role", "a b "
                              "c\n    d")                   # implicitly joined pieces, as scripts/split_move.py wraps them
        names("pdfmd_x.role", "a")                          # the same entry again changes nothing
        names("pdfmd_y", "")
        self.assertEqual(table, dict.fromkeys("abcd", "pdfmd_x.role"))
        with self.assertRaisesRegex(ValueError, "already served from pdfmd_x.role"):
            names("pdfmd_y", "e a")
        with self.assertRaisesRegex(ValueError, "'f,' is not a name"):
            names("pdfmd_y", "f, g")
        self.assertEqual(table, dict.fromkeys("abcd", "pdfmd_x.role"))      # a refused line adds nothing

    def test_pdfmd_names_fills_pdfmd_s_own_table(self):
        pdfmd.names(f"{PACKAGE}.role", "TABLE cached")
        self.assertEqual(pdfmd.DEFERRED_NAMES["TABLE"], f"{PACKAGE}.role")
        self.assertEqual(pdfmd.DEFERRED_NAMES["cached"], f"{PACKAGE}.role")

    def test_a_table_entry_read_once_is_kept_and_never_loaded_again(self):
        pdfmd.names(f"{PACKAGE}.role", "TABLE")
        self.assertNotIn("TABLE", vars(pdfmd))
        with mock.patch.object(pdfmd, "load_package", wraps=pdfmd.load_package) as load:
            first = pdfmd.TABLE
            self.assertIs(pdfmd.TABLE, first)
            self.assertIs(getattr(pdfmd, "TABLE"), first)
        self.assertEqual(load.call_count, 1)
        self.assertIs(vars(pdfmd)["TABLE"], sys.modules[f"{PACKAGE}.role"].TABLE)
        self.forget()                                       # the module gone: the kept object still answers
        self.assertIs(pdfmd.TABLE, first)

    def test_a_patch_of_a_table_entry_is_undone_before_and_after_its_first_read(self):
        pdfmd.names(f"{PACKAGE}.role", "TABLE")
        with mock.patch.object(pdfmd, "TABLE", "patched"):  # not read yet: the patch reads it first
            self.assertEqual(pdfmd.TABLE, "patched")
        real = sys.modules[f"{PACKAGE}.role"].TABLE
        self.assertIs(pdfmd.TABLE, real)
        with mock.patch.object(pdfmd, "TABLE", "again"):    # kept in pdfmd's globals now
            self.assertEqual(pdfmd.TABLE, "again")
        self.assertIs(pdfmd.TABLE, real)
        with mock.patch.dict(pdfmd.TABLE, {"b": 2}):        # in place: the module's own dict
            self.assertEqual(sys.modules[f"{PACKAGE}.role"].TABLE, {"a": 1, "b": 2})
        self.assertEqual(real, {"a": 1})

    def test_a_cached_function_in_the_table_keeps_cache_clear(self):
        pdfmd.names(f"{PACKAGE}.role", "cached")
        self.assertIs(pdfmd.cached, sys.modules[f"{PACKAGE}.role"].cached)
        first = pdfmd.cached()
        self.assertIs(pdfmd.cached(), first)
        pdfmd.cached.cache_clear()
        self.assertIsNot(pdfmd.cached(), first)


class Start(unittest.TestCase):
    def test_chain_and_paragraph_load_only_on_first_use(self):
        code = textwrap.dedent("""\
            import sys
            from pathlib import Path
            import pdfmd
            import pdfmd_base
            names = ('pdfmd_chain', 'pdfmd_paragraph')
            assert not any(name in sys.modules for name in names), [name for name in names if name in sys.modules]
            sys.argv = ['pdfmd', '--version']
            try:
                pdfmd.main()
            except SystemExit as error:
                assert error.code == 0
            assert not any(name in sys.modules for name in names)
            assert pdfmd.paragraph_spacing_typst_args(Path('unused.md'), [], 'html') == []
            assert sys.modules['pdfmd_paragraph'].core is pdfmd_base.core and pdfmd_base.bound() is pdfmd
            assert 'pdfmd_chain' not in sys.modules
            assert pdfmd.chain_stopped() == ''
            assert sys.modules['pdfmd_chain'].core is pdfmd_base.core
        """)
        done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_heavy_packages_do_not_load_at_start(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import pdfmd; "
                "print(' '.join(name for name in ('pdfmd_serve', 'pdfmd_office', 'http.server', 'ssl') if name in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")


class SharedCore(unittest.TestCase):
    """v3.33.188: `core` is lib/pdfmd_base's one object, bound to pdfmd when pdfmd.py loads; it was a `core = None` per
    module, set only when pdfmd.py imported that module, so a module imported any other way had none."""

    def test_every_module_takes_core_from_pdfmd_base(self):
        own = []
        for path in lib_sources():
            if path.parent.name == "pdfmd_base":
                continue
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if "core" in top_level_bindings([node]) and not (
                        isinstance(node, ast.ImportFrom) and node.module == "pdfmd_base"
                        and [(alias.name, alias.asname) for alias in node.names] == [("core", None)]):
                    own.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
        self.assertEqual(own, [], "a `core` of its own: `from pdfmd_base import core` instead")

    def test_reads_writes_and_patches_go_to_pdfmd(self):
        core = pdfmd_base.core
        pdfmd = pdfmd_base.bound()               # the copy of pdfmd.py loaded first in this process (a test may load two)
        self.assertIs(core.display_path, pdfmd.display_path)
        self.assertEqual(core.__file__, pdfmd.__file__)
        with mock.patch.object(pdfmd, "display_path", lambda path: "patched"):
            self.assertEqual(core.display_path("x"), "patched")
        self.assertIs(core.display_path, pdfmd.display_path)
        before = pdfmd.VERBOSE_OUTPUT
        with mock.patch.object(core, "VERBOSE_OUTPUT", "patched through core"):
            self.assertEqual(pdfmd.VERBOSE_OUTPUT, "patched through core")
        self.assertEqual(pdfmd.VERBOSE_OUTPUT, before)
        core.split_probe_value = 1
        self.assertEqual(pdfmd.split_probe_value, 1)
        del core.split_probe_value
        self.assertFalse(hasattr(pdfmd, "split_probe_value"))
        self.assertFalse(hasattr(core, "split_probe_value"))

    def test_the_first_binding_wins(self):
        first = pdfmd_base.bound()
        self.assertIsNotNone(first)
        pdfmd_base.bind(object())
        self.assertIs(pdfmd_base.bound(), first)

    def test_a_package_imported_on_its_own_has_its_core(self):
        code = textwrap.dedent("""\
            import os, sys
            sys.path[:0] = [sys.argv[1], os.path.join(sys.argv[1], "lib")]
            import pdfmd_base
            try:
                pdfmd_base.core.display_path
            except AttributeError as error:
                assert "not bound yet" in str(error), error
            else:
                raise AssertionError("an unbound core answered")
            assert not hasattr(pdfmd_base.core, "display_path")
            import pdfmd
            import pdfmd_chain                    # not through pdfmd: as a worker or another package imports it
            assert pdfmd_chain.core.display_path is pdfmd.display_path
            assert pdfmd_chain.stopped() == ""
        """)
        done = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=ROOT, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


# ---- the safety net (v3.33.187i) -------------------------------------------------------------------------------------
GENERATED = {"pdfmd_inkmd", "pdfmd_yaml", "__pycache__", "node_modules"}      # generated copies: never moved into or edited
# files whose `core` is not pdfmd: name -> what it is there
OTHER_CORE = {"lib/pdfmd_serve/shell.py": "the JSON core of --serve (pdfmd_serve.core.Core), a parameter"}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def lib_sources() -> list[Path]:
    return sorted(path for path in (ROOT / "lib").rglob("*.py") if not GENERATED & set(path.relative_to(ROOT).parts))


def own_binding(function: ast.AST, name: str) -> str | None:
    """'param' or 'local' when ``function`` binds ``name`` itself (not in a nested function), else None."""
    arguments = function.args
    every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg]
    if any(argument is not None and argument.arg == name for argument in every):
        return "param"
    declared = stored = False
    pending = list(ast.iter_child_nodes(function))
    while pending:
        node = pending.pop()
        if isinstance(node, (*FUNCTIONS, ast.ClassDef)):
            continue
        if isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            declared = True
        elif isinstance(node, ast.Name) and node.id == name and not isinstance(node.ctx, ast.Load):
            stored = True
        elif isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) == name:
            stored = True
        pending.extend(ast.iter_child_nodes(node))
    return "local" if stored and not declared else None


def core_uses(path: Path) -> tuple[list[tuple[str, int]], list[int]]:
    """The `core.NAME` uses in ``path`` whose `core` is pdfmd (the module's own `core`, or a parameter named `core`, which
    pdfmd_batch, pdfmd_report and pdfmd_args are handed pdfmd as), and the lines of uses with no `core` in scope."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_core = "core" in top_level_bindings(tree.body)
    found: list[tuple[str, int]] = []
    unbound: list[int] = []

    def visit(node: ast.AST, chain: list[ast.AST]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == "core":
                kind = next((binding for function in reversed(chain) for binding in [own_binding(function, "core")] if binding),
                            "module" if module_core else None)
                if kind is None:
                    unbound.append(child.lineno)
                elif kind != "local":
                    found.append((child.attr, child.lineno))
            visit(child, [*chain, child] if isinstance(child, FUNCTIONS) else chain)

    visit(tree, [])
    return found, unbound


def top_level_bindings(body: list[ast.stmt]) -> set[str]:
    """The names pdfmd.py binds at its top level, inside a top-level `if`/`try`/`with`/`for` too."""
    names: set[str] = set()
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name.split(".")[0]) for alias in node.names)
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            for block in (node.body, getattr(node, "orelse", []), getattr(node, "finalbody", []),
                          *[handler.body for handler in getattr(node, "handlers", [])]):
                names |= top_level_bindings(block)
            if isinstance(node, ast.For):
                names.update(name.id for name in ast.walk(node.target) if isinstance(name, ast.Name))
        else:
            names.update(name.id for name in ast.walk(node) if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store))
    return names


def table_lines(tree: ast.Module) -> list[tuple[str, str]]:
    """(name, module) for each word of pdfmd.py's top-level `names("module", "a b c")` and `DEFERRED_NAMES.update(a=...)`
    lines, in order; a `names(...)` line in any other shape (which `scripts/split_move.py` would not see) is an error."""
    found: list[tuple[str, str]] = []
    for node in tree.body:
        call = node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
        if call is None:
            continue
        if isinstance(call.func, ast.Name) and call.func.id == "names":
            if call.keywords or len(call.args) != 2 or not all(
                    isinstance(argument, ast.Constant) and isinstance(argument.value, str) for argument in call.args):
                raise AssertionError(f"pdfmd.py:{node.lineno}: names(...) takes two strings, the module and the names")
            found += [(name, call.args[0].value) for name in call.args[1].value.split()]
        elif (isinstance(call.func, ast.Attribute) and call.func.attr == "update"
              and isinstance(call.func.value, ast.Name) and call.func.value.id == "DEFERRED_NAMES"):
            found += [(keyword.arg, keyword.value.value) for keyword in call.keywords]
    return found


def module_source(module: str) -> Path:
    """lib/'s file for a module: `pdfmd_x` is lib/pdfmd_x/__init__.py, `pdfmd_x.role` lib/pdfmd_x/role.py."""
    path = ROOT / "lib" / Path(*module.split("."))
    return path / "__init__.py" if path.is_dir() else path.with_suffix(".py")


def stand_ins(tree: ast.Module) -> list[tuple[str, str, str]]:
    """(name, module, attribute) of every `name = deferred("module", "attribute")` at pdfmd.py's top level."""
    return [(node.targets[0].id, node.value.args[0].value, node.value.args[1].value) for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "deferred"]


# Run in a child process, so what it loads (every deferred package) and what it reads (pdfmd's table) do not depend on what
# earlier tests in this process did.
PROBE = textwrap.dedent("""\
    import importlib, json, sys
    sys.path.insert(0, sys.argv[1])
    import pdfmd
    asked = json.loads(sys.stdin.read())
    def has(module, name):
        try:
            return hasattr(importlib.import_module(module), name)
        except ImportError:
            return False
    print(json.dumps({
        "table": dict(pdfmd.DEFERRED_NAMES),
        "core_missing": sorted(name for name in asked["core"] if not hasattr(pdfmd, name)),
        "table_missing": sorted(f"{name} ({module})" for name, module in pdfmd.DEFERRED_NAMES.items() if not has(module, name)),
        "stand_ins_missing": sorted(f"{name} = deferred({module!r}, {attribute!r})"
                                    for name, module, attribute in asked["stand_ins"] if not has(module, attribute)),
    }))
""")


class SafetyNet(unittest.TestCase):
    """Phase 2 moves definitions out of pdfmd.py by name (SPLIT.md); a slip in one shows here, not as a wrong build later."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse((ROOT / "pdfmd.py").read_text(encoding="utf-8"))
        cls.uses: dict[str, list[str]] = {}
        cls.unbound: list[str] = []
        for path in lib_sources():
            relative = path.relative_to(ROOT).as_posix()
            if relative in OTHER_CORE:
                continue
            found, unbound = core_uses(path)
            for name, line in found:
                cls.uses.setdefault(name, []).append(f"{relative}:{line}")
            cls.unbound += [f"{relative}:{line}" for line in unbound]
        asked = {"core": sorted(cls.uses), "stand_ins": stand_ins(cls.tree)}
        done = subprocess.run([sys.executable, "-c", PROBE, str(ROOT)], input=json.dumps(asked), capture_output=True,
                              text=True, encoding="utf-8", env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
        if done.returncode:
            raise AssertionError(done.stdout + done.stderr)
        cls.probe = json.loads(done.stdout)

    def test_the_scan_finds_the_core_reads(self):
        # 495 distinct names at 3.33.74 and more with every move; far fewer means the scan lost track, not that lib/ changed
        self.assertGreater(len(self.uses), 400)
        self.assertGreater(len(stand_ins(self.tree)), 50)

    def test_every_core_name_in_lib_is_something_pdfmd_has(self):
        self.assertEqual(self.unbound, [], "core.X where no `core` is in scope")
        missing = {name: self.uses[name][:3] for name in self.probe["core_missing"]}
        self.assertEqual(missing, {}, "core.X that pdfmd has no X for (a name lost or misspelt in a move)")

    def test_every_table_entry_and_stand_in_names_something_its_module_has(self):
        self.assertEqual(self.probe["table_missing"], [])
        self.assertEqual(self.probe["stand_ins_missing"], [])

    def test_the_table_read_from_the_source_is_the_table_pdfmd_has(self):
        lines = table_lines(self.tree)
        self.assertGreater(len(lines), 5)
        twice = sorted(name for name, count in Counter(name for name, _ in lines).items() if count > 1)
        self.assertEqual(twice, [], "a name in two table lines: the later one wins, the earlier one is dead")
        self.assertEqual(dict(lines), self.probe["table"])

    @unittest.skipUnless(sys.version_info >= (3, 12), "scripts/split_move.py needs Python 3.12 (names inside f-strings)")
    def test_the_mover_reads_the_same_table(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        self.addCleanup(sys.path.remove, str(ROOT / "scripts"))
        import split_move
        self.assertEqual(split_move.table_entries(self.tree), set(self.probe["table"]))

    def test_no_module_rebinds_a_name_it_serves_to_the_table(self):
        # pdfmd keeps the object it read first (3.33.189): a module that rebinds the name later would leave pdfmd.X stale
        state = {name for node in ast.walk(self.tree) if isinstance(node, ast.Global) for name in node.names}
        rebound, missing = [], []
        for name, module in self.probe["table"].items():
            if name in state or name.endswith("_CLI"):
                rebound.append(f"{name}: pdfmd's state, never a table entry (a -j worker gets a copy of it)")
            path = module_source(module)
            if not path.is_file():
                missing.append(f"{name}: {module}")
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Global) and name in node.names:
                    rebound.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: global {name}")
        self.assertEqual(missing, [], "a table module with no file under lib/")
        self.assertEqual(rebound, [], "a table entry has to stay the same object: mutate it in place, or serve a function")

    def test_no_name_is_both_a_pdfmd_global_and_a_table_entry(self):
        # read from the source, not from the module: a table entry that has been read is kept in pdfmd's globals
        both = sorted(set(self.probe["table"]) & top_level_bindings(self.tree.body))
        self.assertEqual(both, [], "bound in pdfmd.py and in the table: the table entry is never used")

    def test_no_code_in_lib_binds_a_bare_state_name(self):
        tree = self.tree
        state = {name for node in ast.walk(tree) if isinstance(node, ast.Global) for name in node.names}
        state |= {name for name in top_level_bindings(tree.body) if name.endswith("_CLI")}
        workers = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                       and getattr(node.targets[0], "id", None) == "WORKER_GLOBALS")
        state |= {element.value for element in workers.elts}
        self.assertGreater(len(state), 60)
        found = []
        for path in lib_sources():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load) and node.id in state:
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: {node.id}")
                elif isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) in state:
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{getattr(node, 'lineno', '?')}: "  # no lineno before 3.10
                                 f"import {node.asname or node.name}")
        self.assertEqual(found, [], "pdfmd's state is written as core.X = ... in lib/; a bare name is a copy of its own")


if __name__ == "__main__":
    unittest.main()

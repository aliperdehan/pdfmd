#!/usr/bin/env python3
"""What one move of SPLIT.md needs, read from the source as it is now (entry 3fi).

    python3 scripts/split_spec.py pdfmd_comments
    python3 scripts/split_spec.py pdfmd_tex.inputs                 # a module of an existing package
    python3 scripts/split_spec.py pdfmd_base --sections moves.md   # sections from another file in SPLIT.md's format
    python3 scripts/split_spec.py pdfmd_routing --phase 1          # phase 1's section of a name both phases use

The section is looked up under SPLIT.md's `## Phase 2:` heading when there is one (phase 1's sections share six names with
phase 2's: `pdfmd_parts`, `pdfmd_routing`, `pdfmd_native` ...), else in the whole file; `--phase 1` reads under `## Phase 1:`.

For the package's definitions and constants (from its section) it prints:

- where the code goes (a new package, appended to one, or a module of its own in an existing one);
- where each one is in pdfmd.py now (line ranges; the comment block above a definition is not included), and a name bound
  only inside a top-level `if`/`try` (a module-level statement: moved by hand);
- the pdfmd names the moved code reads, which it must read as `core.NAME` (helpers, constants and state that stay), and
  the state it writes with `global`, which becomes `core.NAME = ...`;
- the modules and imported names it uses, which the package imports itself;
- the moved names that pdfmd.py, a test or a lib/ module still reads: the table entries;
- the names that tests patch or set on pdfmd (`mock.patch.object(pdfmd, "x")`, `patch("pdfmd.x")`, `patch.dict(pdfmd.X)`,
  `setattr(pdfmd, "X", ...)`, `pdfmd.X = ...`) and the moved names they patch on a lib/ module: a call to one of them from the
  moved code goes through `core.`, so the patch reaches it;
- what runs when a module loads: names the moved code reads then (decorators, default arguments, class bodies, constants
  built from constants), which `core` cannot serve, and moved names that code staying in pdfmd.py reads then (a decorator,
  a constant built from one, a module-level statement), which need a binding in pdfmd.py;
- `lru_cache` functions and their `.cache_clear()` / `.cache_info()` callers (a table entry, never a stand-in);
- uses of pdfmd.py itself in the moved code (`__file__`, `__name__`, `globals()`): `core.__file__`, `core`;
- names that pdfmd.py binds at the top level more than once (the later binding wins at run time, so moving one of them
  changes what the rest of pdfmd.py sees), and moved names that code staying in pdfmd.py rebinds with `global` (state);
- the test modules to run (the package's and the always-run set) and the proof command.

It reads files and prints; it changes nothing.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALWAYS = ["test_packaging", "test_setup", "test_docs_consistency", "test_compat", "test_probes", "test_serve",
          "test_launcher", "test_jobs", "test_split"]
SELF_NAMES = {"__file__", "__name__", "__spec__", "__doc__", "globals", "vars"}


def phase_part(text: str, phase: int) -> str | None:
    """The part of SPLIT.md under its `## Phase N:` heading, up to the next level-2 heading."""
    found = re.search(r"^## Phase %d:.*?(?=^## |\Z)" % phase, text, re.MULTILINE | re.DOTALL)
    return found.group(0) if found else None


def section(package: str, text: str | None = None, phase: int | None = None,
            root: Path = ROOT) -> tuple[list[str], list[str], list[str]]:
    """The definitions, constants and test modules that SPLIT.md (or ``text``) lists for ``package``: under the
    `## Phase N:` heading of ``phase``, or by default under `## Phase 2:` when there is one and else in the whole text."""
    if text is None:
        text = (root / "SPLIT.md").read_text(encoding="utf-8")
    part = phase_part(text, phase or 2)
    if part is None:
        if phase:
            raise SystemExit(f"{package}: no `## Phase {phase}:` heading")
        part = text
    found = list(re.finditer(r"^#### \d+\. `%s`.*?(?=^#{2,4} |\Z)" % re.escape(package), part, re.MULTILINE | re.DOTALL))
    if not found:
        raise SystemExit(f"{package}: no section")
    if len(found) > 1:
        raise SystemExit(f"{package}: {len(found)} sections with this name in one phase")
    body = found[0].group(0)

    def names(label: str) -> list[str]:
        line = re.search(r"^%s[^:]*:(.*)$" % re.escape(label), body, re.MULTILINE)
        return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", line.group(1)) if line else []

    tests = re.search(r"^Tests:(.*?)(?:\n\n|\Z)", body, re.MULTILINE | re.DOTALL)
    return names("Definitions"), names("Constants"), (re.findall(r"`(test_\w+)`", tests.group(1)) if tests else [])


def destination(package: str, root: Path = ROOT) -> str:
    """Where a move's code goes: `pdfmd_x.role` is lib/pdfmd_x/role.py, `pdfmd_x` its __init__.py."""
    top, _, role = package.partition(".")
    exists = (root / "lib" / top).is_dir()
    if role:
        target = root / "lib" / top / f"{role.replace('.', '/')}.py"
        return f"lib/{top}/{role.replace('.', '/')}.py" + (" (EXISTS: append, or choose another name)" if target.exists()
                                                           else f" (a new module of {'the existing' if exists else 'a NEW'} package)")
    return f"lib/{top}/__init__.py" + (" (appended to the existing package)" if exists else " (a new package: packaging in three places)")


def bound_names(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):  # `A, B = 1, 2` binds both
        return [name.id for target in node.targets for name in ast.walk(target) if isinstance(name, ast.Name)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def nested_bindings(node: ast.stmt) -> list[str]:
    """Names a top-level `if`/`try`/`with`/`for` binds inside itself (not in functions or classes)."""
    if not isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
        return []
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.append(child.id)
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            names += [(alias.asname or alias.name.split(".")[0]) for alias in child.names]
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(child.name)
    return names


def imported_names(tree: ast.Module) -> set[str]:
    """Every name an import binds, at any depth (a try/except import at the top level included)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update((alias.asname or alias.name.split(".")[0]) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update((alias.asname or alias.name) for alias in node.names)
    return names


def loaded(node: ast.AST) -> set[str]:
    """The names a definition reads, without the ones it binds itself (arguments, locals, comprehension targets)."""
    reads: set[str] = set()
    own: set[str] = set()
    declared: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            (reads if isinstance(child.ctx, ast.Load) else own).add(child.id)
        elif isinstance(child, ast.arg):
            own.add(child.arg)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            own.add(child.name)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child is not node:
            own.add(child.name)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            declared.update(child.names)     # after the walk: ast.walk meets `global X` before the `X = ...` below it
    return reads - (own - declared - {getattr(node, "name", None)})


def eager_reads(node: ast.AST) -> set[str]:
    """The names read while the statement itself runs (a module loading), not when a function it defines is called later:
    decorators, default arguments, base classes, class bodies, an assignment's value; a lambda's body runs later."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        parts = [*node.decorator_list, *node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]
    elif isinstance(node, ast.ClassDef):
        parts = [*node.decorator_list, *node.bases, *(keyword.value for keyword in node.keywords)]
        parts += [item for item in node.body]
    else:
        parts = [node]
    reads: set[str] = set()
    for part in parts:
        pending = [part]
        while pending:
            child = pending.pop()
            if isinstance(child, ast.Lambda):
                pending += [*child.args.defaults, *(d for d in child.args.kw_defaults if d is not None)]
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child is not node:
                reads |= eager_reads(child)      # a method or a nested class: its own decorators, defaults, body
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                reads.add(child.id)
            pending.extend(ast.iter_child_nodes(child))
    return reads


def start_line(node: ast.stmt) -> int:
    return min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])


def ranges(numbers: list[int]) -> str:
    out: list[list[int]] = []
    for number in sorted(numbers):
        if out and out[-1][1] == number - 1:
            out[-1][1] = number
        else:
            out.append([number, number])
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in out)


def listing(items, limit: int = 8) -> str:
    items = list(items)
    return ", ".join(items[:limit]) + (f" and {len(items) - limit} more" if len(items) > limit else "")


def test_patches(tests: list[Path], moving: set[str]) -> dict[str, list[str]]:
    """name -> where tests patch or set it on pdfmd ("file:line kind"), and moved names patched on another object."""
    forms = [
        ("patch.object", re.compile(r"patch\.object\(\s*pdfmd\s*,\s*[\"'](\w+)[\"']")),
        ("patch", re.compile(r"patch\(\s*[\"']pdfmd\.(\w+)[\"']")),
        ("patch.dict", re.compile(r"patch\.dict\(\s*(?:pdfmd\.|[\"']pdfmd\.)(\w+)(?![\w.])")),  # not pdfmd.os.environ
        ("setattr", re.compile(r"setattr\(\s*pdfmd\s*,\s*[\"'](\w+)[\"']")),
        ("assigned", re.compile(r"(?<![\w.])pdfmd\.(\w+)\s*=(?!=)")),
        ("item set", re.compile(r"(?<![\w.])pdfmd\.(\w+)\s*\[[^\]]*\]\s*=(?!=)")),          # in place, like patch.dict
        ("patch.object on ", re.compile(r"patch\.object\(\s*(?!pdfmd\s*,)([\w.]+)\s*,\s*[\"'](\w+)[\"']")),
    ]
    found: dict[str, list[str]] = {}
    for path in tests:
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for kind, pattern in forms:
                for match in pattern.finditer(line):
                    if kind == "patch.object on ":
                        if match.group(2) in moving:
                            found.setdefault(match.group(2), []).append(f"{path.name}:{number} {kind}{match.group(1)}")
                    else:
                        found.setdefault(match.group(1), []).append(f"{path.name}:{number} {kind}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("package", help="a section's key: pdfmd_x, or pdfmd_x.role for a module of an existing package")
    parser.add_argument("--sections", type=Path, help="read the section from this file instead of SPLIT.md")
    parser.add_argument("--phase", type=int, choices=(1, 2), help="look under `## Phase N:` (default: 2 when it is there)")
    parser.add_argument("--root", type=Path, default=ROOT, help="the checkout to read (default: this script's)")
    args = parser.parse_args(argv)
    package = args.package
    root = args.root.resolve()
    text = args.sections.read_text(encoding="utf-8") if args.sections else None
    definitions, constants, test_modules = section(package, text, args.phase, root)
    moving = set(definitions) | set(constants)
    source = (root / "pdfmd.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    where: dict[str, list[ast.stmt]] = {}
    for node in tree.body:
        for name in bound_names(node):
            where.setdefault(name, []).append(node)
    rebound: dict[str, list[ast.AST]] = {}
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(function):
                if isinstance(child, ast.Global):
                    for name in child.names:
                        rebound.setdefault(name, []).append(function)
    imports = imported_names(tree)

    print(f"# {package}: {len(definitions)} definitions, {len(constants)} constants\n")
    print(f"## Where the code goes\n- {destination(package, root)}")
    print("\n## Where they are now")
    moved_nodes: list[ast.stmt] = []
    moved_lines: set[int] = set()
    for name in [*definitions, *constants]:
        nodes = where.get(name, [])
        if not nodes:
            nested = [node for node in tree.body if name in nested_bindings(node)]
            if nested:
                print(f"- {name}: bound inside the module-level statement at "
                      + ", ".join(f"{start_line(node)}-{node.end_lineno}" for node in nested) + ": MOVE IT BY HAND")
            else:
                print(f"- {name}: NOT FOUND at the top level of pdfmd.py")
            continue
        for node in nodes:
            start = start_line(node)
            print(f"- {name}: {start}-{node.end_lineno}")
            if node not in moved_nodes:
                moved_nodes.append(node)
            moved_lines.update(range(start, node.end_lineno + 1))
        if len(nodes) > 1:
            print(f"  WARNING: bound {len(nodes)} times; the last one wins at run time")
    moved_ids = {id(node) for node in moved_nodes}
    inside = {id(child) for node in moved_nodes for child in ast.walk(node)}

    reads: set[str] = set()
    for node in moved_nodes:
        reads |= loaded(node)
    reads -= moving
    stays = sorted(name for name in reads if name in where and name not in imports)
    modules = sorted(name for name in reads if name in imports)
    print("\n## Read as core.NAME (pdfmd names that stay)")
    print("\n".join(f"- {name}" + ("  (rebound with global)" if name in rebound else "") for name in stays) or "- none")
    written = sorted({name for node in moved_nodes for child in ast.walk(node) if isinstance(child, ast.Global)
                      for name in child.names if name not in moving})
    print("\n## Written by the moved code with `global` (the `global` line goes, writes become core.NAME = ...)")
    print("\n".join(f"- {name}" for name in written) or "- none")
    print("\n## Imported by the package itself")
    print("\n".join(f"- {name}" for name in modules) or "- none")
    unknown = sorted(name for name in reads if name not in where and name not in imports and not hasattr(builtins, name)
                     and name not in SELF_NAMES)
    if unknown:
        print("\n## Names not found anywhere (check by hand)")
        print("\n".join(f"- {name}" for name in unknown))

    print("\n## Users outside the move (the table entries)")
    tests = sorted((root / "tests").glob("*.py"))
    libs = sorted(path for path in (root / "lib").rglob("*.py")
                  if not {"pdfmd_inkmd", "pdfmd_yaml", "node_modules"} & set(path.parts))
    lib_texts = {path: path.read_text(encoding="utf-8", errors="replace") for path in libs}
    test_texts = {path: path.read_text(encoding="utf-8", errors="replace") for path in tests}
    for name in sorted(moving):
        word = re.compile(r"(?<![\w.])%s\b" % re.escape(name))
        attribute = re.compile(r"\b(?:pdfmd|core)\.%s\b" % re.escape(name))
        users = [f"pdfmd.py:{number}" for number, line in enumerate(lines, 1)
                 if number not in moved_lines and word.search(line.split("#")[0])]
        for path, body in (*test_texts.items(), *lib_texts.items()):
            users += [f"{path.relative_to(root)}:{number}" for number, line in enumerate(body.splitlines(), 1)
                      if attribute.search(line)]
        print(f"- {name}: " + (f"TABLE ({listing(users)})" if users else "only the package"))

    print("\n## Patched or set by tests")
    patched = test_patches(tests, moving)
    relevant = sorted(name for name in patched if name in moving or name in reads or name in written)
    for name in relevant:
        why = "moved" if name in moving else "used by the moved code: always as core." + name
        print(f"- {name} ({why}): {listing(patched[name], 4)}")
    if not relevant:
        print("- none that the move touches")

    print("\n## Read when a module loads (core cannot serve these)")
    eager_moving: dict[str, set[str]] = {}
    for node in moved_nodes:
        for name in eager_reads(node) - set(bound_names(node)):
            if name in where and name not in imports and not hasattr(builtins, name):
                eager_moving.setdefault(name, set()).update(bound_names(node))
    for name in sorted(eager_moving):
        status = "moves too: define it first in the module" if name in moving else "STAYS: core is not usable at import; import it or move it"
        print(f"- {name} ({status}), read by {listing(sorted(eager_moving[name]), 5)}")
    if not eager_moving:
        print("- nothing from pdfmd.py")
    print("\n## Moved names that code staying in pdfmd.py reads when it loads (needs a binding in pdfmd.py, not the table)")
    outside_eager = []
    other_statements = []
    for node in tree.body:
        if id(node) in moved_ids:
            continue
        used = sorted(eager_reads(node) & moving)
        if used and (bound_names(node) or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))):
            outside_eager.append(f"- line {start_line(node)} ({listing(bound_names(node), 3)}): {', '.join(used)}")
        elif not bound_names(node):
            named = sorted(name for name in loaded(node) & moving)
            if named:
                other_statements.append(f"- {start_line(node)}-{node.end_lineno} ({type(node).__name__}): {', '.join(named)}")
    print("\n".join(outside_eager) or "- none")
    print("\n## Module-level statements of pdfmd.py that use a moved name (imports, calls, if/try blocks)")
    print("\n".join(other_statements) or "- none")

    print("\n## Cached functions and their .cache_clear() / .cache_info() callers")
    cached = []
    for name in sorted(moving):
        decorated = any("cache" in ast.unparse(decorator) for node in where.get(name, [])
                        for decorator in getattr(node, "decorator_list", []))
        callers = []
        pattern = re.compile(r"\b(?:(?:pdfmd|core)\.)?%s\.(cache_clear|cache_info)\(" % re.escape(name))
        callers += [f"pdfmd.py:{number}" for number, line in enumerate(lines, 1) if number not in moved_lines and pattern.search(line)]
        for path, body in (*test_texts.items(), *lib_texts.items()):
            callers += [f"{path.relative_to(root)}:{number}" for number, line in enumerate(body.splitlines(), 1)
                        if pattern.search(line)]
        if decorated or callers:
            cached.append(f"- {name}" + (" (cached)" if decorated else "") + (f": {listing(callers, 5)}" if callers else ""))
    print("\n".join(cached) or "- none")

    print("\n## pdfmd.py itself in the moved code (__file__ is core.__file__; sys.modules[__name__] and globals() are core)")
    self_uses = []
    for node in moved_nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in SELF_NAMES and isinstance(child.ctx, ast.Load):
                self_uses.append(f"- {listing(bound_names(node), 2)}: {child.id} at line {child.lineno}")
    print("\n".join(dict.fromkeys(self_uses)) or "- none")

    print("\n## Bound more than once at the top level of pdfmd.py")
    twice = sorted(name for name, nodes in where.items() if len(nodes) > 1 and (name in moving or name in reads))
    for name in twice:
        print(f"- {name}: lines {', '.join(str(node.lineno) for node in where[name])}")
    if not twice:
        print("- none that the move touches")
    print("\n## Moved names rebound with `global`")
    state = []
    for name in sorted(moving & set(rebound)):
        outside = sorted({function.name for function in rebound[name] if id(function) not in inside})
        state.append(f"- {name}: " + (f"STATE, rebound by code that stays ({listing(outside, 4)}): it should stay in pdfmd.py"
                                      if outside else "only by moved code: a global of the package"))
    print("\n".join(state) or "- none")

    print(f"\nMoved lines: {ranges(sorted(moved_lines))}")
    print("\n## Tests to run (from tests/)\npython3 -m unittest -v " + " ".join(dict.fromkeys([*test_modules, *ALWAYS])))
    print("\n## The proof\npython3 scripts/split_check.py   (add --extra 'NAME:ARGS' for the package's own feature)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

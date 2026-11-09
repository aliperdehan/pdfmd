#!/usr/bin/env python3
"""What one move of SPLIT.md needs, read from the source as it is now (entry 3fi).

    python3 scripts/split_spec.py pdfmd_comments

For the package's definitions and constants (from its section in SPLIT.md) it prints:

- where each one is in pdfmd.py now (line ranges; the comment block above a definition is not included);
- the pdfmd names the moved code reads, which it must read as `core.NAME` (helpers, constants and state that stay);
- the modules and imported names it uses, which the package imports itself;
- the moved names that pdfmd.py, a test or a lib/ module still reads: the re-exports;
- the names that tests patch on pdfmd (`mock.patch.object(pdfmd, "x")`, `patch("pdfmd.x")`): a call to one of
  them from the moved code goes through `core.`, so the patch reaches it;
- names that pdfmd.py binds at the top level more than once (the later binding wins at run time, so moving one of them
  changes what the rest of pdfmd.py sees);
- names rebound with `global`, which stay in pdfmd.py;
- the test modules to run (the package's and the always-run set) and the proof command.

It reads files and prints; it changes nothing.
"""

from __future__ import annotations

import ast
import builtins
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(package: str) -> tuple[list[str], list[str], list[str]]:
    """The definitions, constants and test modules that SPLIT.md lists for ``package``."""
    text = (ROOT / "SPLIT.md").read_text(encoding="utf-8")
    match = re.search(r"^#### \d+\. `%s`.*?(?=^#{2,4} )" % re.escape(package), text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(f"{package}: no section in SPLIT.md")
    body = match.group(0)

    def names(label: str) -> list[str]:
        found = re.search(r"^%s[^:]*:(.*)$" % re.escape(label), body, re.MULTILINE)
        return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", found.group(1)) if found else []

    tests = re.search(r"^Tests:(.*?)(?:\n\n|\Z)", body, re.MULTILINE | re.DOTALL)
    return names("Definitions"), names("Constants"), (re.findall(r"`(test_\w+)`", tests.group(1)) if tests else [])


def bound_names(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):  # `A, B = 1, 2` binds both
        return [name.id for target in node.targets for name in ast.walk(target) if isinstance(name, ast.Name)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


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
            own.difference_update(child.names)
    return reads - (own - {getattr(node, "name", None)})


def ranges(numbers: list[int]) -> str:
    out: list[str] = []
    for number in sorted(numbers):
        if out and out[-1][1] == number - 1:
            out[-1][1] = number
        else:
            out.append([number, number])
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in out)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    package = sys.argv[1]
    definitions, constants, test_modules = section(package)
    moving = set(definitions) | set(constants)
    source = (ROOT / "pdfmd.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    where: dict[str, list[ast.stmt]] = {}
    for node in tree.body:
        for name in bound_names(node):
            where.setdefault(name, []).append(node)
    rebound = {name for node in ast.walk(tree) if isinstance(node, ast.Global) for name in node.names}
    imports = imported_names(tree)

    print(f"# {package}: {len(definitions)} definitions, {len(constants)} constants\n")
    print("## Where they are now")
    moved_nodes: list[ast.stmt] = []
    moved_lines: set[int] = set()
    for name in [*definitions, *constants]:
        nodes = where.get(name, [])
        if not nodes:
            print(f"- {name}: NOT FOUND at the top level of pdfmd.py")
            continue
        for node in nodes:
            start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
            print(f"- {name}: {start}-{node.end_lineno}")
            moved_nodes.append(node)
            moved_lines.update(range(start, node.end_lineno + 1))
        if len(nodes) > 1:
            print(f"  WARNING: bound {len(nodes)} times; the last one wins at run time")

    reads: set[str] = set()
    for node in moved_nodes:
        reads |= loaded(node)
    reads -= moving
    stays = sorted(name for name in reads if name in where and name not in imports)
    modules = sorted(name for name in reads if name in imports)
    print("\n## Read as core.NAME (pdfmd names that stay)")
    print("\n".join(f"- {name}" + ("  (rebound with global)" if name in rebound else "") for name in stays) or "- none")
    print("\n## Imported by the package itself")
    print("\n".join(f"- {name}" for name in modules) or "- none")
    unknown = sorted(name for name in reads if name not in where and name not in imports and not hasattr(builtins, name))
    if unknown:
        print("\n## Names not found anywhere (check by hand)")
        print("\n".join(f"- {name}" for name in unknown))

    print("\n## Users outside the move (the re-exports)")
    lines = source.splitlines()
    tests = sorted((ROOT / "tests").glob("*.py"))
    libs = sorted(path for path in (ROOT / "lib").rglob("*.py")
                  if "pdfmd_inkmd" not in path.parts and "node_modules" not in path.parts)
    for name in sorted(moving):
        word = re.compile(r"(?<![\w.])%s\b" % re.escape(name))
        attribute = re.compile(r"\b(?:pdfmd|core)\.%s\b" % re.escape(name))
        users = [f"pdfmd.py:{number}" for number, line in enumerate(lines, 1)
                 if number not in moved_lines and word.search(line.split("#")[0])]
        for path in (*tests, *libs):
            text = path.read_text(encoding="utf-8", errors="replace")
            users += [f"{path.relative_to(ROOT)}:{number}" for number, line in enumerate(text.splitlines(), 1)
                      if attribute.search(line)]
        shown = ", ".join(users[:8]) + (f" and {len(users) - 8} more" if len(users) > 8 else "")
        print(f"- {name}: " + (f"RE-EXPORT ({shown})" if users else "only the package"))

    print("\n## Patched by tests")
    patched: dict[str, list[str]] = {}
    pattern = re.compile(r"patch\.object\(\s*pdfmd\s*,\s*[\"'](\w+)[\"']|patch\(\s*[\"']pdfmd\.(\w+)[\"']")
    for path in tests:
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for found in pattern.finditer(line):
                patched.setdefault(found.group(1) or found.group(2), []).append(f"{path.name}:{number}")
    relevant = sorted(name for name in patched if name in moving or name in reads)
    for name in relevant:
        why = "moved" if name in moving else "called by the moved code: call it as core." + name
        print(f"- {name} ({why}): {', '.join(patched[name][:4])}")
    if not relevant:
        print("- none that the move touches")

    print("\n## Bound more than once at the top level of pdfmd.py")
    twice = sorted(name for name, nodes in where.items() if len(nodes) > 1 and (name in moving or name in reads))
    for name in twice:
        print(f"- {name}: lines {', '.join(str(node.lineno) for node in where[name])}")
    if not twice:
        print("- none that the move touches")

    print(f"\nMoved lines: {ranges(sorted(moved_lines))}")
    always = ["test_packaging", "test_setup", "test_docs_consistency", "test_compat", "test_probes", "test_serve",
              "test_launcher", "test_jobs"]
    print("\n## Tests to run (from tests/)\npython3 -m unittest -v " + " ".join(dict.fromkeys([*test_modules, *always])))
    print("\n## The proof\npython3 scripts/split_check.py   (add --extra 'NAME:ARGS' for the package's own feature)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

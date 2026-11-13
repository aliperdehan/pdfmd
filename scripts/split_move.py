#!/usr/bin/env python3
"""Move one section of SPLIT.md out of pdfmd.py, mechanically (phase 2 of the split, entry 3fi; plan decision D5).

    python3 scripts/split_move.py pdfmd_edit.command --dry-run      # what it would do, and what it refuses
    python3 scripts/split_move.py pdfmd_edit.command                # do it
    python3 scripts/split_move.py pdfmd_x --sections moves.md --out /tmp/try   # write the result elsewhere

It reads the section (`scripts/split_spec.py` finds it: the definitions and constants that move), then:

- cuts each moved statement out of pdfmd.py with the comment block right above it (no blank line between);
- writes them, in pdfmd.py's order, to the package's module (`pdfmd_x` -> lib/pdfmd_x/__init__.py, `pdfmd_x.role` ->
  lib/pdfmd_x/role.py; appended when the file exists), under the imports they need and `from pdfmd_base import core`;
- rewrites every read of a pdfmd name that stays (a definition, a constant, state, an import from a pdfmd_* package, a
  table entry) to `core.NAME`, decided by Python's scoping rules: a parameter, a local, a closure variable, a
  comprehension's own variable or a class attribute of the same name is left alone;
- turns `global X` plus `X = ...` (X staying in pdfmd.py) into `core.X = ...` (also `+=`, `del`, a `for` or `with` target);
- reads a moved name that tests rebind on pdfmd (`patch.object(pdfmd, "x")`, `patch("pdfmd.x")`, `setattr`, `pdfmd.x = ...`)
  as `core.NAME` inside the move too, so the patch still reaches the moved callers;
- `__file__` becomes `core.__file__` and `sys.modules[__name__]` becomes `core`;
- adds the table line to pdfmd.py (`names("pdfmd_x.role", "a b c")`, after the last one) for the moved names read from
  outside the move, and a stand-in (`NAME = deferred(...)`) for a moved function that code staying in pdfmd.py calls bare;
- with `--import-at-start`, binds the moved names that code staying in pdfmd.py needs when it loads (a decorator, a
  constant built from one) or reads bare and are not functions with a plain `from pdfmd_x import ...` right above the
  first statement that needs one: the package then loads at every start (pdfmd_base is the one meant to).

It lists every comment block it carries: the rule (the comment lines right above a statement, no blank line between)
cannot tell a definition's comment from a section's banner that happens to sit on it. It checks itself: every moved statement, parsed from the text it wrote, has the same AST as the original with exactly these
substitutions. It refuses, and writes nothing, when the move needs a decision: a pdfmd name read when the module loads (a
decorator, a default argument, a class body, a constant built from it: `core` cannot serve it then), a moved name that
staying code needs when pdfmd.py loads, or reads bare when it is not a function, or rebinds with `global`, a local or a
parameter named `core`, a name bound by a module-level `if`/`try` or bound twice, `globals()`, `vars()`, `__name__` other
than in `sys.modules[__name__]`, a state write it cannot spell as an attribute (a walrus, `except ... as`, an import). The
packaging of a new package, the changelog and the proof stay with whoever runs it (SPLIT.md).

Python's scoping is computed here from the AST, not with `symtable`: from 3.12 on `symtable` reports an inlined
comprehension's variable as a local of the enclosing function (PEP 709), so its answer depends on the Python version.
Needs Python 3.12 or later (the positions of names inside f-strings).
"""

from __future__ import annotations

import argparse
import ast
import builtins
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import split_spec  # noqa: E402

ROOT = split_spec.ROOT
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
REBINDING = {"patch.object", "patch", "setattr", "assigned"}     # test patches that rebind pdfmd.X (patch.dict does not)
SELF_REFUSED = {"__name__", "globals", "__doc__", "__spec__", "__loader__", "__package__", "__builtins__"}
GENERATED = {"pdfmd_inkmd", "pdfmd_yaml", "node_modules", "__pycache__"}


# ---------------------------------------------------------------------------------------------------- scopes
@dataclass
class Scope:
    kind: str                                # module, function, class, comprehension
    bound: set[str] = field(default_factory=set)
    declared_global: set[str] = field(default_factory=set)
    declared_nonlocal: set[str] = field(default_factory=set)


def target_names(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def scope_of(node: ast.AST) -> Scope:
    """The names ``node`` (a function, lambda, class or comprehension) binds in its own scope, by Python's rules."""
    if isinstance(node, COMPREHENSIONS):
        return Scope("comprehension", set().union(*(target_names(generator.target) for generator in node.generators)))
    scope = Scope("class" if isinstance(node, ast.ClassDef) else "function")
    if isinstance(node, FUNCTIONS):
        arguments = node.args
        scope.bound |= {argument.arg for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                                                      arguments.vararg, arguments.kwarg) if argument is not None}
    pending = list(node.body if isinstance(node.body, list) else [node.body])
    while pending:
        child = pending.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope.bound.add(child.name)      # its decorators, defaults and bases run here; its body is a scope of its own
            pending += [*child.decorator_list, *getattr(child, "bases", []), *(k.value for k in getattr(child, "keywords", []))]
            if not isinstance(child, ast.ClassDef):
                pending += [*child.args.defaults, *(d for d in child.args.kw_defaults if d is not None)]
            continue
        if isinstance(child, ast.Lambda):
            pending += [*child.args.defaults, *(d for d in child.args.kw_defaults if d is not None)]
            continue
        if isinstance(child, COMPREHENSIONS):
            pending.append(child.generators[0].iter)     # evaluated here; a walrus inside binds in the enclosing function
            if scope.kind == "function":
                scope.bound |= {walrus.target.id for walrus in ast.walk(child) if isinstance(walrus, ast.NamedExpr)}
            continue
        if isinstance(child, ast.Name) and not isinstance(child.ctx, ast.Load):
            scope.bound.add(child.id)
        elif isinstance(child, ast.alias):
            scope.bound.add(child.asname or child.name.split(".")[0])
        elif isinstance(child, ast.ExceptHandler) and child.name:
            scope.bound.add(child.name)
        elif isinstance(child, (ast.MatchAs, ast.MatchStar)) and child.name:
            scope.bound.add(child.name)
        elif isinstance(child, ast.MatchMapping) and child.rest:
            scope.bound.add(child.rest)
        elif isinstance(child, ast.Global):
            scope.declared_global |= set(child.names)
        elif isinstance(child, ast.Nonlocal):
            scope.declared_nonlocal |= set(child.names)
        pending.extend(ast.iter_child_nodes(child))
    scope.bound -= scope.declared_global | scope.declared_nonlocal
    return scope


@dataclass
class Use:
    node: ast.Name
    resolved: str                            # "global" or "local"
    eager: bool                              # evaluated while the module loads
    annotation: bool


def name_uses(statement: ast.stmt) -> tuple[list[Use], list[Scope]]:
    """Every Name in a top-level statement, resolved to its scope, and whether it is evaluated while the module loads
    (annotations never are: every module here has `from __future__ import annotations`)."""
    uses: list[Use] = []
    scopes: list[Scope] = []

    def resolve(name: str, chain: list[Scope]) -> str:
        for depth, scope in enumerate(reversed(chain)):
            if scope.kind == "class" and depth > 0:
                continue                     # a class body's names are not seen by the functions inside it
            if name in scope.declared_global:
                return "global"
            if name in scope.declared_nonlocal or name in scope.bound:
                return "local"
        return "global"

    def visit(node: ast.AST, chain: list[Scope], eager: bool, annotation: bool = False) -> None:
        if isinstance(node, ast.Name):
            uses.append(Use(node, resolve(node.id, chain), eager and not annotation, annotation))
            return
        if isinstance(node, FUNCTIONS):
            arguments = node.args
            for part in (*getattr(node, "decorator_list", []), *arguments.defaults,
                         *(d for d in arguments.kw_defaults if d is not None)):
                visit(part, chain, eager, annotation)
            for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg):
                if argument is not None and argument.annotation is not None:
                    visit(argument.annotation, chain, eager, True)
            if getattr(node, "returns", None) is not None:
                visit(node.returns, chain, eager, True)
            inner = scope_of(node)
            scopes.append(inner)
            for part in (node.body if isinstance(node.body, list) else [node.body]):
                visit(part, [*chain, inner], False, annotation)
            return
        if isinstance(node, ast.ClassDef):
            for part in (*node.decorator_list, *node.bases, *(keyword.value for keyword in node.keywords)):
                visit(part, chain, eager, annotation)
            inner = scope_of(node)
            scopes.append(inner)
            for part in node.body:
                visit(part, [*chain, inner], eager, annotation)
            return
        if isinstance(node, COMPREHENSIONS):
            visit(node.generators[0].iter, chain, eager, annotation)
            inner = scope_of(node)
            scopes.append(inner)
            inside = [*chain, inner]
            for number, generator in enumerate(node.generators):
                visit(generator.target, inside, eager, annotation)
                if number:
                    visit(generator.iter, inside, eager, annotation)
                for condition in generator.ifs:
                    visit(condition, inside, eager, annotation)
            for part in ([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]):
                visit(part, inside, eager, annotation)
            return
        if isinstance(node, ast.NamedExpr):
            outer = list(chain)              # the walrus target binds in the nearest scope that is not a comprehension
            while len(outer) > 1 and outer[-1].kind == "comprehension":
                outer.pop()
            visit(node.target, outer, eager, annotation)
            visit(node.value, chain, eager, annotation)
            return
        if isinstance(node, ast.AnnAssign):
            visit(node.annotation, chain, eager, True)
            for part in (node.target, node.value):
                if part is not None:
                    visit(part, chain, eager, annotation)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, chain, eager, annotation)

    visit(statement, [Scope("module")], True)
    return uses, scopes


# ---------------------------------------------------------------------------------------------------- the plan
@dataclass
class Plan:
    key: str
    target: Path
    statements: list[ast.stmt]
    moving: set[str]
    edits: dict[int, str] = field(default_factory=dict)              # id(Name or Subscript) -> replacement text
    globals_kept: dict[int, list[str]] = field(default_factory=dict)  # id(Global) -> names left (empty: the line goes)
    imports: dict[str, str] = field(default_factory=dict)             # name -> its import line
    table: list[str] = field(default_factory=list)
    stand_ins: list[str] = field(default_factory=list)
    at_start: dict[str, int] = field(default_factory=dict)            # name -> the first line that needs it (--import-at-start)
    refused: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    carried: list[str] = field(default_factory=list)                  # the comment blocks that move, to be read


def module_changes(node: ast.AST) -> set[str]:
    """Bindings and deletions executed in the module namespace, without entering nested scopes."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Lambda, *COMPREHENSIONS)):
        return set()
    if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
        return {node.id}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {alias.asname or alias.name.split(".")[0] for alias in node.names}
    return set().union(*(module_changes(child) for child in ast.iter_child_nodes(node)))


def top_level_imports(tree: ast.Module) -> dict[str, ast.stmt]:
    """name -> the plain top-level import statement that binds it (not one inside an `if` or `try`)."""
    found: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = node
    return found


def import_line(node: ast.stmt, name: str) -> str:
    for alias in node.names:
        if (alias.asname or alias.name.split(".")[0]) == name:
            spelled = alias.name + (f" as {alias.asname}" if alias.asname else "")
            return f"import {spelled}" if isinstance(node, ast.Import) else f"from {node.module} import {spelled}"
    raise KeyError(name)


def table_entries(tree: ast.Module) -> set[str]:
    """The names pdfmd.py serves from its table: `names("module", "a b c")` and `DEFERRED_NAMES.update(a="module")`."""
    found: set[str] = set()
    for node in tree.body:
        call = node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
        if call is None:
            continue
        if isinstance(call.func, ast.Name) and call.func.id == "names" and len(call.args) == 2 \
                and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
            found.update(call.args[1].value.split())
        elif isinstance(call.func, ast.Attribute) and call.func.attr == "update" \
                and isinstance(call.func.value, ast.Name) and call.func.value.id == "DEFERRED_NAMES":
            found.update(keyword.arg for keyword in call.keywords if keyword.arg)
    return found


def is_sys_modules_name(node: ast.AST) -> bool:
    return (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Name) and node.slice.id == "__name__"
            and isinstance(node.value, ast.Attribute) and node.value.attr == "modules"
            and isinstance(node.value.value, ast.Name) and node.value.value.id == "sys")


def plan_move(key: str, root: Path, text: str | None, phase: int | None,
              at_start: bool = False) -> tuple[Plan, str, ast.Module]:
    definitions, constants, _tests = split_spec.section(key, text, phase, root)
    moving = set(definitions) | set(constants)
    source = (root / "pdfmd.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top, _, role = key.partition(".")
    target = root / "lib" / top / (f"{role.replace('.', '/')}.py" if role else "__init__.py")
    plan = Plan(key, target, [], moving)
    if role and not (root / "lib" / top).is_dir():
        plan.refused.append(f"lib/{top} does not exist: move its own section first")

    where: dict[str, list[ast.stmt]] = {}
    for node in tree.body:
        for name in split_spec.bound_names(node):
            where.setdefault(name, []).append(node)
    for name in [*definitions, *constants]:
        nodes = where.get(name, [])
        if not nodes:
            nested = [node for node in tree.body if name in split_spec.nested_bindings(node)]
            plan.refused.append(f"{name}: bound inside the module-level statement at line {nested[0].lineno}" if nested
                                else f"{name}: not found at the top level of pdfmd.py")
        elif len(nodes) > 1:
            plan.refused.append(f"{name}: bound {len(nodes)} times at the top level (lines "
                                + ", ".join(str(node.lineno) for node in nodes) + ")")
        elif isinstance(nodes[0], ast.AugAssign):
            plan.refused.append(f"{name}: changed in place at the top level (line {nodes[0].lineno})")
        elif nodes[0] not in plan.statements:
            plan.statements.append(nodes[0])
    for node in tree.body:
        if node not in plan.statements:
            for name in sorted(module_changes(node) & moving):
                plan.refused.append(f"{name}: also bound or deleted by module-level statement at line {node.lineno}")
    plan.statements.sort(key=lambda node: node.lineno)
    inside = {id(child) for node in plan.statements for child in ast.walk(node)}
    for node in plan.statements:
        extra = set(split_spec.bound_names(node)) - moving
        if extra:
            plan.refused.append(f"line {node.lineno} also binds {', '.join(sorted(extra))}, which the section does not list")
    for node in ast.walk(tree):
        if isinstance(node, ast.Global) and id(node) not in inside:
            for name in sorted(set(node.names) & moving):
                plan.refused.append(f"{name}: code that stays in pdfmd.py rebinds it with `global` (line {node.lineno}): "
                                    "it is state and stays")

    imports = top_level_imports(tree)
    tests = sorted((root / "tests").glob("*.py"))
    patched = split_spec.test_patches(tests, moving)
    rebound_by_tests = {name for name, places in patched.items()
                        if any(place.split(" ", 1)[1] in REBINDING for place in places)}
    declared_anywhere = {name for node in ast.walk(tree) if isinstance(node, ast.Global) for name in node.names}
    pdfmd_names = (set(where) | declared_anywhere | table_entries(tree)
                   | {name for node in tree.body for name in split_spec.nested_bindings(node)})
    for_package = {name for name, node in imports.items()
                   if not (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pdfmd"))
                   and name not in rebound_by_tests
                   and name not in declared_anywhere
                   and not any(name in module_changes(other) for other in tree.body
                               if not isinstance(other, (ast.Import, ast.ImportFrom)))}
    staying = (pdfmd_names | set(imports)) - moving - for_package
    core_read: set[str] = set()

    for statement in plan.statements:
        label = ", ".join(split_spec.bound_names(statement))
        uses, scopes = name_uses(statement)
        if any("core" in scope.bound for scope in scopes):
            plan.refused.append(f"{label}: has a local or a parameter named `core`")
        for cls in (node for node in ast.walk(statement) if isinstance(node, ast.ClassDef)):
            bound = scope_of(cls).bound
            for part in cls.body:
                class_uses, _ = name_uses(part)
                for use in class_uses:
                    if use.eager and use.resolved == "global" and isinstance(use.node.ctx, ast.Load) \
                            and use.node.id in bound:
                        plan.refused.append(f"{label}: ambiguous class-body read of {use.node.id} at line "
                                            f"{use.node.lineno}; rewrite it by hand")
        replaced: set[int] = set()
        state_written: set[str] = set()
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "vars" and not node.args:
                plan.refused.append(f"{label}: calls vars() at line {node.lineno} (pdfmd.py's own namespace; decide by hand)")
            elif is_sys_modules_name(node):
                if node.lineno != node.end_lineno:
                    plan.refused.append(f"{label}: sys.modules[__name__] over several lines at line {node.lineno}")
                plan.edits[id(node)] = "core"
                replaced |= {id(child) for child in ast.walk(node)}
            elif isinstance(node, ast.Global):
                staying_here = [name for name in node.names if name not in moving]
                state_written.update(staying_here)
                if staying_here:
                    plan.globals_kept[id(node)] = [name for name in node.names if name in moving]
                for name in node.names:
                    if name in moving and name in rebound_by_tests:
                        plan.refused.append(f"{label}: rebinds {name}, which moves and which tests patch on pdfmd")
        for node in ast.walk(statement):          # a state write `core.X` cannot spell
            bound = None
            if isinstance(node, ast.NamedExpr):
                bound = node.target.id
            elif isinstance(node, ast.ExceptHandler) or isinstance(node, (ast.MatchAs, ast.MatchStar)):
                bound = node.name
            elif isinstance(node, ast.alias):
                bound = node.asname or node.name.split(".")[0]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound = node.name
            elif isinstance(node, ast.MatchMapping):
                bound = node.rest
            if bound in state_written:
                plan.refused.append(f"{label}: binds the state {bound} (line {node.lineno}) in a way `core.{bound}` cannot "
                                    "spell; rewrite it by hand")
        for use in uses:
            node, name = use.node, use.node.id
            if id(node) in replaced or use.resolved != "global":
                continue
            store = not isinstance(node.ctx, ast.Load)
            if name == "__file__" and not store:
                plan.edits[id(node)] = "core.__file__"
            elif name in SELF_REFUSED:
                plan.refused.append(f"{label}: uses {name} at line {node.lineno} (pdfmd.py's own; decide by hand)")
            elif name in moving:
                if name in rebound_by_tests and not store:
                    if use.eager:
                        plan.refused.append(f"{label}: reads {name} when the module loads (line {node.lineno}), and tests "
                                            "patch it on pdfmd")
                    else:
                        plan.edits[id(node)] = f"core.{name}"
                        core_read.add(name)
            elif name in for_package:
                if store:
                    plan.refused.append(f"{label}: rebinds the imported name {name} at line {node.lineno}")
                else:
                    plan.imports[name] = import_line(imports[name], name)
            elif name in staying:
                if use.eager:
                    plan.refused.append(f"{label}: reads {name} when the module loads (line {node.lineno}): core cannot "
                                        "serve it then; import it, move it too, or rewrite the statement by hand")
                else:
                    plan.edits[id(node)] = f"core.{name}"
            elif not hasattr(builtins, name):
                plan.notes.append(f"{label}: {name} (line {node.lineno}) is not a pdfmd name or a builtin; left as it is")

    # who reads the moved names from outside the move
    bare: dict[str, list[tuple[int, bool]]] = {}
    real_binding: set[str] = set()
    for node in tree.body:
        if id(node) in inside:
            continue
        uses, _ = name_uses(node)
        direct_calls = {id(child.func) for child in ast.walk(node) if isinstance(child, ast.Call)}
        for use in uses:
            if use.resolved == "global" and use.node.id in moving and isinstance(use.node.ctx, ast.Load) \
                    and id(use.node) not in direct_calls:
                real_binding.add(use.node.id)
            if use.resolved == "global" and use.node.id in moving and isinstance(use.node.ctx, ast.Load):
                bare.setdefault(use.node.id, []).append((use.node.lineno, use.eager))
    for name in sorted(bare):
        eager_lines = [line for line, eager in bare[name] if eager]
        function = isinstance(where[name][0], (ast.FunctionDef, ast.AsyncFunctionDef))
        if at_start and (eager_lines or not function or name in real_binding):
            plan.at_start[name] = min(line for line, _ in bare[name])
        elif eager_lines:
            plan.refused.append(f"{name}: code that stays in pdfmd.py reads it when pdfmd.py loads (line {eager_lines[0]}): "
                                f"bind it with a plain `from {key} import {name}` by hand (the package then loads at start)")
        elif function and name in real_binding:
            plan.refused.append(f"{name}: staying code needs the real object (attributes or identity); "
                                "use --import-at-start or bind it by hand")
        elif function:
            plan.stand_ins.append(name)
        else:
            plan.refused.append(f"{name}: code that stays in pdfmd.py reads it bare (line {bare[name][0][0]}) and it is "
                                "not a function, so a stand-in cannot serve it; decide by hand")
    outside: set[str] = set(core_read) | (set(patched) & moving)
    texts = [path.read_text(encoding="utf-8", errors="replace") for path in tests]
    texts += [path.read_text(encoding="utf-8", errors="replace") for path in sorted((root / "lib").rglob("*.py"))
              if not GENERATED & set(path.relative_to(root).parts)]
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        texts.append(pyproject.read_text(encoding="utf-8").replace("pdfmd:", "pdfmd."))    # console entry points
    every = "\n".join(texts)
    exported = next((node.value for node in tree.body if isinstance(node, ast.Assign)
                     and getattr(node.targets[0], "id", None) == "__all__"), None)
    api = {element.value for element in getattr(exported, "elts", []) if isinstance(element, ast.Constant)}
    for name in moving:
        if re.search(r"\b(?:pdfmd|core)\.%s\b" % re.escape(name), every) or name in api:
            outside.add(name)
    plan.table = sorted(outside - set(plan.stand_ins) - set(plan.at_start),
                        key=lambda name: where[name][0].lineno if name in where else 0)
    served = set(plan.table) | set(plan.stand_ins) | set(plan.at_start)
    for statement in plan.statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Global):
                for name in sorted(set(node.names) & moving & served):
                    plan.refused.append(f"{name}: moved code rebinds an exported name at line {node.lineno}; it is state")
    plan.notes = list(dict.fromkeys(plan.notes))
    return plan, source, tree


# ---------------------------------------------------------------------------------------------------- the text
def comment_start(lines: list[str], start: int, previous_end: int) -> int:
    """The first line (1-based) of the comment block right above line ``start`` (no blank line between)."""
    line = start
    while line - 1 > previous_end and lines[line - 2].startswith("#"):
        line -= 1
    return line


def rewritten_block(plan: Plan, statement: ast.stmt, lines: list[str], first: int) -> str:
    """Lines ``first``..end of ``statement`` with the plan's edits applied (ast's columns are UTF-8 byte offsets)."""
    edits: dict[int, list[tuple[int, int, str]]] = {}
    dropped: set[int] = set()
    for node in ast.walk(statement):
        replacement = plan.edits.get(id(node))
        if replacement is not None:
            edits.setdefault(node.lineno, []).append((node.col_offset, node.end_col_offset, replacement))
        if id(node) in plan.globals_kept:
            kept = plan.globals_kept[id(node)]
            line = lines[node.lineno - 1].encode("utf-8")
            before, after = line[:node.col_offset], line[node.end_col_offset:].strip()
            if node.lineno != node.end_lineno or before.strip() or (after and not after.startswith(b"#")):
                plan.refused.append(f"line {node.lineno}: a `global` statement that shares its line; rewrite it by hand")
            elif kept:
                edits.setdefault(node.lineno, []).append((node.col_offset, node.end_col_offset, f"global {', '.join(kept)}"))
            else:
                dropped.add(node.lineno)
    out: list[str] = []
    for number in range(first, statement.end_lineno + 1):
        if number in dropped:
            continue
        line = lines[number - 1]
        if number in edits:
            data = line.encode("utf-8")
            for start, end, replacement in sorted(edits[number], reverse=True):
                data = data[:start] + replacement.encode("utf-8") + data[end:]
            line = data.decode("utf-8")
        out.append(line)
    return "\n".join(out)


def substituted(node, plan: Plan):
    """A new tree: ``node`` with the plan's substitutions (the original, whose node ids key the plan, is left alone)."""
    if isinstance(node, list):
        out = []
        for item in node:
            if isinstance(item, ast.Global) and id(item) in plan.globals_kept:
                if plan.globals_kept[id(item)]:
                    out.append(ast.Global(plan.globals_kept[id(item)]))
                continue
            out.append(substituted(item, plan))
        return out
    if not isinstance(node, ast.AST):
        return node
    replacement = plan.edits.get(id(node))
    if replacement == "core" and isinstance(node, ast.Subscript):
        return ast.Name("core", ast.Load())
    if replacement is not None and isinstance(node, ast.Name):
        return ast.Attribute(ast.Name("core", ast.Load()), replacement.split(".", 1)[1], type(node.ctx)())
    return type(node)(**{name: substituted(value, plan) for name, value in ast.iter_fields(node)})


def module_header(plan: Plan) -> str:
    docstring = (f'"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `{plan.key}`). pdfmd\'s own helpers, settings and\n'
                 'state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""\n')
    plain = sorted({line for line in plan.imports.values() if line.startswith("import ")}, key=str.lower)
    joined: dict[str, list[str]] = {}
    for line in plan.imports.values():
        if line.startswith("from "):
            module, _, spelled = line[len("from "):].partition(" import ")
            joined.setdefault(module, []).append(spelled)
    imports = plain + [f"from {module} import {', '.join(sorted(set(names), key=str.lower))}"
                       for module, names in sorted(joined.items())]
    uses_core = any(replacement.startswith("core") for replacement in plan.edits.values())
    return "\n".join([docstring, "from __future__ import annotations", "", *imports, *([""] if imports else []),
                      *(["from pdfmd_base import core", ""] if uses_core else []), "", ""])


def table_lines(key: str, names: list[str], width: int = 124) -> list[str]:
    """`names("key", "a b c")`, wrapped as implicitly joined strings (each piece but the last ends with a space)."""
    head = f'names("{key}", "'
    pieces: list[list[str]] = [[]]
    for name in names:
        if pieces[-1] and len(head) + len(" ".join(pieces[-1] + [name])) + 3 > width:
            pieces.append([])
        pieces[-1].append(name)
    lines = [head + " ".join(pieces[0])]
    for piece in pieces[1:]:
        lines[-1] += ' "'
        lines.append(" " * (len(head) - 1) + '"' + " ".join(piece))
    lines[-1] += '")'
    return lines


def apply(plan: Plan, source: str, tree: ast.Module, out: Path, root: Path) -> list[str]:
    """Write the new pdfmd.py and the module under ``out`` (``root`` for a move in place); the files written, or [] when
    the plan is refused on the way (the self-check, a `global` sharing its line, a clash in an existing module)."""
    lines = source.split("\n")
    previous_end: dict[int, int] = {}
    last_end = 0
    for node in tree.body:
        previous_end[id(node)] = last_end
        last_end = node.end_lineno
    blocks: list[str] = []
    removed: list[tuple[int, int]] = []
    for statement in plan.statements:
        first = comment_start(lines, split_spec.start_line(statement), previous_end[id(statement)])
        if first < split_spec.start_line(statement):
            plan.carried.append(f"{', '.join(split_spec.bound_names(statement))}: {split_spec.start_line(statement) - first} "
                                f"comment lines from line {first}: {lines[first - 1][:70]}")
        block = rewritten_block(plan, statement, lines, first)
        blocks.append(block)
        removed.append((first, statement.end_lineno))
        try:
            check = ast.parse(block).body
        except SyntaxError as error:
            check = [error]
        if len(check) != 1 or not isinstance(check[0], ast.AST) or ast.dump(check[0]) != ast.dump(substituted(statement, plan)):
            plan.refused.append(f"{', '.join(split_spec.bound_names(statement))}: the self-check failed (the written text "
                                "does not parse to the original with the substitutions)")
    if plan.refused:
        return []

    anchor = None                            # the table line goes after the last `names(...)`, else DEFERRED_NAMES.update
    for wanted in ("names", "update"):
        for node in tree.body:
            call = node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
            if call is None:
                continue
            if wanted == "names" and isinstance(call.func, ast.Name) and call.func.id == "names":
                anchor = node
            elif (wanted == "update" and isinstance(call.func, ast.Attribute) and call.func.attr == "update"
                  and isinstance(call.func.value, ast.Name) and call.func.value.id == "DEFERRED_NAMES"):
                anchor = node
        if anchor is not None:
            break
    added = (table_lines(plan.key, plan.table) if plan.table else []) + \
        [f'{name} = deferred("{plan.key}", "{name}")' for name in plan.stand_ins]
    edits: list[tuple[int, int, list[str]]] = [(start, end, []) for start, end in removed]
    if added:
        if anchor is None:
            plan.refused.append("pdfmd.py has no `names(...)` or `DEFERRED_NAMES.update(...)` line to put the table after")
            return []
        if any(start <= anchor.end_lineno <= end for start, end in removed):
            plan.refused.append("the table's anchor line is inside the move")
            return []
        edits.append((anchor.end_lineno + 1, anchor.end_lineno, added))
    if plan.at_start:                        # right above the first top-level statement that needs one, with its comments
        first_use = min(plan.at_start.values())
        holder = next(node for node in tree.body if split_spec.start_line(node) <= first_use <= node.end_lineno)
        at = comment_start(lines, split_spec.start_line(holder), previous_end[id(holder)])
        if any(start <= at <= end for start, end in removed):
            plan.refused.append(f"the first statement that needs {', '.join(sorted(plan.at_start))} is inside the move")
            return []
        edits.append((at, at - 1, [f"from {plan.key} import {', '.join(sorted(plan.at_start, key=str.lower))}  # noqa: E402", ""]))
    new_lines = list(lines)
    for start, end, replacement in sorted(edits, reverse=True):
        new_lines[start - 1:end] = replacement
        if not replacement:                  # where a block left: at most two blank lines
            before = 0
            while start - 2 - before >= 0 and not new_lines[start - 2 - before].strip():
                before += 1
            after = 0
            while start - 1 + after < len(new_lines) and not new_lines[start - 1 + after].strip():
                after += 1
            del new_lines[start - 1:start - 1 + max(0, min(after, before + after - 2))]
    text = "\n".join(new_lines)
    ast.parse(text)

    existing = plan.target if plan.target.exists() else None
    body = "\n\n\n".join(blocks) + "\n"
    if existing is None:
        module = module_header(plan) + body
    else:
        module = existing.read_text(encoding="utf-8")
        present = ast.parse(module)
        have = {alias.asname or alias.name.split(".")[0] for node in present.body if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names} | {name for node in present.body for name in split_spec.bound_names(node)}
        clash = sorted(plan.moving & have)
        if clash:
            plan.refused.append(f"{plan.target.relative_to(root).as_posix()} already binds {', '.join(clash)}")
            return []
        required = dict(plan.imports)
        if any(replacement.startswith("core") for replacement in plan.edits.values()):
            required["core"] = "from pdfmd_base import core"
        for name, line in sorted(required.items()):
            bindings = [node for node in present.body if name in module_changes(node)]
            if bindings and any(not isinstance(node, (ast.Import, ast.ImportFrom))
                                or import_line(node, name) != line for node in bindings):
                plan.refused.append(f"{plan.target.relative_to(root).as_posix()}: incompatible dependency binding "
                                    f"{name}; requires {line}")
        if plan.refused:
            return []
        missing = [line for name, line in sorted(plan.imports.items()) if name not in have]
        if "core" not in have and any(replacement.startswith("core") for replacement in plan.edits.values()):
            missing.append("from pdfmd_base import core")
        if missing:
            ends = [node.end_lineno for node in present.body if isinstance(node, (ast.Import, ast.ImportFrom))]
            docstring = present.body[0].end_lineno if present.body and isinstance(present.body[0], ast.Expr) else 0
            module_lines = module.split("\n")
            at = max(ends) if ends else docstring
            module_lines[at:at] = missing
            module = "\n".join(module_lines)
        module = module.rstrip("\n") + "\n\n\n" + body
    ast.parse(module)
    written = []
    for relative, content in (("pdfmd.py", text), (plan.target.relative_to(root).as_posix(), module)):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(relative)
    return written


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        raise SystemExit("split_move.py needs Python 3.12 or later (the positions of names inside f-strings)")
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("package", help="a section's key: pdfmd_x, or pdfmd_x.role")
    parser.add_argument("--sections", type=Path, help="read the section from this file instead of SPLIT.md")
    parser.add_argument("--phase", type=int, choices=(1, 2))
    parser.add_argument("--root", type=Path, default=ROOT, help="the checkout to move in (default: this script's)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and check it; write nothing")
    parser.add_argument("--out", type=Path, help="write pdfmd.py and the module under this folder instead of in place")
    parser.add_argument("--import-at-start", action="store_true",
                        help="bind what staying code needs when pdfmd.py loads with a plain import (the package loads at start)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    text = args.sections.read_text(encoding="utf-8") if args.sections else None
    new_package = not (root / "lib" / args.package.partition(".")[0]).is_dir()
    plan, source, tree = plan_move(args.package, root, text, args.phase, args.import_at_start)
    print(f"# {plan.key}: {len(plan.statements)} statements -> {plan.target.relative_to(root).as_posix()}")
    print(f"core.NAME rewrites: {len(plan.edits)}; `global` lines changed: {len(plan.globals_kept)}")
    print("imports: " + ("; ".join(sorted(plan.imports.values())) or "none"))
    print("table: " + (" ".join(plan.table) or "none"))
    print("stand-ins: " + (" ".join(plan.stand_ins) or "none"))
    if plan.at_start:
        print("imported at start: " + " ".join(sorted(plan.at_start)))
    for note in plan.notes:
        print(f"note: {note}")
    written: list[str] = []
    if not plan.refused:
        if args.dry_run:
            with tempfile.TemporaryDirectory(prefix="split-move-") as scratch:
                apply(plan, source, tree, Path(scratch), root)
        else:
            written = apply(plan, source, tree, args.out.resolve() if args.out else root, root)
    if plan.refused:
        print("\nREFUSED (nothing written):")
        for reason in plan.refused:
            print(f"- {reason}")
        return 2
    print("self-check: every moved statement parses to the original with the substitutions")
    for carried in plan.carried:
        print(f"comments carried (check they belong to the definition): {carried}")
    if written:
        print("written: " + ", ".join(written) + (f" (under {args.out})" if args.out else ""))
    if new_package:
        print("A new package: add it to pyproject.toml (packages, package-dir) and to PACKAGES in scripts/build_zipapp.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

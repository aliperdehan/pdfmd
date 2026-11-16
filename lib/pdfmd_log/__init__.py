"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_log`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from pdfmd_base import core


# v3.31.41 (entry 3ea): how a path is written in a message. `auto`: relative to the working folder (up to PATH_UP `..` steps above
# it), else `~/...` under the home folder, else absolute; `relative`: the same without `~`; `home`: `~/...` under the home
# folder, else absolute; `full`: absolute. --path-style / --path-up, `options: {path-style, path-up}` of the config and of a folder's
# settings (pdfmd --setup). -v/--verbose gives `full` unless --path-style is given.
PATH_STYLES = ("auto", "relative", "home", "full")


DISPLAY_ALIAS: dict[Path, Path] = {}


def path_style_settings(requested: str | None, requested_up: int | None = None, document: Path | None = None,
                        verbose: bool = False) -> tuple[str, int]:
    """(style, steps up) of this run: --path-style / --path-up, else `options.path-style` / `options.path-up` (the config, then the
    folder settings above ``document``, the nearest winning), else `auto` and 2. ``verbose`` (-v, --debug) makes the style `full`
    unless --path-style was given: the detail asked for is the whole path."""
    options = core.config_options(document)
    style = requested or ("full" if verbose else str(options.get("path-style") or "auto").strip().casefold())
    if style not in PATH_STYLES:
        raise SystemExit(f"unknown path-style {style!r}. Valid: {', '.join(PATH_STYLES)}")
    up = requested_up if requested_up is not None else options.get("path-up", core.PATH_UP)
    try:
        up = int(up)
    except (TypeError, ValueError):
        up = -1
    if up < 0:
        raise SystemExit(f"path-up must be a whole number of folders (0 or more), not {up if requested_up is not None else options.get('path-up')!r}")
    return style, up


def display_path(path: Path, up: int | None = None) -> str:
    """Format `path` for a user-facing AUTO/CMD message.

    Relative to the current working directory by default (SHOW_FULL_PATHS
    False, the default -- see --full-paths), which is what a caller
    actually invoking pdfmd from a project directory wants to read; falls
    back to the absolute path when `path` isn't under cwd at all (a system
    temp file, e.g.) since a relative path can't reach it, or when
    SHOW_FULL_PATHS is True (--full-paths, for a copy-pasteable absolute
    path -- e.g. to hand to another tool, or when cwd itself is ambiguous
    in a script's own log). Since v3.31.41 a folder above the working folder is written with `..` (up to PATH_UP steps, or ``up``)
    and a path under the home folder as ``~/...``, per PATH_STYLE.
    """
    if core.DISPLAY_ALIAS:                             # an ebook's Markdown in a scratch folder is shown as the book (v3.29.1)
        try:
            path = core.DISPLAY_ALIAS.get(path) or core.DISPLAY_ALIAS.get(path.resolve()) or path
        except OSError:
            pass
    if core.SHOW_FULL_PATHS or core.PATH_STYLE == "full":
        return str(path)
    # The folder is resolved, the file itself is not: a symlink (`metadata/metadata.yaml` pointing at
    # a shared house-style file) is shown where it sits, not where it leads. The working folder is resolved too:
    # on Windows it can be in 8.3 short form (`RUNNER~1`) while the file's resolves to the long one.
    try:
        here = Path.cwd().resolve()
    except OSError:
        here = Path.cwd()
    try:
        located = path.parent.resolve() / path.name
    except OSError:
        return str(path)
    candidates = [located]
    try:
        candidates.append(path.resolve())
    except OSError:
        pass
    if core.PATH_STYLE != "home":
        for candidate in candidates:
            try:
                return str(candidate.relative_to(here))
            except ValueError:
                pass
        for candidate in candidates:
            try:
                relative = os.path.relpath(candidate, here)
            except ValueError:                        # another drive on Windows
                continue
            ups = 0
            for part in Path(relative).parts:
                if part != "..":
                    break
                ups += 1
            if ups <= (core.PATH_UP if up is None else up):
                return relative
    if core.PATH_STYLE != "relative":
        try:
            home = Path.home().resolve()
        except (OSError, RuntimeError):
            home = None
        if home is not None:
            for candidate in candidates:
                try:
                    return os.path.join("~", *candidate.relative_to(home).parts)
                except ValueError:
                    pass
    return str(path)


class AutoLog:
    """What pdfmd decided for the build in hand, shown in three lines (v3.28.16) rather than one a decision.

    ``FOUND`` is what it picked up from the folder (metadata files, a preamble, a Lua filter, the parts),
    ``DEFAULTS`` what it applied because nothing said otherwise (the global metadata of ``pdfmd --setup``, the
    margin, the fonts, the packages it adds), and ``AUTO: KINDS`` the decisions that have no short form. A line is
    cut at ``WIDTH`` characters ("+N more (--verbose)"): the screen is not for the catalogue. ``--verbose`` prints
    each decision with its reason, as it happens, as before. In a batch a line equal to the one before it is not
    printed again."""

    WIDTH = 110                          # the width of a line when the output is not a terminal
    HEADINGS = ("FOUND", "DEFAULTS")
    # A decision that is one of a kind per build (the later one replaces the earlier); the others are listed each
    ONE_OF = frozenset({"PARTS", "MARGIN", "MAINFONT", "MATHFONT", "MONOFONT"})
    # The order a line lists its items in, whichever was found first: the files, then the parts; the global
    # metadata, then margin, fonts, packages
    RANK = {"YAML": 0, "TEX": 1, "LUA": 2, "PARTS": 3, "GLOBAL": 0, "MARGIN": 1, "MAINFONT": 2, "MATHFONT": 2.5, "MONOFONT": 3,
            "TEXPACKAGES": 4, "TITLE": 5, "TABLEWIDTH": 6, "SETTINGS": 0.5}

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], tuple[int, str]] = {}
        self.other: list[str] = []
        self.shown: dict[str, str] = {}
        self.dedupe = False
        self.quiet = False

    def snapshot(self) -> tuple[dict, list, dict]:
        return dict(self.items), list(self.other), dict(self.shown)

    def restore(self, saved: tuple[dict, list, dict]) -> None:
        self.items, self.other, self.shown = dict(saved[0]), list(saved[1]), dict(saved[2])

    def reset(self, dedupe: bool = False) -> None:
        self.items.clear()
        self.other.clear()
        self.shown.clear()
        self.dedupe = dedupe

    @staticmethod
    def classify(kind: str, detail: str) -> tuple[str, str] | None:
        """(heading, short text) of a decision that has a short form, from the words it was announced with."""
        if kind == "PARTS":
            found = re.search(r"(\d+) (more file|part)s?\b", detail)
            return (("FOUND", f"{found.group(1)} {found.group(2)}{'s' if found.group(1) != '1' else ''}") if found else None)
        if kind == "LUA":
            return "FOUND", Path(detail).name or detail
        if kind == "MARGIN":
            found = re.search(r"no geometry/margin set; using geometry:margin=(\S+)", detail)
            return ("DEFAULTS", f"margin {found.group(1)}") if found else None
        if kind == "MAINFONT":
            found = (re.search(r"no mainfont set; using (.+)$", detail)
                     or re.search(r": (.+?) instead of ", detail))
            return ("DEFAULTS", f"font {found.group(1)}") if found else None
        if kind == "MATHFONT":
            found = re.search(r"no mathfont set; using (.+?) to go with ", detail)
            return ("DEFAULTS", f"math in {found.group(1)}") if found else None
        if kind == "MONOFONT":
            found = re.search(r"no monofont set; using (.+?) on ", detail)
            return ("DEFAULTS", f"code in {found.group(1)}") if found else None
        if kind == "TEXPACKAGES":
            found = re.match(r"loads (.+?) unless the preamble does", detail)
            return ("DEFAULTS", f"packages {found.group(1)}") if found else None
        if kind == "TITLE":
            return "DEFAULTS", "title from heading"
        if kind == "TABLEWIDTH":
            found = re.search(r"(\d+) wide tables?", detail)
            count = int(found.group(1)) if found else 1
            return "DEFAULTS", f"balanced {count} wide table{'s' if count != 1 else ''}"
        return None

    def record(self, kind: str, detail: str, verbose: bool, heading: str | None = None,
               short: str | None = None) -> None:
        """One decision: printed at once with ``verbose``, else kept for ``flush``."""
        if verbose:
            print(f"AUTO {kind}  {detail}")
            return
        core.record_note(f"AUTO {kind}  {detail}")           # the record has it whatever --verbose said
        if heading is None:
            found = self.classify(kind, detail)
            heading, short = found if found else (None, None)
        if heading is None:
            if kind not in self.other:
                self.other.append(kind)
            return
        self.items[(heading, kind if kind in self.ONE_OF else short)] = (self.RANK.get(kind, 9), short)

    @staticmethod
    def file_line(kind: str, path: Path) -> str:
        """The AUTO line of a file pdfmd picked up."""
        if kind == "YAML" and core.is_global_metadata(path):
            return (f"AUTO {kind}  {core.display_path(path)}  "
                    + ("(the global metadata of pdfmd --setup)" if core.preset_name(path) == "default"
                       else f"(the preset {core.preset_name(path)} of pdfmd --setup)"))
        return f"AUTO {kind}  {core.display_path(path)}"

    def record_file(self, kind: str, path: Path, verbose: bool) -> None:
        """A file pdfmd picked up (AUTO YAML / AUTO TEX): FOUND, but the global metadata is a default."""
        line = self.file_line(kind, path)
        if verbose:
            print(line)
            return
        core.record_note(line)
        if kind == "YAML" and core.is_global_metadata(path):
            self.items[("DEFAULTS", "global")] = (self.RANK["GLOBAL"], "global metadata" if core.preset_name(path) == "default"
                                                  else f"preset {core.preset_name(path)}")
        else:
            self.items[("FOUND", f"{kind} {path}")] = (self.RANK[kind], core.display_path(path))

    def width(self) -> int:
        """The line width: the terminal's own when stdout is one (v3.28.18), else ``WIDTH``."""
        try:
            if sys.stdout.isatty():
                return max(60, shutil.get_terminal_size((self.WIDTH, 24)).columns)
        except (OSError, ValueError, AttributeError):
            pass
        return self.WIDTH

    @staticmethod
    def grouped(parts: list[str]) -> list[str]:
        """``metadata/a.yaml``, ``metadata/b.tex`` -> ``metadata: a.yaml + b.tex`` (v3.28.18): files that share a folder
        are listed under it once, in the place of the first. A folder with one file keeps its path."""
        folders: dict[str, list[str]] = {}
        for part in parts:
            if re.search(r"[/\\]", part):
                folder, name = re.split(r"[/\\](?=[^/\\]*$)", part)
                folders.setdefault(folder, []).append(name)
        done: set[str] = set()
        result: list[str] = []
        for part in parts:
            if re.search(r"[/\\]", part):
                folder, _ = re.split(r"[/\\](?=[^/\\]*$)", part)
                if len(folders[folder]) > 1:
                    if folder not in done:
                        done.add(folder)
                        result.append(f"{folder}: " + " + ".join(folders[folder]))
                    continue
            result.append(part)
        return result

    def fit(self, heading: str, parts: list[str]) -> str:
        prefix = f"{heading:<10}"
        line = prefix + ", ".join(parts)
        width = self.width()
        if len(line) <= width:
            return line
        for count in range(len(parts) - 1, 0, -1):
            cut = prefix + ", ".join(parts[:count]) + f", +{len(parts) - count} more (--verbose)"
            if len(cut) <= width:
                return cut
        return prefix + parts[0] + f", +{len(parts) - 1} more (--verbose)"

    def flush(self) -> None:
        """Print what was recorded since the last flush, FOUND, DEFAULTS, then the decisions without a short form."""
        if self.quiet:
            self.items.clear()
            self.other.clear()
            return
        for heading in self.HEADINGS:
            parts = [text for _, text in sorted((value for (group, _), value in self.items.items() if group == heading),
                                                key=lambda value: value[0])]
            if parts:
                if heading == "FOUND" and str(core.config_options().get("found-style", "group")).strip().casefold() != "path":
                    parts = self.grouped(parts)
                line = self.fit(heading, parts)
                if not (self.dedupe and self.shown.get(heading) == line):
                    print(line)
                self.shown[heading] = line
        if self.other:
            line = f"AUTO: {' '.join(self.other)}. Use --verbose to see in full"
            if not (self.dedupe and self.shown.get("AUTO") == line):
                print(line)
            self.shown["AUTO"] = line
        self.items.clear()
        self.other.clear()


AUTO_LOG = AutoLog()


def under_home(path: Path) -> str:
    """``path`` with the home folder written as ``~`` (a record path is printed, and pasted into reports)."""
    text, home = str(path), str(Path.home())
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def failure_text(error: BaseException) -> str:
    if isinstance(error, SystemExit):
        return str(error.code) if isinstance(error.code, str) else f"exit {error.code}"
    if isinstance(error, KeyboardInterrupt):
        return "interrupted"
    return f"{type(error).__name__}: {error}"


def open_file(path: Path) -> None:
    """Open a finished file with the platform's default viewer, for --open."""
    if sys.platform == "win32":
        try:
            os.startfile(path)  # Windows' own "open with default app"
        except OSError as error:
            print(f"WARN  --open: could not open {path}: {error}", file=sys.stderr)
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open" if sys.platform.startswith("linux") else None
    if opener is None or not core.which(opener):
        print(f"WARN  --open: no '{opener or 'file opener'}' found for this platform; "
              f"open {path} yourself", file=sys.stderr)
        return
    try:
        subprocess.run([opener, str(path)])
    except OSError as error:
        print(f"WARN  --open: could not open {path}: {error}", file=sys.stderr)


def cmd_part(text: str, quote: bool = True) -> str:
    """One word of the CMD line. The line is a command to run again, so a path is never written with `..` (it would mean
    something else from another folder): under the working folder it is relative, under the home folder ``~/...`` (v3.31.41,
    entry 3ea; the shell expands the tilde, so it stays outside the quotes), else absolute, per `path-style`. Words that are
    not absolute paths are untouched."""
    if not os.path.isabs(text):
        return shlex.quote(text) if quote else text
    shown = core.display_path(Path(text), up=0)
    if shown == "~" or shown.startswith(("~/", "~\\")):
        rest = shown[2:].replace(os.sep, "/")
        return "~" if shown == "~" else "~/" + (shlex.quote(rest) if quote else rest)
    return shlex.quote(shown) if quote else shown


def log_cmd(cmd: list, cwd: Path, verbose: bool) -> None:
    """Print the exact subprocess command about to run, under --verbose.

    Added 2026-09-16 after a real debugging session (the pdfmd.py table-
    width/nulabreport.lua interaction, see TABLE_WIDTH_LUA_FILTER's own
    comment) that would have taken a fraction of the time if --verbose had
    shown this from the start -- it previously only ever printed pdfmd's
    OWN "AUTO ..." decisions (which metadata/preamble/font it picked), never
    the actual command line those decisions built, so which lua-filters
    were passed and in what order was invisible without editing this file
    to find out by hand. shlex.quote so a copy-pasted line is directly
    re-runnable even when an argument has spaces (a metadata file path
    under a directory with one, for instance).
    """
    line = "CMD  " + " ".join(cmd_part(str(part)) for part in cmd) + f"  (cwd={cmd_part(str(cwd), quote=False)})"
    if not verbose:
        core.record_note(line)             # the record has it whatever --verbose said
        return
    print(line, file=sys.stderr)

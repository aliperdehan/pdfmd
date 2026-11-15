"""TeX self-repair (v3.33.218 on; queue item 2b): a broken TeX installation is mended for this run only.

An AI sandbox, a container or a fresh server shows the same few breakages again and again; pdfmd named the cause
(`tex_failure_cause`) and left the user to fix it. With the setting `tex-repair: auto` (the default; `off` keeps the old
behaviour exactly) the build mends what it can inside its own run: an engine skipped before it fails, a stand-in `.sty` on
TEXINPUTS, a scratch cache folder, an engine order. Every remedy that fires prints ONE `NOTE` naming what it did and why, and
`--strict` counts a repaired build as a warning (the lines are kept in `core.BUILD["repaired"]`, which `finish_build` reads).
No remedy changes the TeX installation, the user's cache or any file outside this run's temporary folders.

The six remedies (the notes of the maintainer's queue, 3fm and 3fo, are the design): luaotfload missing (lualatex is skipped,
`plan`), lmodern.sty missing, soul.sty missing with struck-out text, an unwritable TeX cache, a corrupt luaotfload database,
and Biber's stale unpack cache. Each is added with its own version and is described in the CHANGELOG.

What is found missing is asked of `kpsewhich` once per run for all the files (`installed`), with `article.cls` as a witness
that kpsewhich answers at all: no kpsewhich, no answer in time, a witness that is not found (a broken `texmf.cnf`) and MiKTeX
(which installs a missing package on the fly) all mean "unknown", and unknown means "present", so a healthy machine is never
mended by mistake.

`core` is the `pdfmd` module (lib/pdfmd_base); the names read here (`BUILD`, `config_options`, `display_path`,
`first_pdfmd_option`, `run_probe`, `which`) are read as `core.X` when the code runs. The module is loaded on first use
(`core.load_package("pdfmd_tex.repair")`), not at start.
"""

from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pdfmd_base import core

MODES = ("auto", "off")
# YAML reads a bare off/no as a boolean; on/yes are accepted too and mean auto
MODE_WORDS = {"auto": "auto", "on": "auto", "true": "auto", "yes": "auto", "off": "off", "false": "off", "no": "off"}

TEX_ENGINES = ("lualatex", "xelatex", "pdflatex")
# A file every TeX tree has (LaTeX's own base): found, kpsewhich answers; not found, its answer is not trusted (a file-format fact)
WITNESS = "article.cls"

PROBED: dict[str, bool | None] = {}      # file name -> found by kpsewhich (None: unknown); asked once per run
NOTED: set[str] = set()                  # the remedies whose NOTE was printed this run
# this build's: the mode in force, the document as a NOTE names it, the stand-in files each engine gets on TEXINPUTS
STATE: dict = {"mode": None, "label": "", "stubs": {}}

# The stand-in packages (file-format facts: what the package would define). They are written when an engine needs one, into
# this run's temporary folder, and put on TEXINPUTS AFTER the default path, so a real file always wins.
LMODERN_STUB = r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{lmodern}[2026/01/01 pdfmd stub: no-op, fonts come from fontspec]
"""
# soul's \st (strikeout) and \ul (underline), which Pandoc's template uses on every engine but LuaLaTeX, drawn with ulem when it is
# installed (`[normalem]`: \emph stays italic; not loaded again when the document loaded ulem first); soul's other commands print
# their argument, so a document that uses them still builds
SOUL_STUB = r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{soul}[2026/01/01 pdfmd stub: st and ul through ulem, the rest plain]
%ULEM%\DeclareRobustCommand*{\st}[1]{%STRIKE%}
\DeclareRobustCommand*{\ul}[1]{%UNDERLINE%}
\providecommand*{\hl}[1]{#1}
\providecommand*{\so}[1]{#1}
\providecommand*{\caps}[1]{#1}
\providecommand*{\sethlcolor}[1]{}
\providecommand*{\setstcolor}[1]{}
\providecommand*{\setulcolor}[1]{}
\providecommand*{\soulregister}[2]{}
"""
ULEM_LOAD = "\\@ifpackageloaded{ulem}{}{\\RequirePackage[normalem]{ulem}}\n"
STUBS = {"lmodern.sty": LMODERN_STUB, "soul.sty": SOUL_STUB}
# a struck-out or underlined text in a Markdown source: ~~text~~, <del>, <s>, <strike>, <u>, [text]{.underline} (what makes
# Pandoc's template load soul); a match inside code is a false alarm that costs a NOTE and a stand-in no engine reads
STRIKES = re.compile(r"(?<![~\\])~~(?=\S)[^~\n]+?(?<=\S)~~(?!~)|<(?:del|s|strike|u)[ >]|\{\.(?:underline|ul)\}", re.IGNORECASE)


def mode_word(value) -> str | None:
    if isinstance(value, bool):
        return "auto" if value else "off"
    return MODE_WORDS.get(str(value).strip().casefold()) if value is not None else None


def resolve_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """`tex-repair` of the document, its metadata files, its folders and the config (the first that says), else auto. A
    word that is neither is one WARN, and auto. Input that is not Markdown (a `.tex`, an office file) reads the config only."""
    try:
        if md_path.suffix.lower() in (".md", ".markdown"):
            value = core.first_pdfmd_option(md_path, metadata_files, "tex-repair")
        else:
            value = core.config_options().get("tex-repair")
    except Exception:          # noqa: BLE001 -- a document that cannot be read fails elsewhere, with its own message
        value = None
    if value is None:
        return "auto"
    word = mode_word(value)
    if word is None:
        print(f"WARN  {core.display_path(md_path)}: pdfmd-options.tex-repair {value!r} is not one of {', '.join(MODES)}; "
              "using auto", file=sys.stderr)
        return "auto"
    return word


def current_mode() -> str:
    """The mode of the build in progress (set by `plan`); outside a build, the config's."""
    if STATE["mode"] is None:
        try:
            return mode_word(core.config_options().get("tex-repair")) or "auto"
        except Exception:          # noqa: BLE001
            return "auto"
    return STATE["mode"]


def installed(names: tuple[str, ...]) -> dict[str, bool | None]:
    """Whether kpsewhich finds each of ``names`` (True, False, or None for unknown); one call for the names not asked yet."""
    todo = [name for name in names if name not in PROBED]
    if todo:
        answer: set[str] | None = None
        executable = core.which("kpsewhich") if sys.platform != "win32" else None
        if executable:
            done = core.run_probe([executable, WITNESS, *todo])
            if done is not None:
                found = {Path(line.strip()).name for line in (done.stdout or "").splitlines() if line.strip()}
                answer = found if WITNESS in found else None
        for name in todo:
            PROBED[name] = None if answer is None else name in answer
    return {name: PROBED[name] for name in names}


def missing(name: str) -> bool:
    """True only when kpsewhich answered and does not find ``name``."""
    return installed((name,))[name] is False


def unwritable_cache() -> list[str]:
    """Called when a run starts, by pdfmd's `provide_writable_places`, with TEXMFCACHE set in the environment: when none of its
    entries can be written (LuaTeX stops at once with `system : no writeable cache path`) it goes to a scratch folder of this
    run, and what was moved is returned for that function's one NOTE (and kept for --strict). Nothing is read from a
    document at that point, so only the config's `tex-repair` decides; nothing is moved without a TeX engine, and a value that
    uses kpathsea's braces is left alone. (A TEXMFVAR that cannot be written, or a home that cannot, was moved before.)"""
    entries = [Path(entry.removeprefix("!!")) for entry in os.environ.get("TEXMFCACHE", "").split(os.pathsep) if entry]
    if not entries or "{" in os.environ["TEXMFCACHE"] or any(core.folder_is_writable(entry) for entry in entries):
        return []
    try:
        if mode_word(core.config_options().get("tex-repair")) == "off":
            return []
    except Exception:          # noqa: BLE001 -- an unreadable config fails elsewhere, with its own message
        pass
    if not any(core.which(name) for name in ("lualatex", "xelatex", "pdflatex", "latexmk", "tectonic")):
        return []
    folder = core.temporary_place("texmf") / "texmf-cache"
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["TEXMFCACHE"] = str(folder)
    core.BUILD["repaired_run"].append("NOTE  tex-repair: TEXMFCACHE cannot be written, so this run keeps the TeX font cache in a "
                                      "temporary folder (LuaTeX's first run indexes the fonts again)")
    return ["the TeX font cache (TEXMFCACHE)"]


def stub_folder() -> Path:
    """The folder this run's stand-in files are written in (made once, removed when the run ends)."""
    return core.temporary_place("tex-stubs")


def write_stub(folder: Path, name: str, ulem: bool = True) -> Path:
    """The stand-in package ``name`` in ``folder`` (soul's draws with ulem when ``ulem``, else prints plain text)."""
    text = STUBS[name]
    if name == "soul.sty":
        text = (text.replace("%ULEM%", ULEM_LOAD if ulem else "")
                .replace("%STRIKE%", "\\sout{#1}" if ulem else "#1").replace("%UNDERLINE%", "\\uline{#1}" if ulem else "#1"))
    path = folder / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def texinputs_with(current: str | None, folder: Path) -> str:
    """TEXINPUTS that keeps ``current`` and the default path and ends with ``folder`` (an empty entry stands for the default)."""
    base = (current or "").rstrip(os.pathsep)
    return f"{base}{os.pathsep}{os.pathsep}{folder}" if base else f"{os.pathsep}{folder}"


def overlay(engine: str, base: dict | None = None) -> dict[str, str]:
    """The environment variables this build's remedies change for ``engine`` (empty: none), given the environment it would
    otherwise have (``base``, else the process's)."""
    if current_mode() == "off":
        return {}
    changes: dict[str, str] = {}
    names = STATE["stubs"].get(engine)
    if names:
        folder = stub_folder()
        for name, how in names.items():
            if not (folder / name).is_file():
                write_stub(folder, name, **how)
        changes["TEXINPUTS"] = texinputs_with((os.environ if base is None else base).get("TEXINPUTS"), folder)
    return changes


@contextmanager
def engine_environment(engine: str) -> Iterator[None]:
    """The process's environment with this build's remedies for ``engine`` while a command that inherits it runs (the
    Pandoc command of an engine, whose environment is built in several places)."""
    changes = overlay(engine)
    if not changes:
        yield
        return
    saved = {name: os.environ.get(name) for name in changes}
    os.environ.update(changes)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def engine_env(engine: str, env: dict | None) -> dict | None:
    """``env`` (None: the process's) with this build's remedies for ``engine``, for a command pdfmd starts itself; ``env``
    itself when nothing applies."""
    changes = overlay(engine, env)
    if not changes:
        return env
    return {**(os.environ if env is None else env), **changes}


def say(key: str, text: str) -> None:
    """The NOTE of the remedy ``key`` (printed once per run) and its line for --strict (once per build)."""
    line = f"NOTE  {STATE['label']}: tex-repair: {text}"
    if key not in NOTED:
        NOTED.add(key)
        print(line, file=sys.stderr)
    lines = core.BUILD.setdefault("repaired", [])
    if line not in lines:
        lines.append(line)


def struck_out(sources: list[Path]) -> bool:
    """Whether a Markdown source has text that Pandoc's template needs soul for (STRIKES)."""
    for source in sources:
        if source.suffix.lower() in (".md", ".markdown"):
            text = core.read_text_or_none(source)
            if text and STRIKES.search(text):
                return True
    return False


def plan(md_path: Path, metadata_files: list[Path], engines: list[str], reorder: bool = False) -> list[str]:
    """The engine chain of the build after the remedies that change it (called by lib/pdfmd_chain's plan_build, for a PDF
    build whose chain has a TeX engine). The chain is never left empty. ``reorder``: the chain is pdfmd's own (not pinned,
    not started with the engine that made the PDF), so an engine may go first."""
    STATE.update(mode=resolve_mode(md_path, metadata_files), label=core.display_path(md_path), stubs={})
    if STATE["mode"] == "off" or not any(engine in TEX_ENGINES for engine in engines):
        return engines
    chain = list(engines)
    pandoc_made = md_path.suffix.lower() != ".tex"          # a .tex of the user's is compiled as it is (the cases below are Pandoc's template)
    strikes = pandoc_made and any(engine in chain for engine in ("xelatex", "pdflatex")) and struck_out(core.BUILD.get("sources") or [md_path])
    installed(tuple(["luaotfload-main.lua"] * ("lualatex" in chain) + ["lmodern.sty"] * pandoc_made
                    + ["soul.sty", "ulem.sty", "lua-ul.sty", "luacolor.sty"] * strikes))      # one kpsewhich call
    # 1. luaotfload, LuaTeX's font loader, is missing: lualatex would fail whatever the document
    if "lualatex" in chain and len(chain) > 1 and missing("luaotfload-main.lua"):
        chain.remove("lualatex")
        say("luaotfload", f"luaotfload (LuaTeX's font loader) is not installed, so lualatex is skipped and {chain[0]} is tried "
                          "first (found with kpsewhich; this run only; `tex-repair: off` tries lualatex anyway)")
    # 2. lmodern.sty is missing, and Pandoc's template loads it for every LaTeX engine: xelatex and lualatex (fontspec sets
    # their fonts) load an empty stand-in; pdflatex needs the real fonts, so it is skipped when another engine can run
    if pandoc_made and missing("lmodern.sty"):
        standins = [engine for engine in ("xelatex", "lualatex") if engine in chain]
        for engine in standins:
            STATE["stubs"].setdefault(engine, {})["lmodern.sty"] = {}
        skipped = "pdflatex" in chain and len(chain) > 1
        if skipped:
            chain.remove("pdflatex")
        if standins or skipped:
            doing = []
            if standins:
                doing.append(" and ".join(standins) + (" use" if len(standins) > 1 else " uses")
                             + " an empty stand-in for it (fontspec sets the fonts)")
            if skipped:
                doing.append("pdflatex is skipped (it needs the real fonts)")
            say("lmodern", "lmodern.sty is not installed (Pandoc's LaTeX template loads it): " + "; ".join(doing)
                + " (this run only; `tex-repair: off` changes nothing)")
    # 3. soul.sty is missing and the text is struck out or underlined: LuaLaTeX draws it with lua-ul, so it goes first when the
    # chain may be reordered; xelatex and pdflatex get a stand-in soul.sty that draws it with ulem (plain text, and a WARN,
    # when ulem is missing too)
    if strikes and missing("soul.sty"):
        lines = []
        lua_ok = "lualatex" in chain and not missing("lua-ul.sty") and not missing("luacolor.sty")
        if reorder and lua_ok and chain[0] != "lualatex":
            chain.remove("lualatex")
            chain.insert(0, "lualatex")
            lines.append("lualatex goes first (its lua-ul draws the line)")
        ulem = not missing("ulem.sty")
        standins = [engine for engine in ("xelatex", "pdflatex") if engine in chain]
        for engine in standins:
            STATE["stubs"].setdefault(engine, {})["soul.sty"] = {"ulem": ulem}
        if standins:
            lines.append(" and ".join(standins) + (" use" if len(standins) > 1 else " uses") + " a stand-in soul.sty that "
                         + ("draws the line with ulem's \\sout and \\uline" if ulem else "prints the text plain"))
        if lines:
            say("soul", "soul.sty is not installed and the text is struck out or underlined: " + "; ".join(lines)
                + " (this run only; `tex-repair: off` changes nothing)")
        if standins and not ulem and "soul-plain" not in NOTED:
            NOTED.add("soul-plain")
            print(f"WARN  {STATE['label']}: tex-repair: soul.sty and ulem.sty are not installed, so struck-out text is printed "
                  "without its line (install soul: tlmgr install soul)", file=sys.stderr)
    return chain

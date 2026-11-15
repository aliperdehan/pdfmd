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

import sys
from pathlib import Path

from pdfmd_base import core

MODES = ("auto", "off")
# YAML reads a bare off/no as a boolean; on/yes are accepted too and mean auto
MODE_WORDS = {"auto": "auto", "on": "auto", "true": "auto", "yes": "auto", "off": "off", "false": "off", "no": "off"}

TEX_ENGINES = ("lualatex", "xelatex", "pdflatex")
# A file every TeX tree has (LaTeX's own base): found, kpsewhich answers; not found, its answer is not trusted (a file-format fact)
WITNESS = "article.cls"

PROBED: dict[str, bool | None] = {}      # file name -> found by kpsewhich (None: unknown); asked once per run
NOTED: set[str] = set()                  # the remedies whose NOTE was printed this run
STATE: dict = {"mode": None, "label": ""}   # this build's: the mode in force, the document as it is named in a NOTE


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


def say(key: str, text: str) -> None:
    """The NOTE of the remedy ``key`` (printed once per run) and its line for --strict (once per build)."""
    line = f"NOTE  {STATE['label']}: tex-repair: {text}"
    if key not in NOTED:
        NOTED.add(key)
        print(line, file=sys.stderr)
    lines = core.BUILD.setdefault("repaired", [])
    if line not in lines:
        lines.append(line)


def plan(md_path: Path, metadata_files: list[Path], engines: list[str]) -> list[str]:
    """The engine chain of the build after the remedies that change it (called by lib/pdfmd_chain's plan_build, for a PDF
    build whose chain has a TeX engine). The chain is never left empty."""
    STATE["mode"] = resolve_mode(md_path, metadata_files)
    STATE["label"] = core.display_path(md_path)
    if STATE["mode"] == "off" or not any(engine in TEX_ENGINES for engine in engines):
        return engines
    chain = list(engines)
    # 1. luaotfload, LuaTeX's font loader, is missing: lualatex would fail whatever the document
    if "lualatex" in chain and len(chain) > 1 and missing("luaotfload-main.lua"):
        chain.remove("lualatex")
        say("luaotfload", f"luaotfload (LuaTeX's font loader) is not installed, so lualatex is skipped and {chain[0]} is tried "
                          "first (found with kpsewhich; this run only; `tex-repair: off` tries lualatex anyway)")
    return chain

"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_flavours.markup`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from pdfmd_base import core


try:
    from pdfmd_flavours import PRESETS as FLAVOUR_PRESETS, WORDS as FLAVOUR_WORDS
except ImportError:      # a copy of pdfmd.py without its packages: strict Pandoc and nothing else
    FLAVOUR_PRESETS, FLAVOUR_WORDS = {}, ("auto",)

MARKUP_KINDS = ("callouts", "toc", "center", "highlight", "underline", "keep", "landscape", "appendix", "fullcite", "pagecite", "excerpts", "space")


def markup_value(value) -> list[str]:
    """The kinds a `markup` value names, in MARKUP_KINDS order: true or `all` every one, false none, a list (or a
    comma-separated string) those."""
    if value is None or value is False:
        return []
    if value is True:
        return list(MARKUP_KINDS)
    items = value if isinstance(value, list) else str(value).replace(",", " ").split()
    words = [str(item).strip().casefold() for item in items if str(item).strip()]
    if any(word in ("all", "true", "yes", "on") for word in words):
        return list(MARKUP_KINDS)
    unknown = [word for word in words if word not in MARKUP_KINDS and word not in ("false", "no", "off", "none")]
    if unknown:
        print(f"WARN  markup: {', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a kind of universal markup "
              f"({', '.join(MARKUP_KINDS)}, or all)", file=sys.stderr)
    return [kind for kind in MARKUP_KINDS if kind in words]


def show_comments_on(md_path: Path, metadata_files: list[Path]) -> bool:
    """Whether the <!-- comments --> of the text are shown in the output (v3.29.21): `--show-comments` / `--no-show-comments`,
    else `pdfmd-options.show-comments`. Off by default, and not one of the `markup: true` kinds."""
    if core.SHOW_COMMENTS_CLI["on"] is not None:
        return bool(core.SHOW_COMMENTS_CLI["on"])
    value = core.first_pdfmd_option(md_path, metadata_files, "show-comments")
    return value is True or str(value).strip().casefold() in ("true", "yes", "on", "1")


_FLAVOUR_TOLD: set[str] = set()


UNCLOSED_WORDS = ("hide", "keep")


def unclosed_comment_mode(md_path: Path, metadata_files=()) -> str:
    """What a `%%` with no closing `%%` does (v3.32.21): `hide` (Obsidian's way: the rest of the note is the comment) or `keep` (it
    stays text). `--unclosed-comment`, else `pdfmd-options.unclosed-comment`, else the flavour's own (`hide` for obsidian, `keep`
    for pdfmd: outside a vault a lone `%%` may be TeX). Another word is told once and the flavour's is used."""
    preset = core.FLAVOUR_PRESETS.get(flavour_of(md_path, metadata_files))
    default = preset.unclosed if preset else "keep"
    value = core.UNCLOSED_CLI["mode"]
    if value is None:
        value = core.first_pdfmd_option(md_path, list(metadata_files), "unclosed-comment")
    name = default if value is None else str(value).strip().casefold()
    if name in UNCLOSED_WORDS:
        return name
    if name and name not in _FLAVOUR_TOLD:
        _FLAVOUR_TOLD.add(name)
        print(f"NOTE  unclosed-comment: {name} is not one of {', '.join(UNCLOSED_WORDS)}; using {default}", file=sys.stderr)
    return default


def flavour_setting(md_path: Path, metadata_files=()) -> tuple[str, str | None]:
    """The flavour setting of a file, as (preset, reader spec): the command line, else `pdfmd-options.flavour` / `flavor` / `reader`.
    A preset word (any case) is the preset, with no spec; `auto` or nothing is obsidian inside a vault and pdfmd elsewhere; any
    other value is a Pandoc reader spec (`gfm+smart`): the flavour is auto's and the spec is the reader."""
    value = core.FLAVOUR_CLI["name"]
    if value is None:
        value = core.first_pdfmd_option(md_path, list(metadata_files), "flavour", "flavor", "reader")
    text = "" if value is None else str(value).strip()
    word = text.casefold()
    if word in core.FLAVOUR_PRESETS:
        return word, None
    auto = "obsidian" if core.vault_root(md_path) is not None else "pdfmd"
    return auto, (None if word in ("", "auto") else text)


def flavour_of(md_path: Path, metadata_files=()) -> str:
    """The flavour this file is read in: `obsidian`, `pdfmd`, `pandoc`, `gfm` or `commonmark` (see flavour_setting)."""
    return flavour_setting(md_path, metadata_files)[0]


def flavour_default(md_path: Path, metadata_files, column: str) -> str:
    """What the flavour switches on without a setting (v3.32.24): its `markup` or `pagebreak` column (see pdfmd_flavours), for a
    Markdown file only; empty for any other input and for `pandoc`, `gfm` and `commonmark`."""
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return ""
    preset = core.FLAVOUR_PRESETS.get(flavour_of(md_path, metadata_files))
    return getattr(preset, column, "") if preset else ""


def obsidian_source(text: str, md_path: Path, metadata_files=(), show: bool | None = None) -> str:
    """``text`` as Pandoc should read it in the flavour's own syntax: %%comments%% hidden (obsidian, pdfmd), or (``show``, by default
    `show-comments`) turned into HTML comments the writers draw as Comment boxes; then each `![[picture|300]]` written as a Markdown
    image (see embed_source). Unchanged when the flavour has neither or the text has none of them. A `%%` that never closes is told
    once (see unclosed_comment_mode for what becomes of it)."""
    preset = core.FLAVOUR_PRESETS.get(flavour_of(md_path, metadata_files)) if ("%%" in text or "[[" in text) else None
    if preset is None:
        return text
    if preset.comments and "%%" in text:
        text = hidden_comments(text, md_path, metadata_files, show)
    if preset.embeds and "![[" in text:
        text = core.embed_source(text, md_path, metadata_files)
    if preset.wikilinks and "[[" in text:
        try:
            from pdfmd_obsidian import wikilinks_as_text
            text = wikilinks_as_text(text).text
        except ImportError:
            pass
    return text


def hidden_comments(text: str, md_path: Path, metadata_files=(), show: bool | None = None) -> str:
    """``text`` without its %%comments%% (v3.32.20), or with them as HTML comments when they are to be shown."""
    try:
        from pdfmd_obsidian import hide_comments
    except ImportError:
        print("WARN  the pdfmd_obsidian package is missing; %%comments%% are left as they are", file=sys.stderr)
        return text
    mode = unclosed_comment_mode(md_path, metadata_files)
    result = hide_comments(text, show_comments_on(md_path, list(metadata_files)) if show is None else show, mode)
    for line in result.unclosed:
        told = f"{md_path}:{line}"
        if told not in _FLAVOUR_TOLD:
            _FLAVOUR_TOLD.add(told)
            rest = len(text.splitlines()) - line + 1
            what = (f"the rest of the note ({rest} line{'s' if rest != 1 else ''}) is hidden, as Obsidian hides it; "
                    "pdfmd-options: unclosed-comment: keep leaves it as text" if mode == "hide"
                    else "it is kept as text; pdfmd-options: unclosed-comment: hide hides the rest, as Obsidian does")
            print(f"WARN  {core.display_path(md_path)}, line {line}: a `%%` with no closing `%%`: {what}", file=sys.stderr)
    return result.text


def markup_kinds(md_path: Path, metadata_files: list[Path]) -> list[str]:
    """The kinds of universal markup this build carries: the command line's, else pdfmd-options' (less a chosen kit's
    `markup-off:`, pdfmd_kits.markup); with the comments (`comments`, which no list names) when they are to be shown."""
    kinds: list[str] = []
    if not core.MARKUP_CLI["off"]:
        if core.MARKUP_CLI["kinds"] is not None:
            kinds = markup_value(core.MARKUP_CLI["kinds"] or True)
        else:
            value = core.first_pdfmd_option(md_path, metadata_files, "markup")
            kinds = markup_value(flavour_default(md_path, metadata_files, "markup") if value is None else value)
            if kinds and core.active_kits(md_path, metadata_files, None):
                kinds = core.kit_markup_off(md_path, metadata_files, kinds)        # a kit's `markup-off:` (v3.33.68)
    if show_comments_on(md_path, metadata_files):
        kinds.append("comments")
    return kinds


def markup_filter_args(sources: Path | list[Path], metadata_files: list[Path]) -> list[str]:
    """``--lua-filter markup.lua`` with the kinds that take part (`-M pdfmd-markup=callouts`), when any."""
    files = sources if isinstance(sources, list) else [sources]
    fit = core.embed_filter_args(sources, metadata_files) + core.figure_filter_args(sources, metadata_files)   # before markup.lua, so a markup filter stays the last argument
    kinds = [kind for kind in markup_kinds(files[0], metadata_files) if kind != "excerpts"] if files else []
    if not kinds:
        return fit
    try:
        import pdfmd_lua
    except ImportError:
        core.pdfmd_lua_missing()
        return fit
    shipped = pdfmd_lua.path("markup")
    return fit + (["-M", "pdfmd-markup=" + ",".join(kinds), "--lua-filter", str(shipped)] if shipped is not None else [])


MARKUP_CALLOUT_HEADER = r"""% pdfmd: the box of a callout (pdfmd-options: markup: callouts)
\makeatletter
\@ifpackageloaded{xcolor}{}{\usepackage{xcolor}}
\makeatother
\definecolor{pdfmd-note}{HTML}{0969DA}
\definecolor{pdfmd-tip}{HTML}{1A7F37}
\definecolor{pdfmd-important}{HTML}{8250DF}
\definecolor{pdfmd-warning}{HTML}{9A6700}
\definecolor{pdfmd-caution}{HTML}{CF222E}
\definecolor{pdfmd-comment}{HTML}{6E7781}
\IfFileExists{tcolorbox.sty}{\def\pdfmdhastcolorbox{1}}{}
\ifdefined\pdfmdhastcolorbox
  \usepackage{tcolorbox}\tcbuselibrary{breakable}
  \newtcolorbox{pdfmdcallout}[1]{breakable, colback=#1!6!white, colframe=#1, boxrule=0pt, leftrule=2.5pt, arc=0pt,
    left=8pt, right=8pt, top=5pt, bottom=5pt}
\else
  \newenvironment{pdfmdcallout}[1]{\par\medskip\begin{quote}}{\end{quote}\medskip}
\fi
"""


MARKUP_HIGHLIGHT_HEADER = r"""% pdfmd: highlighted text (pdfmd-options: markup: highlight)
\makeatletter
\@ifpackageloaded{xcolor}{}{\usepackage{xcolor}}
\makeatother
\definecolor{pdfmd-mark}{HTML}{FFF3A3}
% under LuaTeX Pandoc's template loads lua-ul (with soul's \ul) for an underline; the same load here, with its own \highLight, keeps the two apart
% lua-ul's \highLight colours through luacolor, which Pandoc's template loads only for ~~struck~~ text: both are needed, else soul
\ifdefined\directlua
  \IfFileExists{lua-ul.sty}{\IfFileExists{luacolor.sty}{\def\pdfmdhasluaul{1}}{}}{}
\fi
\IfFileExists{soul.sty}{\def\pdfmdhassoul{1}}{}
\ifdefined\pdfmdhasluaul
  \usepackage{luacolor}
  \usepackage[soul]{lua-ul}
  \newcommand{\pdfmdhl}[1]{\highLight[pdfmd-mark]{#1}}
\else\ifdefined\pdfmdhassoul
  \usepackage{soul}
  \sethlcolor{pdfmd-mark}
  \newcommand{\pdfmdhl}[1]{\hl{#1}}
\else
  \newcommand{\pdfmdhl}[1]{#1}
\fi\fi
"""


MARKUP_LANDSCAPE_HEADER = r"""% pdfmd: landscape pages (pdfmd-options: markup: landscape)
\IfFileExists{pdflscape.sty}{\def\pdfmdhaslscape{1}}{}
\ifdefined\pdfmdhaslscape
  \usepackage{pdflscape}
\else
  \IfFileExists{lscape.sty}{\usepackage{lscape}}{\newenvironment{landscape}{}{}}
\fi
"""


# the LaTeX definitions each kind of markup needs (the kinds not here need none)
MARKUP_HEADERS = {"callouts": MARKUP_CALLOUT_HEADER, "comments": MARKUP_CALLOUT_HEADER, "highlight": MARKUP_HIGHLIGHT_HEADER,
                  "landscape": MARKUP_LANDSCAPE_HEADER}


def markup_header_args(sources: Path | list[Path], metadata_files: list[Path], before: list[str] | None = None) -> list[str]:
    """`--include-in-header` for a LaTeX build's universal markup: the pdfmdcallout environment, \\pdfmdhl ... in ONE header file
    of pdfmd's own (a filter's `header-includes` is dropped by every other header file of pdfmd's), or []. ``before`` is the
    Pandoc command so far: after a kit's or the user's own LaTeX the header keeps what that defined (v3.33.67,
    pdfmd_tex.markup)."""
    files = sources if isinstance(sources, list) else [sources]
    kinds = [kind for kind in markup_kinds(files[0], metadata_files) if kind != "excerpts"] if files else []
    pieces = core.markup_header_pieces(files[0], metadata_files, kinds, before) if kinds else []     # the box is one piece
    if not pieces:
        return []
    text = "\n".join(pieces)
    header = core.cache_root() / "tex" / f"packages-markup-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.tex"
    try:
        if not header.is_file():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text(text, encoding="utf-8")
    except OSError:
        return []
    return ["--include-in-header", str(header)]

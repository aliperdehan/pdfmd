"""Universal markup's LaTeX header when LaTeX of somebody else's comes before it (v3.33.67): a kit's package, a `preamble.tex`
or another header file of the user's, an own template or a class other than the standard ones.

pdfmd's markup header (`MARKUP_HEADERS` in `pdfmd.py`) loads pdflscape for `landscape` and lua-ul or soul for `highlight`.
lscape defines its environment with `\\def`, so a `landscape` environment a kit had defined (nulabreport's: a wider sheet,
logo and footer upright) was replaced without a word by pdflscape's turned portrait page; and lua-ul with `[soul]` stopped
LuaLaTeX when soul or a bare lua-ul was loaded first (`\\textul already defined`, an option clash). After such LaTeX the
header is the guarded one below: it keeps a `landscape` environment that exists (`\\landscape` and `\\endlandscape`) and
a lua-ul or soul that is loaded, and sets the highlight colour of soul's `\\hl` for pdfmd's own `\\pdfmdhl` only. A document
with nothing before pdfmd's header gets the header as it always was, byte for byte.

`core` is the `pdfmd` module, bound by `pdfmd.py` when the module is first loaded (a stand-in there loads it on the first
call); the pdfmd names it reads (`MARKUP_HEADERS`, `active_kits`, `cache_root`, `effective_metadata`) are read as `core.X`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

core = None

# The classes that define no `landscape` and no highlighting of their own (Pandoc's template is written for them). Any other
# `documentclass` may, so it gets the guarded header (a file-format fact, not a setting: what a class defines).
STANDARD_CLASSES = frozenset({"article", "report", "book", "scrartcl", "scrreprt", "scrbook", "memoir", "beamer"})

LANDSCAPE_GUARDED = r"""% pdfmd: landscape pages (pdfmd-options: markup: landscape)
% a landscape environment defined above (a kit's, a class's, a preamble's) is kept: pdflscape would replace it
\ifdefined\landscape\ifdefined\endlandscape\def\pdfmdownlandscape{1}\fi\fi
\ifdefined\pdfmdownlandscape\else
  \IfFileExists{pdflscape.sty}{\def\pdfmdhaslscape{1}}{}
  \ifdefined\pdfmdhaslscape
    \usepackage{pdflscape}
  \else
    \IfFileExists{lscape.sty}{\usepackage{lscape}}{\newenvironment{landscape}{}{}}
  \fi
\fi
"""

HIGHLIGHT_GUARDED = r"""% pdfmd: highlighted text (pdfmd-options: markup: highlight)
\makeatletter
\@ifpackageloaded{xcolor}{}{\usepackage{xcolor}}
\definecolor{pdfmd-mark}{HTML}{FFF3A3}
% under LuaTeX Pandoc's template loads lua-ul (with soul's \ul) for an underline; the same load here, with its own \highLight, keeps the two apart
% a lua-ul or a soul loaded above (by a kit, a class, a preamble) is kept as it was loaded, and so is the colour of its \hl
% lua-ul's \highLight colours through luacolor (loaded again it is a no-op): both are needed, else soul
\ifdefined\directlua
  \IfFileExists{lua-ul.sty}{\IfFileExists{luacolor.sty}{\def\pdfmdhasluaul{1}}{}}{}
\fi
\IfFileExists{soul.sty}{\def\pdfmdhassoul{1}}{}
\ifdefined\pdfmdhasluaul
  \@ifpackageloaded{luacolor}{}{\usepackage{luacolor}}
  \@ifpackageloaded{lua-ul}{}{\@ifpackageloaded{soul}{\usepackage{lua-ul}}{\usepackage[soul]{lua-ul}}}
  \newcommand{\pdfmdhl}[1]{\highLight[pdfmd-mark]{#1}}
\else\ifdefined\pdfmdhassoul
  \@ifpackageloaded{soul}{\newcommand{\pdfmdhl}[1]{{\sethlcolor{pdfmd-mark}\hl{#1}}}}{%
    \usepackage{soul}
    \sethlcolor{pdfmd-mark}
    \newcommand{\pdfmdhl}[1]{\hl{#1}}}
\else
  \newcommand{\pdfmdhl}[1]{#1}
\fi\fi
\makeatother
"""

GUARDED = {"landscape": LANDSCAPE_GUARDED, "highlight": HIGHLIGHT_GUARDED}


def _values(cmd: list[str], short: str, long: str) -> list[str]:
    """The values of an option of ``cmd`` written `-X value`, `-Xvalue`, `--long value` or `--long=value`."""
    found = []
    for index, item in enumerate(cmd):
        if item in (short, long) and index + 1 < len(cmd):
            found.append(cmd[index + 1])
        elif item.startswith(long + "="):
            found.append(item.split("=", 1)[1])
        elif short and item.startswith(short) and len(item) > len(short) and not item.startswith("--"):
            found.append(item[len(short):])
    return found


def pdfmds_own_header(path: Path) -> bool:
    """Whether a header file is one pdfmd writes itself: in its cache folder, or a `pdfmd-*` file of the system's temporary folder
    (the fonts header, `pdfmd-fonts-*.tex`; the PDF properties, `pdfmd-pdfmeta-*.tex`). A document's `header-includes` file
    (`.NAME.pdfmd-header-*.tex`, beside it) is the user's LaTeX, and so is every other file."""
    try:
        where = path.resolve()
        cache = core.cache_root().resolve()
        temporary = Path(tempfile.gettempdir()).resolve()
    except OSError:
        return False
    return cache in where.parents or (where.parent == temporary and where.name.startswith("pdfmd-"))


def foreign_latex_before(md_path: Path, metadata_files: list[Path], before: list[str]) -> bool:
    """Whether LaTeX that is not Pandoc's template or pdfmd's own may come before the markup header in this build: a chosen kit, a
    header file outside pdfmd's cache folder (`preamble.tex`, `-H`), an own template or defaults file, a non-standard class."""
    if core.active_kits(md_path, metadata_files, None):
        return True
    if any(item in ("--template", "-d", "--defaults") or item.startswith(("--template=", "--defaults=")) for item in before):
        return True
    for name in _values(before, "-H", "--include-in-header"):
        if not pdfmds_own_header(Path(name)):
            return True
    classes = [value.split("=", 1)[1] if "=" in value else value.split(":", 1)[1]
               for value in _values(before, "-V", "--variable") + _values(before, "-M", "--metadata")
               if value.split("=", 1)[0].split(":", 1)[0].strip() == "documentclass" and ("=" in value or ":" in value)]
    if not classes:
        klass = core.effective_metadata(md_path, metadata_files, []).get("documentclass")
        classes = [] if klass is None else [str(klass)]
    return any(text.strip() and text.strip() not in STANDARD_CLASSES for text in classes)


def markup_header_pieces(md_path: Path, metadata_files: list[Path], kinds: list[str], before: list[str] | None) -> list[str]:
    """The pieces of the markup header for ``kinds``, each once: the guarded `landscape` and `highlight` when LaTeX of somebody
    else's may come before them (foreign_latex_before; ``before`` is the Pandoc command so far, None when not known)."""
    headers = core.MARKUP_HEADERS
    if before is not None and any(kind in GUARDED for kind in kinds) and foreign_latex_before(md_path, metadata_files, before):
        headers = {**headers, **GUARDED}
    return list(dict.fromkeys(headers[kind] for kind in kinds if kind in headers))

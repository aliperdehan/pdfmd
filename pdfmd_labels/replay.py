"""The TeX that replays a scan inside a partial build, and the file that holds it.

At ``\\AtBeginDocument`` the build runs the scan's events in a box that is thrown away: every numbered heading,
caption and equation row does its ``\\refstepcounter`` and every label its own ``\\label``, with the ``.aux`` write
redirected into a scratch file that is then read back through ``\\pdfmd@seed``. LaTeX, not pdfmd, does the counting, so
the document's number style (a Roman ``\\thesection``, ``\\counterwithin``, a package's counters) and cleveref's
``label@cref`` entries come out as in a full build. Afterwards every counter and ``\\the...`` macro is put back, so the
replay leaves nothing behind. ``\\pdfmd@seed`` defines a label only if nothing defined it before (an ``.aux`` read, the
last full build's seed, the part's own labels), which is what keeps the order: own > last full build > replay.
"""

from __future__ import annotations

from .scan import Scan

REPLAY_DEFS = r"""\makeatletter
\providecommand\pdfmd@seed[2]{\@ifundefined{r@#1}{\expandafter\gdef\csname r@#1\endcsname{#2}}{}}
\providecommand\pdfmd@part[2]{}
\newwrite\pdfmd@w
\newsavebox\pdfmd@box
\def\pdfmd@sv#1{\expandafter\xdef\csname pdfmd@sv@#1\endcsname{\the\csname c@#1\endcsname}%
  \expandafter\let\csname pdfmd@th@#1\expandafter\endcsname\csname the#1\endcsname}
\def\pdfmd@rs#1{\global\csname c@#1\endcsname=\csname pdfmd@sv@#1\endcsname\relax
  \expandafter\global\expandafter\let\csname the#1\expandafter\endcsname\csname pdfmd@th@#1\endcsname}
\def\pdfmd@sn#1{\def\pdfmd@x{#1}\def\pdfmd@y{page}\ifx\pdfmd@x\pdfmd@y\else
  \xdef\pdfmd@acc{\pdfmd@acc\global\csname c@#1\endcsname=\the\csname c@#1\endcsname\relax}\fi}
\newcommand\pdfmd@ev@step[1]{\@ifundefined{c@#1}{}{\refstepcounter{#1}}}
\newcommand\pdfmd@ev@sec[2]{\ifnum\c@secnumdepth<#2\relax\else\pdfmd@ev@step{#1}\fi}
\newcommand\pdfmd@ev@fn{\@ifundefined{c@footnote}{}{\stepcounter{footnote}}}
\newcommand\pdfmd@ev@app{\appendix}
\newcommand\pdfmd@ev@lab[1]{\label{#1}}
\newcommand\pdfmd@ev@part[1]{\gdef\pdfmd@acc{}\begingroup\let\@elt\pdfmd@sn\cl@@ckpt\endgroup
  \@ifundefined{pdfmd@st@#1}{\expandafter\xdef\csname pdfmd@st@#1\endcsname{\pdfmd@acc}}{}}
\long\def\pdfmd@write#1#2#3{\begingroup\def\thepage{??}#2\let\protect\@unexpandable@protect
  \edef\reserved@a{\immediate\write\pdfmd@w{#3}}\reserved@a\endgroup}
\def\pdfmd@replay#1{%
  \begingroup
    \let\@elt\pdfmd@sv \cl@@ckpt
    \@ifundefined{@chapapp}{}{\xdef\pdfmd@chapapp{\@chapapp}}%
    \immediate\openout\pdfmd@w=\jobname.pdfmd-seed\relax
    \let\pdfmd@pw\protected@write \let\protected@write\pdfmd@write
    \setbox\pdfmd@box\vbox{\csname #1\endcsname}%
    \let\protected@write\pdfmd@pw
    \immediate\closeout\pdfmd@w
    \let\@elt\pdfmd@rs \cl@@ckpt
    \@ifundefined{@chapapp}{}{\xdef\@chapapp{\pdfmd@chapapp}}%
    \let\newlabel\pdfmd@seed
    \InputIfFileExists{\jobname.pdfmd-seed}{}{}%
  \endgroup}
\makeatother
"""

HEADER = "% the cross-references of the whole document, counted from its sources (pdfmd --seed-labels)\n"


def render(result: Scan) -> str:
    """The seed file: the replay macros, then the events as one macro per line, run once the document begins."""
    lines = []
    for event in result.events:
        if event.kind == "sec":
            lines.append(f"\\pdfmd@ev@sec{{{event.arg}}}{{{event.level}}}")
        elif event.kind == "step":
            lines.append(f"\\pdfmd@ev@step{{{event.arg}}}" if event.arg != "footnote" else "\\pdfmd@ev@fn")
        elif event.kind == "lab":
            lines.append(f"\\pdfmd@ev@lab{{{event.arg}}}")
        elif event.kind == "part":
            lines.append(f"\\pdfmd@ev@part{{{event.arg}}}")
        elif event.kind == "app":
            lines.append("\\pdfmd@ev@app")
    body = "\n".join(lines)
    return (HEADER + REPLAY_DEFS
            + "\\makeatletter\n\\def\\pdfmd@events{%\n" + body.replace("\n", "%\n") + "%\n}\n"
            + "\\AtBeginDocument{\\pdfmd@replay{pdfmd@events}}\n\\makeatother\n")

"""LaTeX fragments drawn as pictures.

What cannot be made native in a Word/ODT file (tikz, chemfig, a house style's own macros, math Pandoc's
converter rejects) is compiled by LaTeX *in the document's own preamble* -- the same fonts, packages and
macros as the PDF -- one fragment to a page, cropped to its box; each page becomes an SVG (vector) and a
300 dpi PNG (the fallback Word and LibreOffice draw), with the box's depth so an inline fragment sits on
the text's baseline. Results are cached by content: a rebuild draws only what changed.

The Lua filter runs twice: once to list the fragments, once to put their pictures in.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

SETUP = r"""
\usepackage[active,tightpage]{preview}
\setlength\PreviewBorder{0pt}
\makeatletter
\newsavebox{\pdfmdbox}
\newwrite\pdfmdlog
\immediate\openout\pdfmdlog=\jobname.pdfmdlog
\newenvironment{pdfmdblock}{\par\begin{minipage}{\textwidth}}{\par\end{minipage}}
\newenvironment{pdfmdinline}{\begin{lrbox}{\pdfmdbox}}{\end{lrbox}%
  \immediate\write\pdfmdlog{\the\wd\pdfmdbox:\the\ht\pdfmdbox:\the\dp\pdfmdbox}\usebox{\pdfmdbox}}
\PreviewEnvironment{pdfmdblock}
\PreviewEnvironment{pdfmdinline}
\makeatother
"""

INLINE_KINDS = ("inline", "math-inline", "math-display")


def body(item: dict) -> str:
    kind, tex = item["kind"], item["tex"]
    if kind == "math-inline":
        return "\\begin{pdfmdinline}$" + tex + "$\\end{pdfmdinline}"
    if kind == "math-display":
        return "\\begin{pdfmdinline}$\\displaystyle " + tex + "$\\end{pdfmdinline}"
    if kind == "inline":
        return "\\begin{pdfmdinline}" + tex + "\\end{pdfmdinline}"
    return "\\begin{pdfmdblock}\n" + tex + "\n\\end{pdfmdblock}"


def document(preamble: str, items: list[dict], labels_aux: Path | None) -> str:
    lines = [preamble, SETUP]
    if labels_aux is not None:
        lines.append("\\AtBeginDocument{\\makeatletter\\InputIfFileExists{%s}{}{}\\makeatother}" % labels_aux.as_posix())
    lines.append("\\begin{document}")
    for item in items:
        lines.append(body(item))
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n"


def parse_dimension(text: str) -> float:
    """TeX's `12.3pt` (what \\the prints) in points."""
    match = re.match(r"\s*(-?[\d.]+)pt", text)
    return float(match.group(1)) if match else 0.0


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def tools_available() -> bool:
    return shutil.which("pdftocairo") is not None


def convert_pages(pdf: Path, count: int, folder: Path, jobs: int = 4) -> list[dict]:
    """Page i of `pdf` as folder/page-i.svg and .png; returns [{svg, png, width, height}]."""
    def one(page: int) -> dict:
        stem = folder / f"page-{page}"
        _run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), str(pdf), f"{stem}.svg"])
        _run(["pdftocairo", "-png", "-r", "300", "-transp", "-singlefile", "-f", str(page), "-l", str(page),
              str(pdf), str(stem)])
        svg = Path(f"{stem}.svg")
        size = re.search(r'<svg[^>]*\bwidth="([\d.]+)(?:pt)?"[^>]*\bheight="([\d.]+)(?:pt)?"', svg.read_text(encoding="utf-8")[:2000]) \
            if svg.is_file() else None
        return {"svg": f"{stem}.svg", "png": f"{stem}.png",
                "width": float(size.group(1)) if size else 0.0, "height": float(size.group(2)) if size else 0.0}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(one, range(1, count + 1)))


def page_count(pdf: Path) -> int:
    done = _run(["pdfinfo", str(pdf)])
    found = re.search(r"Pages:\s+(\d+)", done.stdout)
    return int(found.group(1)) if found else 0


def first_error(log_text: str) -> str:
    match = re.search(r"^! (.+)$", log_text, re.M)
    return match.group(1).strip() if match else "LaTeX failed"


def render(items: list[dict], preamble: str, labels_aux: Path | None, work: Path, store: Path,
           compile_tex: Callable[[Path, Path], tuple[bool, str]], log: Callable[[str], None] = lambda text: None
           ) -> dict[str, str]:
    """Draw `items` ({id, kind, tex}); pictures and `<id>.json` go to `store`. Returns {id: reason} for the
    ones that would not compile. Everything at once; on a failure the group is halved until the
    fragments that break are alone."""
    failures: dict[str, str] = {}
    store.mkdir(parents=True, exist_ok=True)
    counter = [0]

    def attempt(group: list[dict]) -> None:
        if not group:
            return
        counter[0] += 1
        folder = work / f"group-{counter[0]}"
        folder.mkdir(parents=True, exist_ok=True)
        tex = folder / "fragments.tex"
        tex.write_text(document(preamble, group, labels_aux), encoding="utf-8")
        pdf = folder / "fragments.pdf"      # the engine writes it beside the .tex
        ok, reason = compile_tex(tex, pdf)
        pages = page_count(pdf) if ok and pdf.is_file() else 0
        if ok and pages == len(group):
            log_file = folder / "fragments.pdfmdlog"
            lines = log_file.read_text(encoding="utf-8").splitlines() if log_file.is_file() else []
            measured = [line.split(":") for line in lines]
            converted = convert_pages(pdf, pages, folder)
            inline_index = 0
            for item, picture in zip(group, converted):
                depth = 0.0
                if item["kind"] in INLINE_KINDS:
                    if inline_index < len(measured) and len(measured[inline_index]) == 3:
                        depth = parse_dimension(measured[inline_index][2])
                    inline_index += 1
                target_svg, target_png = store / f"{item['id']}.svg", store / f"{item['id']}.png"
                shutil.copyfile(picture["svg"], target_svg)
                shutil.copyfile(picture["png"], target_png)
                (store / f"{item['id']}.json").write_text(json.dumps({
                    "svg": str(target_svg), "png": str(target_png), "width": picture["width"],
                    "height": picture["height"], "depth": depth, "kind": item["kind"]}), encoding="utf-8")
            return
        if len(group) == 1:
            failures[group[0]["id"]] = reason or "LaTeX failed"
            return
        middle = len(group) // 2
        attempt(group[:middle])
        attempt(group[middle:])

    attempt(items)
    return failures


def preamble_of(tex: str) -> str | None:
    """Everything before \\begin{document} of a standalone .tex."""
    index = tex.find("\\begin{document}")
    return tex[:index] if index != -1 else None


def labels_only(aux_text: str) -> str:
    """Just the \\newlabel lines of an .aux file: the references of a fragment resolve against the real build."""
    return "\n".join(line for line in aux_text.splitlines() if line.startswith("\\newlabel")) + "\n"


def store_key(preamble: str, engine: str, labels_text: str) -> str:
    """The folder name pictures are kept under: they depend on the preamble, the engine and the labels."""
    digest = hashlib.sha1()
    for part in (preamble, engine, labels_text):
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]

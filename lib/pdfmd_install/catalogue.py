"""Read-only catalogue for a bare --install; installation stays in the existing dispatch."""

from __future__ import annotations

import sys

from pdfmd_base import core


def table() -> str:
    tools = core.display_path(core.tools_directory())
    fonts = core.display_path(core.fonts_directory())
    data = core.display_path(core.data_root())
    rows = {
        "pandoc": ("pip: pypandoc_binary (PyPI)", "Python environment running pdfmd", "pip uninstall pypandoc_binary"),
        "typst": ("download: typst/typst GitHub release", tools, "delete typst in tools folder"),
        "core:tex": ("pip: pypandoc_binary; download: tectonic-typesetting/tectonic GitHub release and fonts:core",
                     f"Python environment + {tools} + {fonts}",
                     "pip uninstall pypandoc_binary; delete tectonic in tools folder; --uninstall fonts:core"),
        "full": ("pip: pypandoc_binary; download: typst/typst GitHub release and fonts:core",
                 f"Python environment + {tools} + {fonts}",
                 "pip uninstall pypandoc_binary; delete typst in tools folder; --uninstall fonts:core"),
        "math": ("pip: pymd2pdf, matplotlib (PyPI)", "Python environment running pdfmd", "pip uninstall pymd2pdf matplotlib"),
        "math:katex": ("download: KaTeX GitHub release; nodejs.org if needed", data + "/katex + " + tools, "delete data/katex (shared node may be kept)"),
        "math:mathjax": ("download: MathJax npm packages, STIX Two font; nodejs.org if needed", data + "/mathjax + " + tools,
                         "delete data/mathjax (shared node may be kept)"),
        "diagram:d2": ("download: terrastruct/d2 GitHub release", tools, "delete d2 in tools folder"),
        "diagram:dot": ("download: @hpcc-js/wasm-graphviz (npm); nodejs.org if needed", data + "/graphviz + " + tools,
                        "delete graphviz folder and dot launcher (shared node may be kept)"),
        "diagram:resvg": ("download: linebender/resvg GitHub release", tools, "delete resvg in tools folder"),
        "diagram": ("download: D2/resvg GitHub releases, Graphviz npm; nodejs.org if needed", data + "/graphviz + " + tools,
                    "delete graphviz folder and d2, dot, resvg in tools folder"),
        "calibre": ("package manager, or download: kovidgoyal/calibre GitHub release",
                    "~/Applications/calibre.app" if sys.platform == "darwin" else data + "/calibre (Windows: winget)",
                    "remove with package manager, or delete downloaded Calibre"),
        "fonts": ("list; fonts:NAME downloads font releases (GitHub)", fonts, "--uninstall fonts:NAME"),
        "emoji": ("download: Noto colour emoji font (GitHub)", fonts, "--uninstall fonts:emoji"),
        "ocr": ("list; ocr:LANG downloads tessdata_fast (GitHub)", data + "/tessdata", "--uninstall ocr:LANG"),
        "kit": ("list; kit:SOURCE copies a local folder or downloads a git repository", "kits beside pdfmd config", "--uninstall kit:NAME"),
        "translit": ("pip: pypinyin, anyascii (PyPI)", "Python environment running pdfmd", "pip uninstall pypinyin anyascii"),
        "tui": ("pip: prompt_toolkit (PyPI)", "Python environment running pdfmd", "pip uninstall prompt_toolkit"),
        "batchocr": ("pip: batchocr[md] (GitHub release), including PyMuPDF", "Python environment running pdfmd", "pip uninstall batchocr"),
    }
    for alias, original in (("core", "full"), ("core:typst", "full"), ("cortex", "core:tex"), ("diagram:all", "diagram")):
        rows[alias] = rows[original]
    lines = ["Optional pieces (bare group names list choices; nothing is fetched by this table):", "",
             "Kind | Size | Fetch / source | Target | Removal"]
    for kind, size in core.INSTALL_SIZES.items():
        source, target, removal = rows[kind]
        lines.append(f"{kind} | {size} | {source} | {target} | {removal}")
    lines += ["", "Install: pdfmd --install KIND. Use the Python running pdfmd for pip removal (python -m pip).",
              "Downloaded tools have no general --uninstall; delete only the named tool or folder. Shared node can stay."]
    return "\n".join(lines)

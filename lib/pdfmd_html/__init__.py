"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_html`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import re
import struct
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable

from pdfmd_base import core


KATEX_VERSION = "0.18.9"


KATEX_PACKAGE = f"https://registry.npmjs.org/katex/-/katex-{KATEX_VERSION}.tgz"


def katex_folder() -> Path | None:
    """The KaTeX files pdfmd installed: this release's, else the newest other one there (an older pdfmd's)."""
    root = core.data_root() / "katex"

    def complete(folder: Path) -> bool:
        return (folder / "katex.min.js").is_file() and (folder / "katex.min.css").is_file()

    if complete(root / KATEX_VERSION):
        return root / KATEX_VERSION
    try:
        found = [folder for folder in root.iterdir() if complete(folder)]
    except OSError:
        return None
    return max(found, key=lambda folder: tuple(int(part) for part in re.findall(r"\d+", folder.name)), default=None)


def katex_runtime() -> tuple[str, Path] | None:
    """(node, the KaTeX folder) when math in a WeasyPrint PDF can be typeset, else None."""
    folder = katex_folder()
    node = core.which("node") if folder is not None else None
    return (node, folder) if node else None


MATHJAX_VERSION = "4.1.3"


MATHJAX_FONT_SHA256 = {"stix2": "664c8c40d739a231016cd6108cb6401166151772913e82b802bdd4b64812acf5"}


MATHJAX_DEFAULT_FONT = "stix2"


# the text font -> the MathJax math font that goes with it (a body that is not here gets STIX Two's, sized to its x-height)
MATHJAX_FONT_FOR = {"stix two text": "stix2"}


def mathjax_font_package(font: str) -> str:
    return f"mathjax-{font}-font"


def mathjax_folder() -> Path | None:
    """The MathJax files pdfmd installed: this release's, else the newest other one there (an older pdfmd's)."""
    root = core.data_root() / "mathjax"

    def complete(folder: Path) -> bool:
        return (folder / "node_modules" / "@mathjax" / "src" / "bundle" / "node-main.cjs").is_file() and bool(
            core.mathjax_fonts(folder))

    if complete(root / MATHJAX_VERSION):
        return root / MATHJAX_VERSION
    try:
        found = [folder for folder in root.iterdir() if complete(folder)]
    except OSError:
        return None
    return max(found, key=lambda folder: tuple(int(part) for part in re.findall(r"\d+", folder.name)), default=None)


def mathjax_fonts(folder: Path) -> list[str]:
    """The math fonts installed in a MathJax folder, in the order MATHJAX_FONT_SHA256 lists them."""
    modules = folder / "node_modules" / "@mathjax"
    return [font for font in MATHJAX_FONT_SHA256 if (modules / mathjax_font_package(font) / "chtml.js").is_file()]


def mathjax_runtime() -> tuple[str, Path] | None:
    """(node, the MathJax folder) when math in a WeasyPrint PDF can be typeset by MathJax, else None."""
    folder = mathjax_folder()
    node = core.which("node") if folder is not None else None
    return (node, folder) if node else None


def mathjax_font_for(body_font: str | None, installed: list[str]) -> tuple[str, bool] | None:
    """(the MathJax font to use, whether it is the one that goes with the body font): the table's font for the body when
    it is installed, else STIX Two's (the widest fit for a serif body), else the first one there; None with none."""
    wanted = MATHJAX_FONT_FOR.get((body_font or "").casefold())
    if wanted in installed:
        return wanted, True
    if MATHJAX_DEFAULT_FONT in installed:
        return MATHJAX_DEFAULT_FONT, False
    return (installed[0], False) if installed else None


KATEX_X_HEIGHT = 0.442       # KaTeX_Main's x-height per em (v3.28.25: the size that matches a body font's is its x-height / this)


def sfnt_x_height(path: Path, index: int = 0) -> float | None:
    """A font file's x-height as a fraction of its em (OS/2 sxHeight / head unitsPerEm), None when the file has none."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        base = 0
        if data[:4] == b"ttcf":
            base = struct.unpack(">I", data[12 + 4 * index:16 + 4 * index])[0]
        tables = {}
        count = struct.unpack(">H", data[base + 4:base + 6])[0]
        for number in range(count):
            at = base + 12 + 16 * number
            tables[data[at:at + 4]] = struct.unpack(">II", data[at + 8:at + 16])[0]
        units = struct.unpack(">H", data[tables[b"head"] + 18:tables[b"head"] + 20])[0]
        os2 = tables[b"OS/2"]
        version = struct.unpack(">H", data[os2:os2 + 2])[0]
        height = struct.unpack(">h", data[os2 + 86:os2 + 88])[0] if version >= 2 else 0
    except (struct.error, KeyError, IndexError):
        return None
    return height / units if height > 0 and units > 0 else None


def body_x_height(family: str | None) -> float | None:
    """The x-height (a fraction of the em) of an installed body font, found with fontconfig; None when the font is not
    installed or its file records none."""
    fc_match = core.which("fc-match")
    if not family or not fc_match:
        return None
    try:
        done = subprocess.run([fc_match, "-f", "%{family}\n%{file}\n%{index}", family], capture_output=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (done.stdout or "").splitlines()
    if done.returncode != 0 or len(lines) < 3 or family.casefold() not in lines[0].casefold():
        return None                                  # fontconfig answered with another font: the family is not installed
    return sfnt_x_height(Path(lines[1]), int(lines[2]) if lines[2].isdigit() else 0)


@lru_cache(maxsize=None)
def katex_scale(family: str | None) -> float | None:
    """The `font-size` (in em of the body) that gives KaTeX's formulas the body font's x-height: x-height / 0.442 (STIX Two
    Text 1.07, Noto Serif 1.21, Times 1.01, Georgia 1.09, Libertinus 0.97), kept within 0.85 and 1.4; None when the font is
    not known or has no x-height recorded (KaTeX keeps its own 1.21em)."""
    height = core.body_x_height(family)
    if height is None:
        return None
    return round(min(1.4, max(0.85, height / KATEX_X_HEIGHT)), 2)


def weasyprint_math_args(engine: str, pandoc_options: list[str], body_font: str | None = None,
                         no_auto: list[str] | None = None) -> list[str]:
    """For WeasyPrint (v3.27.12), which does not draw MathML (Pandoc's default HTML math printed each formula twice as
    flat text): Pandoc's plain math, simple formulas in Unicode and the others as TeX, unless the command line chooses
    the math; and pdfmd_lua/weasyprint.lua, which says once that the math is text and (v3.28.3) keeps a table's
    caption whole. With node and MathJax (v3.28.46, `pdfmd --install math:mathjax`) the filter typesets the math with
    it, in the font that goes with the body font; with KaTeX (v3.28.11, `pdfmd --install math:katex`) it typesets what
    MathJax cannot read, or all of it when MathJax is not there (or `--no-auto mathjax`): the variables name their
    folders and node. Last of the filters, after the LaTeX filter's \\ce in math."""
    if engine != "weasyprint":
        return []
    chosen = any(item.startswith(HTML_MATH_OPTIONS) for item in pandoc_options)
    out = [] if chosen else core.html_math_args("plain")
    try:
        import pdfmd_lua
    except ImportError:
        return out
    shipped = pdfmd_lua.path("weasyprint")
    if shipped is None:
        return out
    runtime = None if chosen or not (pdfmd_lua.FILTERS / "katex.cjs").is_file() else core.katex_runtime()
    if runtime is not None:
        node, folder = runtime
        out += ["-V", f"pdfmd-katex={folder}", "-V", f"pdfmd-katex-url={folder.as_uri()}",
                "-V", f"pdfmd-katex-node={node}"]
        scale = core.katex_scale(body_font)
        if scale is not None:
            out += ["-V", f"pdfmd-katex-scale={scale}"]
    jax = (None if chosen or core.auto_disabled(no_auto, "mathjax") or not (pdfmd_lua.FILTERS / "mathjax.cjs").is_file()
           else core.mathjax_runtime())
    if jax is not None:
        node, folder = jax
        font = mathjax_font_for(body_font, core.mathjax_fonts(folder))
        if font is not None:
            out += ["-V", f"pdfmd-mathjax={folder}", "-V", f"pdfmd-mathjax-font={font[0]}",
                    "-V", f"pdfmd-mathjax-node={node}"]
            height = None if font[1] else core.body_x_height(body_font)
            if height is not None:
                out += ["-V", f"pdfmd-body-xheight={round(height, 4)}"]          # the size match, for a body the font is not made for
    return out + ["--lua-filter", str(shipped)]


def ascii_table_transform(md_path: Path, metadata_files: list[Path], parts: list[Path], named_reader=None,
                          *, reader: str | None = None) -> "Callable[[str, Path], str] | None":
    """The ``transform`` of scaffold_inputs() that repairs the ASCII tables of a part (the document's own setting), or None."""
    if not parts:
        return None
    mode = core.table_ascii_mode(md_path, list(metadata_files))

    def transform(text: str, part: Path) -> str:
        if "@-" in text:
            text = core.deferred("pdfmd_excerpts.resolution", "protect_hyphen_prefix")(
                text, md_path, metadata_files, core.effective_no_auto(md_path, core.NO_AUTO_CLI), named_reader)
        if "\\[" in text:
            text = core.deferred("pdfmd_excerpts.pagecite", "protect_escapes")(text, md_path, metadata_files)
        if mode != "off":
            text = core.repair_ascii_text(text, mode, core.display_path(part), reader=reader)
        return core.cell_tags_text(text, md_path, metadata_files, core.display_path(part))
    return transform


HTML_TARGETS = frozenset({"html", "html4", "html5"})


DEFAULT_OUTPUT_ALIASES = {"tex": "latex", "txt": "txt", "text": "txt", "md": "markdown", "htm": "html",
                          "typ": "typst", "markdown": "markdown", "jpeg": "jpg", "tif": "tiff"}


# The math method, in whichever spelling the installed Pandoc has -- three
# generations: `--math-method=X` (3.11, which deprecates the others and warns),
# `--html-math-method=X` (a middle range of 3.x), and the short flags
# `--mathml`/`--mathjax`/... (older, 3.1 among them, which does not know the
# long forms at all). Found out from `pandoc --help`, never from a guessed
# version number.
HTML_MATH_METHODS = ("mathml", "mathjax", "katex", "webtex", "plain", "gladtex")


HTML_MATH_OPTIONS = ("--math-method", "--html-math-method", "--mathml", "--mathjax", "--katex", "--webtex", "--gladtex",
                     "--latexmathml")       # on the command line, any of these chooses the math itself


HTML_MATH_SHORT_FLAGS = {"mathml": "--mathml", "mathjax": "--mathjax", "katex": "--katex",
                         "webtex": "--webtex", "gladtex": "--gladtex"}   # "plain" is the default: no flag


def pandoc_has_option(option: str) -> bool:
    """Whether the installed Pandoc lists ``option`` in its --help, as a whole
    option name (`--math-method` is not found inside `--html-math-method`)."""
    if core._PANDOC_HELP is None:
        done = core.run_probe(["pandoc", "--help"])
        core._PANDOC_HELP = done.stdout if done else ""
    return bool(re.search(r"(?<![\w-])" + re.escape(option) + r"(?![\w-])", core._PANDOC_HELP))


def html_math_args(method: str) -> list[str]:
    for option in ("--math-method", "--html-math-method"):
        if pandoc_has_option(option):
            return [f"{option}={method}"]
    flag = HTML_MATH_SHORT_FLAGS.get(method)
    return [flag] if flag else []


def cascaded_option(md_path: Path, metadata_files: list[Path], key: str):
    """``pdfmd-options.<key>``: the document's own, else its metadata files' in order, else the config's (None if none
    sets it); a mapping merged field by field (see first_pdfmd_option)."""
    return core.first_pdfmd_option(md_path, metadata_files, key)


def default_output_format(md_path: Path, metadata_files: list[Path]) -> str | None:
    """``pdfmd-options.default-output`` (a Pandoc writer name, or pdf), None
    if unset. Only Markdown documents have one."""
    if md_path.suffix.lower() not in (".md", ".markdown"):
        return None
    value = cascaded_option(md_path, metadata_files, "default-output")
    if not isinstance(value, str) or not value.strip():
        return None
    name = value.strip().casefold().lstrip(".")
    name = DEFAULT_OUTPUT_ALIASES.get(name, name)
    if name == "ascii" or name.startswith("ascii:"):
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.default-output cannot be '{name}'; ASCII output is "
                         "asked for on the command line (--to ascii) or by the output's name (-o x.ascii.txt)")
    ASSEMBLED_FORMAT = core.ASSEMBLED_FORMAT
    if name == ASSEMBLED_FORMAT:
        raise SystemExit(f"{core.display_path(md_path)}: pdfmd-options.default-output cannot be "
                         f"'{ASSEMBLED_FORMAT}'; use --stop-at markdown")
    return name


def html_settings(md_path: Path, metadata_files: list[Path]) -> dict:
    value = cascaded_option(md_path, metadata_files, "html")
    return value if isinstance(value, dict) else {}


def html_pandoc_args(md_path: Path, metadata_files: list[Path], pandoc_options: list[str],
                     cli_self_contained: bool | None, note) -> list[str]:
    """The Pandoc arguments an HTML target adds (see the comment above
    HTML_TARGETS), with MathML unless the user chooses a method."""
    settings = core.html_settings(md_path, metadata_files)
    truthy = lambda value: value is True or str(value).casefold() in {"true", "yes", "on"}
    self_contained = (cli_self_contained if cli_self_contained is not None
                      else truthy(settings.get("self-contained", False)))
    standalone = self_contained or truthy(settings.get("standalone", False))
    out: list[str] = []
    if standalone and not core.has_standalone_option(pandoc_options):
        out.append("--standalone")
    if self_contained and "--embed-resources" not in pandoc_options and "--self-contained" not in pandoc_options:
        out.append("--embed-resources" if core.pandoc_version() >= (2, 19) else "--self-contained")
        note("HTML", f"{md_path}: self-contained: one file, resources inlined")
    elif standalone:
        note("HTML", f"{md_path}: a full page (--standalone)")
    out += core.deferred("pdfmd_bridge.html_math", "arguments")(settings, pandoc_options, md_path, metadata_files)
    css = settings.get("css")
    for name in ([css] if isinstance(css, str) else css if isinstance(css, list) else []):
        out += ["--css", str((md_path.parent / str(name)).resolve())]
    if standalone and not any(item.startswith(("--metadata=pagetitle", "-Mpagetitle")) for item in pandoc_options):
        if not (core.frontmatter_value(md_path, "title") or core.frontmatter_value(md_path, "pagetitle")
                or any(core.metadata_file_yaml(item).get("title") or core.metadata_file_yaml(item).get("pagetitle")
                       for item in metadata_files)):
            out += ["--metadata", f"pagetitle={md_path.stem}"]
    return out

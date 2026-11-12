"""The command names that other tools answer to: `mdpdf`, `md2pdf`, `inkmd`, `batchmd` and `pan-tec` are console entry points
of pdfmd (`pyproject.toml`: `pdfmd:mdpdf_main` and the rest), each of which translates that tool's own command line into pdfmd's
and runs `main()`.

Moved out of `pdfmd.py` unchanged (v3.33.15, SPLIT.md), with `INKMD_KEYS`, `MD2PDF_ENGINE_WORDS`, `MD2PDF_IGNORED_VALUE_KEYS`,
`MD2PDF_VALUE_KEYS`, `MDPDF_KEYS`, `MDPDF_NPM_FLAGS` and `MDPDF_NPM_VALUE_KEYS`. `core` is the `pdfmd` module, bound by `pdfmd.py`
when it loads (the first binding wins); the pdfmd names the code uses (`main`, `build_parser`) are read as `core.X` when it runs.
`expand_glob` is `glob.glob`, imported here as `pdfmd.py` imports it.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import tempfile
from glob import glob as expand_glob
from pathlib import Path
from tempfile import NamedTemporaryFile

from pdfmd_base import core


MDPDF_KEYS = {"-o": "--out", "--output": "--out", "-h": "--header", "--header": "--header",
              "-f": "--footer", "--footer": "--footer", "-t": "--pdf-title", "--title": "--pdf-title",
              "-s": "--pdf-subject", "--subject": "--pdf-subject", "-a": "--pdf-author",
              "--author": "--pdf-author", "-k": "--pdf-keywords", "--keywords": "--pdf-keywords",
              "-p": "--paper", "--paper": "--paper"}


# The npm `mdpdf` (Puppeteer; elliotblackburn) has other keys under the same command name (v3.30.41). They do not collide
# with the PyPI mdpdf's, except --header/--footer: a template "left,middle,right" there, an HTML file here, told apart by the value.
MDPDF_NPM_VALUE_KEYS = ("--style", "--h-height", "--f-height", "--border", "--border-top", "--border-left", "--border-bottom",
                        "--border-right", "--format", "--orientation")
MDPDF_NPM_FLAGS = ("--gh-style", "--no-emoji", "--debug")


# The `md2pdf` command (v3.30.40). Several tools install that name: jmaupetit's `md2pdf` (-i -o -c -e -C -W), `md-to-pdf`
# (--stylesheet --css --pdf-options --config-file ... and a file as the only argument) and kxxoling's (--theme). The keys do not
# collide in meaning, so one table answers all three; what pdfmd has no use for is named on stderr and left out, never silently.
MD2PDF_VALUE_KEYS = {"-i": "", "--input": "", "-o": "--out", "--output": "--out", "-c": "--css", "--css-file": "--css",
                     "--stylesheet": "--css", "-W": "-j", "--workers": "-j", "--document-title": "--pdf-title"}
MD2PDF_IGNORED_VALUE_KEYS = ("-e", "--extras", "-C", "--config", "--config-file", "--body-class", "--page-media-type",
                             "--highlight-style", "--marked-options", "--pdf-options", "--launch-options",
                             "--gray-matter-options", "--port", "--md-file-encoding", "--stylesheet-encoding",
                             "--watch-options", "--basedir", "--theme")
MD2PDF_ENGINE_WORDS = frozenset({"lualatex", "xelatex", "pdflatex", "tectonic", "typst", "weasyprint", "wkhtmltopdf", "context",
                                 "pandoc", "tex", "html", "calibre", "inkmd", "native", "soffice", "edge", "chrome", "brave",
                                 "chromium", "prince", "groff", "pdfroff", "pagedjs-cli"})


INKMD_KEYS = {"-o": "--out", "--out": "--out", "--output": "--out", "--page-size": "--paper"}


def mdpdf_npm_file(value: str) -> bool:
    """A --header/--footer value that is the npm mdpdf's HTML file, not the PyPI mdpdf's template."""
    return value.lower().endswith((".html", ".htm", ".hbs")) or Path(value).is_file()


def mdpdf_npm_length(value: str) -> str:
    """A length of the npm mdpdf (mm, cm, in, px) as one the page setup knows: px are CSS pixels, 0.75 pt each."""
    match = re.fullmatch(r"\s*([0-9.]+)\s*px\s*", value)
    return f"{float(match.group(1)) * 0.75:g}pt" if match else value.strip()


def mdpdf_translate(argv: list[str]) -> list[str]:
    """The ``mdpdf`` command's own keys (``-o -h -f -t -s -a -k -p`` and their long forms) as pdfmd options,
    plus what mdpdf always does: bookmarks and attached linked files. Anything else is a pdfmd option as
    usual (the npm mdpdf's ``--style --format --orientation --border* MDPDF_STYLES`` too, its ``--header FILE.html`` and the rest named
    on stderr and left out). Wildcards in the inputs are expanded here, as mdpdf does, for shells that do not, and several
    Markdown inputs are combined into one PDF (``--report``), as mdpdf does. A last positional ending in
    ``.pdf`` after another positional is the output (``mdpdf in.md out.pdf``, the form of the Go ``mdpdf`` and
    ``md2static``); mdpdf itself never reads a PDF, and an option's value (``--cover x.pdf``) is not mistaken
    for it because the token before it is the option."""
    out, rest, literal, documents = ["--bookmarks", "--attach-links"], list(argv), False, 0
    previous, second = None, None                 # the last token read, when it was a positional; where the output is
    npm: dict[str, str] = {}                      # the npm mdpdf's values by key; ignored: what pdfmd has no use for
    ignored: list[str] = []
    while rest:
        token = rest.pop(0)
        if literal or token == "-" or not token.startswith("-"):
            matches = sorted(expand_glob(token)) if re.search(r"[*?\[]", token) else []
            out += matches or [token]
            documents += sum(1 for name in (matches or [token])
                             if Path(name).suffix.lower() in (".md", ".markdown") and Path(name).is_file())
            if second is None and previous is not None and not matches and token.lower().endswith(".pdf") \
                    and not previous.lower().endswith(".pdf") and (not rest or (rest[0].startswith("-") and not literal)):
                second = len(out) - 1           # `mdpdf in.md out.pdf`: the output as a second positional (v3.30.39)
            previous = token
            continue
        previous = None
        if token == "--":
            literal = True
            continue
        if token.startswith("--"):
            key, equals, value = token.partition("=")
        else:
            key, equals, value = token[:2], "", token[2:]
        if token.startswith("--") and (key in MDPDF_NPM_VALUE_KEYS or key in MDPDF_NPM_FLAGS):
            if key in MDPDF_NPM_FLAGS:
                ignored.append(key)
            elif equals or rest:
                npm[key] = value if equals else rest.pop(0)
            else:
                out.append(token)                     # missing value: let the parser complain
            continue
        if key not in MDPDF_KEYS:
            out.append(token)
            continue
        if not (equals or value):
            if not rest:
                out.append(MDPDF_KEYS[key])           # missing value: let the parser complain
                continue
            value = rest.pop(0)
        if key in ("--header", "--footer") and mdpdf_npm_file(value):
            ignored.append(f"{key} {value}")          # an HTML file for Puppeteer: pdfmd's header is a template
            continue
        out += [MDPDF_KEYS[key], value.casefold() if key in ("-p", "--paper") else value]
    if second is not None and "--out" not in out:
        out[second:second + 1] = ["--out", out[second]]
    style = npm.pop("--style", None) or os.environ.get("MDPDF_STYLES")
    if style:
        out += ["--css", style]
        if not any(token in ("-e", "--engine") or token.startswith(("-e", "--engine=")) for token in out):
            out = ["-e", "html", *out]                # only an HTML engine reads a style sheet
    if npm.get("--format") and "--paper" not in out:
        out += ["--paper", npm["--format"].casefold()]
    if npm.get("--orientation", "").casefold() == "landscape":
        out += ["-V", "geometry:landscape"]       # every engine reads it (paper_variables)
    for side, key in (("margin", "--border"), ("top", "--border-top"), ("left", "--border-left"), ("bottom", "--border-bottom"),
                      ("right", "--border-right")):
        if npm.get(key):
            out += ["-V", f"geometry:{side}={mdpdf_npm_length(npm[key])}"]
    for key in ("--h-height", "--f-height"):
        if key in npm:
            ignored.append(f"{key} {npm[key]}")
    if ignored:
        print(f"NOTE  mdpdf: pdfmd has no use for {', '.join(ignored)}; left out", file=sys.stderr)
    if documents > 1 and "--report" not in out and "-r" not in out:
        out.append("--report")                      # several inputs make one PDF, as in mdpdf
    return out


def mdpdf_main() -> None:
    """Entry point of the ``mdpdf`` command: pdfmd, answering to mdpdf's keys."""
    sys.argv[1:] = mdpdf_translate(sys.argv[1:])
    core.main()


def md2pdf_translate(argv: list[str]) -> list[str]:
    """The `md2pdf` command's keys as pdfmd options: ``-i/--input`` are just inputs, ``-o`` the output, ``-c/--css/--stylesheet``
    a style sheet (which only an HTML engine reads, so ``-e html`` is added unless an engine is named; md-to-pdf's ``--css`` is a
    string of styles, not a file, and is dropped), ``-W`` the jobs,
    ``--as-html`` HTML output, ``-w/--watch`` a watch. ``-e`` is an engine when its value is one (as in pdfmd) and jmaupetit's
    Markdown extension otherwise; ``--theme`` is a style sheet when it names a .css file. Keys that pdfmd has no counterpart for
    (extensions, Puppeteer and marked options, a config file) are said once on stderr and dropped, with their value."""
    out, rest, ignored, css, engine = [], list(argv), [], False, False
    while rest:
        token = rest.pop(0)
        key, equals, value = token.partition("=") if token.startswith("--") else (token[:2], "", token[2:])
        if not token.startswith("-") or token == "-":
            out.append(token)
            continue
        if key in ("-e", "--engine") and (equals or value or rest):
            given = value if (equals or value) else rest.pop(0)
            if key == "--engine" or given.casefold().split(",")[0].strip() in MD2PDF_ENGINE_WORDS:
                out += ["-e", given]
                engine = True
            else:
                ignored.append(f"{key} {given}")
            continue
        if key == "--css":                                   # a file in jmaupetit's, a string of styles in md-to-pdf's
            given = value if (equals or value) else (rest.pop(0) if rest else "")
            if "{" in given or not given:
                ignored.append(f"--css {given}".strip())
            else:
                out += ["--css", given]
                css = True
            continue
        if key in MD2PDF_VALUE_KEYS or key in MD2PDF_IGNORED_VALUE_KEYS:
            if not (equals or value):
                if not rest:
                    out.append(MD2PDF_VALUE_KEYS.get(key) or token)       # missing value: let the parser complain
                    continue
                value = rest.pop(0)
            if key == "--theme" and value.lower().endswith(".css"):
                out += ["--css", value]
                css = True
            elif key in MD2PDF_VALUE_KEYS:
                target = MD2PDF_VALUE_KEYS[key]
                out += [target, value] if target else [value]
                css = css or target == "--css"
            else:
                ignored.append(f"{key} {value}")
            continue
        if token == "--as-html":
            out += ["--to", "html"]
        elif token == "--devtools":
            ignored.append(token)
        else:
            out.append(token)
    if ignored:
        print(f"NOTE  md2pdf: pdfmd has no use for {', '.join(ignored)}; left out", file=sys.stderr)
    if css and not engine and "html" not in out:
        out = ["-e", "html", *out]
    return out


def md2pdf_main() -> None:
    """Entry point of the ``md2pdf`` command: pdfmd, answering to the keys of the tools that install that name."""
    sys.argv[1:] = md2pdf_translate(sys.argv[1:])
    core.main()


def inkmd_translate(argv: list[str]) -> list[str]:
    """The ``inkmd`` command's keys as pdfmd options: ``-o/--output`` and ``--page-size`` are renamed,
    ``--family --no-autolinks --no-html --allow-unsafe-urls --allow-remote-images --emoji-fallback`` are
    pdfmd's own, and ``-e inkmd`` is added unless an engine was named. Everything stays where it was."""
    out, rest = [], list(argv)
    while rest:
        token = rest.pop(0)
        key, equals, value = (token.partition("=") if token.startswith("--") else (token[:2], "", token[2:]))
        if not token.startswith("-") or key not in INKMD_KEYS:
            out.append(token)
            continue
        if not (equals or value):
            if not rest:
                out.append(INKMD_KEYS[key])                   # missing value: let the parser complain
                continue
            value = rest.pop(0)
        out += [INKMD_KEYS[key], value.casefold() if key == "--page-size" else value]
    if not any(token == "--engine" or token.startswith("--engine=") or (token.startswith("-e") and not token.startswith("--"))
               for token in out):
        out = ["-e", "inkmd", *out]
    return out


def inkmd_main() -> None:
    """Entry point of the ``inkmd`` command: pdfmd with the built-in renderer unless another engine is named,
    answering to inkmd's keys. Like inkmd it reads standard input when no file is given and writes the PDF to
    standard output when ``-o -`` is given, or when no ``-o`` is given and standard output is not a terminal;
    otherwise (a file and no ``-o`` at a terminal) it is pdfmd: ``name.pdf`` beside the input."""
    options = inkmd_translate(sys.argv[1:])
    if any(token in ("--version", "--help", "-h") for token in options):
        sys.argv[1:] = options
        core.main()
        return
    named, _ = core.build_parser().parse_known_args(options)
    output = str(named.out) if named.out is not None else None
    stdin = not named.path or [str(path) for path in named.path] == ["-"]
    if output == "-":                                       # the pair `--out -`
        at = options.index("--out")
        options = options[:at] + options[at + 2:]
    if stdin:
        options = [token for token in options if token != "-"]
    to_stdout = output == "-" or (output is None and (stdin or not sys.stdout.isatty()))
    if stdin and sys.stdin.isatty() and output is None and sys.stdout.isatty():
        raise SystemExit("inkmd: give a file to read, or -o FILE (standard input and output are both terminals)")
    with tempfile.TemporaryDirectory(prefix="inkmd-") as scratch:
        made = Path(scratch) / "out.pdf"
        arguments = list(options)
        temporary_input = None
        if stdin:
            try:                                  # beside the cwd so relative image paths resolve, as in inkmd
                handle = NamedTemporaryFile("wb", suffix=".md", prefix=".inkmd-stdin-", dir=Path.cwd(), delete=False)
            except OSError:
                handle = NamedTemporaryFile("wb", suffix=".md", dir=scratch, delete=False)
            with handle:
                handle.write(sys.stdin.buffer.read())
            temporary_input = Path(handle.name)
            arguments.append(str(temporary_input))
        if to_stdout:
            arguments += ["--out", str(made), "--no-stamp"]
        sys.argv[1:] = arguments
        code = 0
        try:
            with contextlib.redirect_stdout(sys.stderr) if to_stdout else contextlib.nullcontext():
                core.main()
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
            if stop.code is not None and not isinstance(stop.code, int):
                print(stop.code, file=sys.stderr)
        finally:
            if temporary_input is not None:
                temporary_input.unlink(missing_ok=True)
        if code == 0 and to_stdout and made.is_file():
            sys.stdout.buffer.write(made.read_bytes())
            sys.stdout.buffer.flush()
        raise SystemExit(code)


def batchmd_translate(argv: list[str]) -> list[str]:
    """The ``batchmd`` command is ``pdfmd -b``: batch mode over one folder. With no folder named, the
    current one (``pdfmd -b`` alone refuses). Every argument stays where it was, as a pdfmd option."""
    out = list(argv)
    if not any(token in ("-h", "--help", "--version") for token in out):
        named, _ = core.build_parser().parse_known_args(out)
        if not named.path:
            out.append(".")
    return ["--batch", *out]


def batchmd_main() -> None:
    """Entry point of the ``batchmd`` command: ``pdfmd -b``, with pdfmd's own options."""
    sys.argv[1:] = batchmd_translate(sys.argv[1:])
    core.main()


def pan_tec_translate(argv: list[str]) -> list[str]:
    """The ``pan-tec`` command (v3.29.6): the first version of pdfmd was a shell function, `pandoc "$@"
    --pdf-engine=tectonic --pdf-engine-opt=--chatter=minimal`. The same, with pdfmd behind it: `-e tectonic` and
    Tectonic's quiet output are added unless the command line names an engine / a chatter level of its own."""
    out = list(argv)
    if not any(token == "--engine" or token.startswith("--engine=") or token == "--pdf-engine"
               or token.startswith("--pdf-engine=") or (token.startswith("-e") and not token.startswith("--"))
               for token in out):
        out = ["-e", "tectonic", *out]
    if not any("chatter" in token for token in out):
        out.append("--pdf-engine-opt=--chatter=minimal")
    return out


def pan_tec_main() -> None:
    """Entry point of the ``pan-tec`` command: pdfmd with the Tectonic engine, quiet, as in its first version."""
    sys.argv[1:] = pan_tec_translate(sys.argv[1:])
    core.main()

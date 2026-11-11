"""The command line: `build_parser`, the whole argparse tree of `pdfmd` (every option, its help text and the topics of
`--help TOPIC`), with the `type=` checks of its options (`csv_note_argument`, `csv_count_argument`, `table_keep_argument`,
`calc_round_argument`, `calc_digits_argument`) and the modes `--seed-labels` offers (`pdfmd_labels_modes`).

Moved out of `pdfmd.py` unchanged (v3.33.40, SPLIT.md), with `BUILD_LOG_MODES` (`--build-log MODE`) and `STOP_STAGES`
(`--stop-at STAGE`); the comments that explain the build log and the stages stay in `pdfmd.py`, beside `BUILD_LOG_CLI` and
`ASSEMBLED_FORMAT`. `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins); the pdfmd names the
code uses (`ASSEMBLED_SUFFIX`, `BOPEN_HELP`, `BUNDLE_MAX_MB`, `CACHE_LOCATIONS`, `CALC_ALIGNS`, `CALC_ROUNDS`, `CSS_SCOPES`,
`LUA_MODES`, `METADATA_PRECEDENCES`, `PATH_STYLES`, `PDFMD_VERSION`, `SEED_CALC_MODES`, `STAMP_MODES`, `STAMP_SCOPES`,
`STAMP_STORES`, `UNCLOSED_WORDS`, `ansi_width_argument`, `calc_digits_value`, `csv_count`, `csv_note_mode`, `install_kind`,
`table_keep_count` and `uninstall_kind`) are read as `core.X` when `build_parser` runs. `core.install_kind`,
`core.uninstall_kind` (`pdfmd_install`'s, re-exported by `pdfmd.py`) and `core.ansi_width_argument` (a stand-in there that loads
`pdfmd_ansi.cli`) are the same function objects the options had before, so argparse's "invalid ... value" messages name them as
before. `pdfmd_help` and `pdfmd_labels` are imported inside the functions, as they were. `pdfmd.py` re-exports `build_parser`
(`main`, `lib/pdfmd_compat`, `lib/pdfmd_setup` and the tests call it).
"""

from __future__ import annotations

import argparse
from pathlib import Path

core = None


def csv_note_argument(value: str) -> str:
    found = core.csv_note_mode(value)
    if found is None:
        raise argparse.ArgumentTypeError(f"{value!r}: short, off or full")
    return found


def csv_count_argument(value: str) -> int | str:
    found = core.csv_count(value)
    if found is None:
        raise argparse.ArgumentTypeError(f"{value!r}: a whole number of rows or columns, or all")
    return found


def table_keep_argument(value: str) -> int:
    found = core.table_keep_count(value)
    if found is None:
        raise argparse.ArgumentTypeError(f"{value!r}: a whole number of rows (0 lets every table break)")
    return found


def calc_round_argument(value: str) -> str:
    if value.strip().lower() not in core.CALC_ROUNDS:
        raise argparse.ArgumentTypeError(f"{value!r}: even (2.5 rounds to 2, as R and Python do) or away (2.5 rounds to 3)")
    return value.strip().lower()


def calc_digits_argument(value: str) -> str:
    found = core.calc_digits_value(value)
    if found is None:
        raise argparse.ArgumentTypeError(f"{value!r}: like 4sf (four significant figures) or 2dp (two decimal places)")
    return found


BUILD_LOG_MODES = ("on", "failed", "off")
STOP_STAGES = ("markdown", "tex", "pdf")


def pdfmd_labels_modes() -> tuple[str, ...]:
    try:
        import pdfmd_labels
    except ImportError:
        return ("off",)
    return pdfmd_labels.MODES


def build_parser() -> argparse.ArgumentParser:
    try:
        from pdfmd_help import TieredHelp           # without pdfmd_help argparse keeps its one long page (since 3.33.0 not a shipped case)
    except ImportError:
        TieredHelp = None
    parser = argparse.ArgumentParser(description="Convert Markdown (and other Pandoc-readable) files to PDF or another format with Pandoc.",
                                     add_help=TieredHelp is None)
    if TieredHelp is not None:
        parser.add_argument("-h", "--help", action=TieredHelp)
    parser.add_argument("--version", action="version", version=f"pdfmd {core.PDFMD_VERSION}")
    parser.add_argument("path", type=Path, nargs="*", help="Markdown name, input files or folders; several paths build separately (default: current directory)")
    parser.add_argument("-p", "--presentation", action="store_true", help="create Beamer slides")
    parser.add_argument("--slide-level", type=int, help="Beamer heading level used for slide breaks")
    parser.add_argument("-b", "--batch", action="store_true", help="build files and folders separately (folders select *.md); skip non-inputs")
    parser.add_argument("-r", "--report", "--book", action="store_true",
                        help="combine all Markdown files in PATH into one PDF")
    parser.add_argument("--recursive", action="store_true",
                        help="include Markdown files in subdirectories (batch and report/book modes; "
                             "off by default, both search the given directory only)")
    parser.add_argument("-o", "--out", "--output", type=Path,
                        help="output directory (batch) or filename (single-file/report/book); "
                             "a recognized extension (e.g. .html, .tex, .typ) also selects the "
                             "target format, same as --to")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=None,
                        help="a build that printed a warning (an engine that failed and was replaced, a missing glyph, "
                             "a Pandoc [WARNING]...) counts as failed: the output is kept, the exit code is 1 "
                             "(also `pdfmd-options: {strict: true}`); --no-strict overrides the document")
    parser.add_argument("--build-time", action=argparse.BooleanOptionalAction, default=None,
                        help="print how long a build took on its closing line (`OK  a.md > a.pdf  in 3:07`; on by default; "
                             "--verbose adds the time of every step). Also `pdfmd-options: {build-time: off}`")
    parser.add_argument("--build-log", choices=BUILD_LOG_MODES, metavar="MODE",
                        help="the record of each build, kept in the cache for debugging afterwards (on, failed: only a build "
                             "that failed, off). Also `pdfmd-options: {build-log: failed}`; `build-log-keep` and "
                             "`build-log-max-size` (KB) are settings too")
    parser.add_argument("--last-build", action="store_true",
                        help="print the newest record of FILE's build (see --build-log)")
    parser.add_argument("--failed", action="store_true", help="with --last-build: the newest record of a build that failed")
    parser.add_argument("--serve", nargs="?", const="", metavar="FOLDER",
                        help="the web UI's local server for the project FOLDER (default: the working folder): 127.0.0.1, a random port, "
                             "a token. Prints one JSON line {api, url, port, token, root}; open the url. Stops with Ctrl-C")
    parser.add_argument("--api", nargs="+", metavar="METHOD PATH [JSON]",
                        help="one request of the web UI's API, answered as JSON on stdout, for the project in the working folder: "
                             "`pdfmd --api GET /api/project`, `pdfmd --api GET '/api/file?path=report.md'`, "
                             "`pdfmd --api POST /api/render '{\"text\": \"# Hi\"}'`; JSON `-` reads it from standard input")
    parser.add_argument("--time-format", metavar="STYLE",
                        help="how a time is written: auto (0.42 s, 12.4 s, 3:07, 1:02:03, 1 d 02:03:04), clock (03:07), "
                             "seconds (12.4 s), words (3 min 7 s), or a template with {d} {h} {hh} {m} {mm} {s} {ss} {s1} "
                             "{s2} {ms}, e.g. '{h}:{mm}:{ss}'. Also `pdfmd-options: {time-format: clock}`")
    parser.add_argument("--max-asset-mb", type=float, metavar="MB",
                        help="a size budget for one image or data file: the build warns about each one over it before it "
                             "starts, --check reports it (asset-large). Also `pdfmd-options: {max-asset-mb: 5}`; 0 turns "
                             "a document's budget off")
    parser.add_argument("--max-output-mb", type=float, metavar="MB",
                        help="a size budget for the file that is made: the build warns when it is over, and names the "
                             "largest images behind it. Also `pdfmd-options: {max-output-mb: 20}`; 0 turns it off")
    parser.add_argument("--stop-at", choices=STOP_STAGES, default=None, metavar="STAGE",
                        help="stop the build early, after STAGE: 'markdown' -- the assembled Markdown "
                             "(the parts joined into one file, NAME.assembled.md); 'tex' -- the "
                             "standalone .tex a LaTeX engine would get (same as --to latex, or "
                             "beamer with -p); 'pdf' -- the whole build (default). An -o ending "
                             f"{core.ASSEMBLED_SUFFIX} also means 'markdown'")
    parser.add_argument("--assemble-only", action="store_true",
                        help="shorthand for --stop-at markdown")
    parser.add_argument("--merge", action="store_true",
                        help="one standalone Markdown file that builds alone, anywhere: the parts joined and everything "
                             "pdfmd finds beside the document (metadata, preamble, Lua filters, bibliography, data files "
                             "and pictures) embedded, NAME.assembled.md (or -o). Shorthand for --assemble-only "
                             "--embed-metadata all; --unpack gives the files back"),
    parser.add_argument("--embed-metadata", nargs="*", default=None, metavar="KIND",
                        help="with --stop-at markdown: fold what pdfmd discovers beside the document "
                             "into the assembled file, so it builds the same without them. KIND is "
                             "metadata (the YAML files, merged with the front matter), preamble (the "
                             "LaTeX preamble, into header-includes), lua (the Lua filters, see "
                             "--lua-mode) or bibliography (the bibliography and CSL files the metadata "
                             "names; the style itself only with `csl`), hst (the NAME.hst history file), csl (the "
                             "citation style, 10-90 KB, not in the default) or files (the images, CSV data and "
                             "included files the text and preamble point at; text as it is, the rest base64: "
                             "not in the default as it can be big); none given means all but files and csl, "
                             "`all` means every kind")
    parser.add_argument("--no-embed-metadata", action="store_true",
                        help="turn off embedding for this run, even where a document's "
                             "pdfmd-options.embed asks for it")
    parser.add_argument("--lua-mode", choices=core.LUA_MODES, default=None,
                        help="how --embed-metadata carries Lua filters (default: the document's "
                             "pdfmd-options.embed.lua, else embed): 'embed' -- the whole "
                             "filter in a {=pdfmd} block at the end of the file; 'ref' -- only its "
                             "path (a missing one is a warning, and the build goes on); 'apply' -- run "
                             "now, Markdown to Markdown, so the text already has their effect (a "
                             "filter that checks FORMAT is embedded instead); 'off' -- not carried")
    parser.add_argument("--strip-comments", dest="strip_comments", action="store_true", default=None,
                        help="remove every <!-- --> comment from the Markdown that leaves your hands: "
                             "the assembled file (--stop-at markdown) and the source attached to a PDF. "
                             "Comments inside code blocks and code spans are text and stay, and so do "
                             "pdfmd's own markers (<!-- pdfmd-... -->, <!-- pagebreak -->). A document "
                             "sets it with pdfmd-options.strip-comments")
    parser.add_argument("--keep-comments", dest="strip_comments", action="store_false",
                        help="keep comments, even where a document's pdfmd-options.strip-comments says to "
                             "strip them")
    parser.add_argument("--strip-comments-in", default="", metavar="KINDS",
                        help="strip comments from just these kinds of source (comma-separated: markdown, "
                             "preamble, bibliography, csl, metadata), whatever the rest do. Kept, the YAML "
                             "files come back as written; Lua filters are never touched")
    parser.add_argument("--keep-comments-in", default="", metavar="KINDS",
                        help="keep the comments of these kinds of source (comma-separated, as "
                             "--strip-comments-in), where the rest are stripped")
    parser.add_argument("--attach-bibliography", choices=("used", "all"), default=None,
                        help="what the attached bibliography holds (and the one --assemble-only and --merge "
                             "embed): 'used' (default) only the entries the "
                             "text cites (and what they cross-reference; all of them if it has "
                             "`nocite: '@*'`), 'all' the file as it is. A document sets it with "
                             "pdfmd-options.attach-bibliography")
    parser.add_argument("--css", action="append", default=[], metavar="FILE",
                        help="a style sheet for the HTML writers (HTML, EPUB, the HTML engines' PDF, Calibre), after the "
                             "ones found beside the document (NAME.css, pdfmd.css) and named in its metadata (css:, "
                             "pdfmd-options.css); repeat it for more. With --css-scope all it is read for the paper, "
                             "margins, body font and size, line spacing, link colour and code font of the other writers too")
    parser.add_argument("--css-scope", dest="css_scope", choices=core.CSS_SCOPES, default=None,
                        help="what a style sheet is for: html (default) the writers that read CSS, all those and the "
                             "settings LaTeX, Typst and Word take from the parts of it that say them (@page size and "
                             "margin, body and a and code rules; @media print counts, @media screen does not), below "
                             "what the document, its metadata and the command line set. A document sets it with "
                             "pdfmd-options.css-scope")
    parser.add_argument("--attach-csl", dest="attach_csl", action="store_true", default=None,
                        help="also attach the citation style (.csl) the metadata names, with the source: it is not "
                             "attached by default (a style is 10-90 KB, apa.csl 86 KB, and the global metadata sets one "
                             "for every document), so a machine that builds the source again needs the style by its name. "
                             "A document sets it with pdfmd-options.attach-csl; --embed-metadata csl does the same for "
                             "an assembled file")
    parser.add_argument("--no-attach-csl", dest="attach_csl", action="store_false",
                        help="attach no style, even where a document's pdfmd-options.attach-csl asks for it")
    parser.add_argument("--attach-source", "--embed-source", dest="attach_source", action="store_true",
                        default=None,
                        help="attach the document's whole source (the assembled Markdown, comments "
                             "stripped, plus a manifest of the original layout) to the PDF it builds, so "
                             "`pdfmd --restore FILE.pdf` can write the folder back. A document sets it with "
                             "pdfmd-options.attach-source (alias embed-source)")
    parser.add_argument("--no-attach-source", dest="attach_source", action="store_false",
                        help="attach nothing, even where a document's pdfmd-options.attach-source asks for it")
    parser.add_argument("--keep-source", nargs="?", const="packed", choices=("packed", "readable"), default=None,
                        metavar="MODE",
                        help="end a Markdown output (--to gfm, gfm+raw, markdown ...) with its whole source in one "
                             "HTML comment, so `pdfmd --restore FILE.md` can write the folder back. MODE packed "
                             "(default: compressed, nothing in the source can close the comment) or readable (the "
                             "text, `>` escaped). A document sets it with pdfmd-options.keep-source")
    parser.add_argument("--no-keep-source", dest="keep_source", action="store_const", const=False,
                        help="keep nothing, even where a document's pdfmd-options.keep-source asks for it")
    parser.add_argument("--bundle", nargs="?", const="referenced", choices=("sources", "referenced", "all"), default=None,
                        help="with the source, attach the files it cannot carry: 'sources' (what an attached "
                             "PDF gets without this flag) the LaTeX inputs and data the text and preamble "
                             "read, never images (the PDF holds those and --restore takes them out), "
                             "'referenced' (default for --bundle alone) those and the image files, 'all' every file in the "
                             "document's folder except output and housekeeping (hidden files, .aux/.log, "
                             "backups). Implies --attach-source; --restore puts them back. A document sets it "
                             "with pdfmd-options.bundle (sources | true | all | false); pdfmd-options.bundle-max-mb (default "
                             f"{core.BUNDLE_MAX_MB}) caps the size")
    parser.add_argument("--bundle-packages", dest="bundle_packages", action="store_true", default=None,
                        help="with --bundle, also store the LaTeX packages and classes of your own TeX tree "
                             "that a preamble loads (a house style installed in texmf-home), so a machine "
                             "without them builds the same. Off by default: they are recorded (name, version) "
                             "and restore tells what is missing. A document sets it with "
                             "pdfmd-options.bundle-packages")
    parser.add_argument("--no-bundle", dest="bundle", action="store_const", const="off",
                        help="attach the source alone, with no files beside it (no LaTeX inputs, no data), even where a document's "
                             "pdfmd-options.bundle asks")
    parser.add_argument("--bookmarks", action="store_true",
                        help="add PDF bookmarks from the Markdown headings when the engine made none "
                             "(ideas from mdpdf; always on under the `mdpdf` command)")
    parser.add_argument("--header", default=None, metavar="LEFT,MIDDLE,RIGHT",
                        help="running header printed on every page; fields may use {page} {pages} {header} "
                             "{date} {title}; write \\, for a comma inside a field")
    parser.add_argument("--footer", default=None, metavar="LEFT,MIDDLE,RIGHT",
                        help="running footer, same fields as --header")
    parser.add_argument("--attach-links", action="store_true",
                        help="attach the local files the document links to, with a paperclip in the margin beside the link")
    parser.add_argument("--paper", default=None, metavar="SIZE",
                        help="paper size (a4, letter ...), with the orientation if you like: a4,landscape; same as "
                             "-V papersize=SIZE, but written for each engine (LaTeX, Typst, WeasyPrint, Calibre, the "
                             "browsers and the native renderers all turn the page)")
    parser.add_argument("--paragraph-spacing", metavar="LENGTH", default=None,
                        help="the space between paragraphs, added to the line spacing: a length (6pt, 1em, 2mm; pt mm cm in "
                             "em), 0 for none, or auto (the default: each engine's own; with `indent: true` none). LaTeX and "
                             "Typst; the HTML engines take it from a style sheet. Also "
                             "`pdfmd-options: {paragraph-spacing: 6pt}`, or --setup")
    parser.add_argument("--family", choices=("helvetica", "times"), default=None,
                        help="font family of the built-in renderer (inkmd)")
    parser.add_argument("--no-autolinks", action="store_true",
                        help="built-in renderer: do not turn bare URLs and e-mail addresses into links")
    parser.add_argument("--no-html", action="store_true",
                        help="built-in renderer: show HTML as literal text instead of rendering the safe subset")
    parser.add_argument("--allow-unsafe-urls", action="store_true",
                        help="built-in renderer: allow javascript:, data:, file: links (trusted Markdown only)")
    parser.add_argument("--allow-remote-images", action="store_true",
                        help="built-in renderer: fetch http(s) images while building")
    parser.add_argument("--emoji-fallback", choices=("name", "drop"), default=None,
                        help="built-in renderer: an emoji its font lacks becomes a [name] label or is dropped")
    for name in ("title", "subject", "author", "keywords"):
        parser.add_argument(f"--pdf-{name}", default=None, metavar="TEXT",
                            help=f"set the PDF's {name} property (the document itself is unchanged)")
    parser.add_argument("--extract", action="store_true",
                        help="a PDF input that carries its own pdfmd source is restored by default; "
                             "--extract reads its pages instead (through batchocr), as any other PDF is")
    parser.add_argument("--restore", type=Path, default=None, metavar="FILE",
                        help="write back the folder layout the source a PDF carries (--attach-source), or a Markdown "
                             "file keeps (--keep-source), records (name.md, metadata/, parts/, ...) into "
                             "FILE's NAME.restored/ folder (or -o DIR); never overwrites. With --list, only show "
                             "what it carries")
    parser.add_argument("--list", dest="list_only", action="store_true",
                        help="with --restore: show what the PDF carries, write nothing")
    parser.add_argument("--self-contained", dest="self_contained", action="store_true", default=None,
                        help="for an HTML target: one file with everything inlined (images, CSS; "
                             "--standalone --embed-resources, MathML for math). A document sets it "
                             "with `pdfmd-options: {html: {self-contained: true}}`")
    parser.add_argument("--no-self-contained", dest="self_contained", action="store_false",
                        help="for an HTML target: not self-contained, even where the document says so")
    parser.add_argument("--unpack", action="store_true",
                        help="write what an assembled file embeds (Lua filters, preamble, merged "
                             "metadata) back out as files into NAME.unpacked/ (or -o DIR), checking "
                             "each filter's hash; never overwrites, never edits the file")
    parser.add_argument("--slim", action="store_true",
                        help="with --unpack: after writing the files, rewrite the assembled file "
                             "without what was unpacked, leaving the document plus its NAME.unpacked/ "
                             "folder, which pdfmd discovers by itself")
    parser.add_argument("--trust-embedded", action="store_true",
                        help="run Lua filters embedded in a document even if this pdfmd did not "
                             "write them (a filter can run any command; by default only ones this "
                             "machine's pdfmd embedded itself run)")
    parser.add_argument("--trust-lua", type=Path, nargs="+", metavar="PATH",
                        help="mark a folder (or one Lua filter as it is now) as yours: a discovered or named Lua filter "
                             "there is no longer noted as new or edited, and --strict does not skip it")
    parser.add_argument("-d", "-cwd", "--cwd", "--destination-cwd", action="store_true",
                        dest="destination_cwd",
                        help="save PDFs in the current working directory")
    parser.add_argument("-f", "--font", default=None, help="font to use if glyph fallback is needed")
    parser.add_argument("-e", "--engine", nargs="?", const="", default=None,
                        help="PDF engine, family (tex/html/typst/office), numeric shortcut, or alias; run "
                             "--check-dependencies to see engine choices. 'soffice' (family 'office') is "
                             "a last-resort fallback for Markdown/Pandoc input -- Pandoc -> .docx -> "
                             "headless LibreOffice -- tried only after every tex/typst/html engine has "
                             "failed or is missing in the unrestricted chain, or on request. 'calibre' "
                             "(Calibre's ebook-convert: Pandoc -> one HTML page with MathML -> PDF) and the browsers "
                             "chrome, chromium, edge, brave (family word 'browser': headless, printing the same "
                             "page) are last resorts of the automatic chain, after the numbered engines, and "
                             "are used first when named. With --to an "
                             "ebook or .doc, `-e calibre` / `-e soffice` also name the converter that writes "
                             "it. Meaningless (and ignored) when "
                             "--to targets another non-PDF format. Always wins over a document's own "
                             "pdf-engine/engine front-matter key (see below). A bare -e (no value) "
                             "explicitly requests the full, unrestricted fallback chain across every "
                             "installed engine, overriding even a family restriction in front matter -- "
                             "use it to force output out of a document that would otherwise refuse to "
                             "leave its family. With neither a value nor front matter, the same full "
                             "fallback chain applies by default. A comma list is an ordered chain, tried in "
                             "the order written and nothing else (-e typst,calibre,lualatex; a family word or "
                             "`pandoc`, every engine Pandoc drives, expands in place); a pdf-engine: setting "
                             "takes the same list")
    parser.add_argument("--engine-fallback", choices=("auto", "on", "missing", "off"), default=None, metavar="MODE",
                        help="what a PDF engine's failure does: on (the next engine is tried, whatever failed), missing (only "
                             "an engine that cannot run here falls through; an error in the document stops the build and "
                             "keeps the PDF already there), off (the first failure stops it), auto (default: on when the "
                             "PDF does not exist yet; else the chain starts with the engine that made it, as missing). "
                             "Also `pdfmd-options: {engine-fallback: MODE}`")
    parser.add_argument("-t", "--to", dest="to", default=None, metavar="FORMAT",
                        help="Pandoc target format, e.g. html, latex (tex), typst, plain (txt), docx; or an ebook only "
                             "Calibre writes: azw3, mobi, kepub, lit, lrf, pdb, rb, snb, tcr, pmlz, htmlz, txtz. "
                             "Default is pdf. An -o/--out filename with a recognized extension "
                             "(single-file/report modes only, e.g. -o notes.html) implies this too; "
                             "an explicit --to always wins. No PDF engine is involved, or required "
                             "to be installed, for a non-pdf target -- Pandoc writes that format directly. "
                             "Also png, jpg, tiff, eps, ps, svg (pictures; see --crop), and a list without spaces: "
                             "--to png,docx,tex (one run each; -o is then a folder)")
    parser.add_argument("--from", dest="from_format", default=None, metavar="FORMAT",
                        help="Pandoc source format override (no short flag: -f is --font). Only needed "
                             "when Pandoc's own extension-based guess is wrong, e.g. a .txt file that "
                             "is actually reStructuredText: --from rst")
    parser.add_argument("--install", type=core.install_kind, metavar="KIND",
                        help="install an optional piece for pdfmd to use: 'pandoc' (the real Pandoc from "
                             "PyPI's pypandoc_binary, about 35 MB), 'typst' (Typst's release binary from "
                             "GitHub, into pdfmd's own tools folder), 'full' (both: a complete Markdown-to-PDF "
                             "setup with no admin rights), 'math' (md2pdf with offline math, about 150 MB, "
                             "Python 3.11+), 'math:mathjax' (MathJax 4 and its STIX Two math font, about 12 MB to download, and node "
                             "when there is none, about 30 MB: WeasyPrint's PDFs then have their math typeset by MathJax), "
                             "'math:katex' (KaTeX, about 1.5 MB, and node when there is none, "
                             "about 30 MB: WeasyPrint's PDFs then typeset math, KaTeX alone or what MathJax cannot read), 'diagram' (D2's release binary, 17 MB, and Graphviz as "
                             "WebAssembly run by node, 2 MB: ```d2 and ```dot blocks are drawn; diagram:d2 or diagram:dot "
                             "alone), 'core:tex' (also 'cortex': Pandoc and Tectonic, the self-contained LaTeX engine, "
                             "about 50 MB; 'core:typst' is 'full'), 'calibre' (Calibre, 190 to 360 MB: ebooks as output and input; offers Homebrew or winget "
                             "in a terminal, else downloads the release checked against GitHub's SHA-256: a disk image into "
                             "~/Applications on macOS, an archive into pdfmd's data folder on Linux), 'emoji' (the colour emoji font, about 11 MB, into pdfmd's own "
                             "fonts folder: every engine that can draw colour emoji uses it, and the built-in "
                             "renderer) or 'fonts' (alone: lists the fonts pdfmd can fetch; "
                             "fonts:NAME[,NAME...] installs some, e.g. fonts:arabic,cjk-sc or fonts:core, "
                             "into pdfmd's own folder with no admin rights) or 'ocr' (alone: lists the Tesseract "
                             "languages pdfmd can fetch; ocr:rus,kaz installs some into its own folder) or 'kit' (alone: lists the kits pdfmd "
                             "installed; kit:owner/repo installs the kits of a GitHub repository, kit:owner/repo@v1#name one of them at a "
                             "tag, kit:https://host/x.git any git URL, kit:./folder a folder, kit:apa7 a kit by name from the "
                             "repositories of `kit-sources`; a kit is a folder with a .kit file, at the repository's root or in its "
                             "folders; --uninstall kit:NAME removes it). "
                             "pandoc/math equal `pip install \"pdfmd-cli[KIND]\"`. "
                             "A Pandoc or Typst already on PATH always wins over the installed ones")
    parser.add_argument("--translit", metavar="PACKS",
                        help="romanization packs for finding a document by a name typed in Latin letters "
                             "(`mingyun` finds 命運.md): greek, armenian, georgian, hebrew, arabic, hangul, kana "
                             "(built in), han (pinyin, needs pypinyin or anyascii), other (every other script, "
                             "needs anyascii); `all`, `none` (Cyrillic too), `list` shows what is available. "
                             "Cyrillic (Russian, Kazakh, Ukrainian, Belarusian) is always on. Also PDFMD_TRANSLIT")
    parser.add_argument("--fallback", metavar="MODE",
                        help="what to do about characters the main font cannot draw: char (just those "
                             "characters in another installed font; the default), word (the whole word), "
                             "document (the one installed font that draws most of the document is the main "
                             "font), off (nothing), box (black boxes) or error (stop). `pdfmd-options: "
                             "{fallback: MODE}` or the config file's `options:` set it per document or "
                             "for all")
    parser.add_argument("--missing", metavar="MODE",
                        help="what to do about characters no installed font draws: warn (default), box "
                             "(a black box each) or error")
    parser.add_argument("--check-fonts", action="store_true",
                        help="say which fonts a document would be set in, which characters need a fallback "
                             "font and which no installed font draws (and what to install), without building")
    parser.add_argument("--show-config", action="store_true",
                        help="print where pdfmd's global config file is, and what it sets")
    parser.add_argument("--text-to-markdown", nargs="?", const="auto", choices=("auto", "force", "paragraphs"), metavar="MODE",
                        help="read .txt input as Markdown: headings, lists, tables and paragraphs guessed from how the text "
                             "is typed, the words never changing (needs batchocr 1.2.5: pdfmd --install batchocr). MODE: "
                             "auto (default; a garbled text gets paragraphs only), force, or paragraphs (no structure). Writes "
                             "notes.md beside the text; with -o x.md that is all it does. Off unless asked")
    parser.add_argument("--setup", "--config", nargs="?", const="", metavar="SCREEN",
                        help="change pdfmd's global defaults from a menu (a numbered list; `--setup fancy` is the optional "
                             "full-screen one, installed by `pdfmd --install tui`) instead of editing the config file. "
                             "`--setup FOLDER` (or `.`) does it for that folder and every folder under it, in FOLDER/.pdfmd/. "
                             "--config is the same")
    parser.add_argument("--doc", nargs="*", default=None, metavar="NAME",
                        help="the documents of this version, offline: --doc lists them (readme, recipes, agents, changelog); --doc NAME "
                             "shows one (the Markdown when the output is not a terminal or with --print, else a web page it opens); "
                             "--doc NAME SECTION shows a part (a number counts the ## headings, else a word of the title); "
                             "--doc search WORD finds the lines that have it; --path says where the file is")
    parser.add_argument("--print", dest="doc_print", action="store_true",
                        help="with --doc: print the Markdown, whatever the output is")
    parser.add_argument("--path", dest="doc_path", action="store_true",
                        help="with --doc: print the path of the document's file and nothing else")
    parser.add_argument("--disabled", action="store_true",
                        help="use features the config switches off (`disabled:` in config.yaml, `pdfmd --setup` and d) "
                             "for this run, and show them in --help")
    parser.add_argument("--init-config", action="store_true",
                        help="write a commented config file (~/.config/pdfmd/config.yaml) if there is none")
    parser.add_argument("--uninstall", metavar="fonts:NAME|ocr:LANG|kit:NAME", type=core.uninstall_kind,
                        help="remove fonts, OCR languages or kits installed by --install, e.g. --uninstall fonts:arabic,cjk, "
                             "ocr:rus or kit:apa7")
    parser.add_argument("--init-reference", nargs="?", const="docx", metavar="FORMAT",
                        help="write reference.docx (or odt, pptx) into this folder: Pandoc's own reference document "
                             "with pdfmd's look, to restyle in Word; pdfmd then uses it for every .docx/.odt/.pptx "
                             "it writes beside it (or below it, or in a metadata/ folder)")
    parser.add_argument("--completion", choices=("bash", "zsh", "fish"), metavar="SHELL",
                        help="print a tab-completion script for bash, zsh or fish (generated from this command "
                             "line, so it is never out of date), e.g. pdfmd --completion zsh > ~/.zfunc/_pdfmd")
    parser.add_argument("--user-path", nargs="+", metavar=("VERB", "FOLDER"),
                        help="Windows: put folders on your USER PATH (no administrator rights; it asks first, --yes skips the "
                             "question, --dry-run only shows). `--user-path add FOLDER...` adds the folders you name, or, with no "
                             "folder, those of the tools pdfmd found off PATH (--doctor names them); `--user-path remove` takes off "
                             "exactly what pdfmd added; `--user-path show` lists the entries. Nothing else in pdfmd touches PATH. "
                             "The global --setup has the same as a row")
    parser.add_argument("--add-to-path", nargs="*", metavar="FOLDER", default=None,
                        help="the same as --user-path add [FOLDER...]")
    parser.add_argument("--remove-from-path", action="store_true", help="the same as --user-path remove")
    parser.add_argument("--show-user-path", action="store_true", help="the same as --user-path show")
    parser.add_argument("--yes", action="store_true",
                        help="with --user-path (or --add-to-path, --remove-from-path): do not ask first")
    parser.add_argument("--init", nargs="?", const="", metavar="TEMPLATE",
                        help="start a new document from a template: `pdfmd --init article paper` makes the folder paper/ "
                             "(a template that is one file makes paper.md) with the title, author and date filled in "
                             "(-V title=... -V author=...); nothing that exists is overwritten. Alone it lists the "
                             "templates: article, report, notes, slides, book, and yours (a folder or .md file in the "
                             "config folder's templates/, or any path)")
    parser.add_argument("--check", action="store_true",
                        help="read FILE (a scaffold and its parts too) and report what would go wrong or print wrongly, "
                             "without building: a missing image or csv file, a link or #anchor to nowhere, a duplicate "
                             "{#id}, a @fig:x or \\ref{x} nothing defines, a citation the bibliography lacks, a "
                             "footnote with no text, a skipped heading level, a code fence or <!-- never closed, front "
                             "matter that does not parse. Exit 1 on an error (also on a warning with --strict)")
    parser.add_argument("--check-ignore", action="append", metavar="CODE[,CODE]",
                        help="with --check: leave out these checks (also `pdfmd-options: {check-ignore: [heading-jump]}`; "
                             "one line: `<!-- pdfmd-check: ignore CODE -->` on it or the line above)")
    parser.add_argument("--check-docx", action="store_true",
                        help="say what a Word build of FILE would make native, draw as a picture or leave out, without "
                             "drawing or writing anything (the macro or environment behind each picture is named)")
    parser.add_argument("--crop", action="store_true",
                        help="cut each page to what it draws (the page stays vector; only its boxes change). FILE is a PDF "
                             "(NAME-crop.pdf beside it) or a Markdown source (built first: NAME.pdf). With --to png or svg "
                             "the cropped page is drawn as a picture. -o FILE (one source) or -o FOLDER. Needs Ghostscript "
                             "and pypdf. Options: --crop-pad, --crop-ignore-bottom, --crop-page, --image-dpi")
    parser.add_argument("--crop-pad", type=float, default=None, metavar="PT",
                        help="with --crop: points of room left around the ink (default 2)")
    parser.add_argument("--crop-ignore-bottom", type=float, default=None, metavar="PT",
                        help="with --crop: do not look at the bottom PT points of each page (a page number); default 0")
    parser.add_argument("--image-dpi", type=float, default=None, metavar="DPI",
                        help="with --to png, jpg or tiff: pixels per inch of the picture (default 300)")
    parser.add_argument("--image-quality", type=int, default=None, metavar="1-100",
                        help="with --to jpg: the JPEG quality (default 90)")
    parser.add_argument("--page-folder", action=argparse.BooleanOptionalAction, default=None,
                        help="with a picture target of several pages: put them in a folder NAME/ (001.png ...; the default) "
                             "or, with --no-page-folder, beside the document as NAME-001.png ... (also `pdfmd-options: "
                             "{page-folder: false}`)")
    parser.add_argument("--crop-page", type=int, default=None, metavar="N",
                        help="with --crop: keep page N alone, cropped (default: every page, each to its own ink)")
    parser.add_argument("--editor", metavar="CMD", default=None,
                        help="with --edit: an editor of your own instead of the built-in one (\"code --wait\", \"vim\"); "
                             "the file is watched and rebuilt on every save. On a PDF that carries its source the "
                             "restored source is what it opens. Also `options: {editor: CMD}` in --setup")
    parser.add_argument("--edit", action="store_true",
                        help="edit FILE (default: the Markdown file of this folder) in a small full-screen editor "
                             "with the build one key away (Ctrl-B; F1 lists the keys). Alpha. Needs "
                             "prompt_toolkit: pdfmd --install tui. Other options given beside it are used for the build")
    parser.add_argument("--raw", action="store_true",
                        help="carry the non-Markdown pieces of a document into every output: raw HTML (<img>, "
                             "<table>, <b>...) and raw LaTeX are read by Pandoc into the target's own elements, raw "
                             "Typst is drawn as a vector picture, and nothing is silently dropped for being written in "
                             "another syntax. Per family and syntax: pdfmd-options.raw (or --raw-for)")
    parser.add_argument("--no-raw", action="store_true",
                        help="switch the raw option off for this run, whatever a document's pdfmd-options.raw says")
    parser.add_argument("--raw-for", action="append", metavar="FAMILY=SYNTAXES",
                        help="with --raw or alone: the raw syntaxes one output family takes, e.g. html=tex,typst "
                             "(families: tex, typst, html, office, md; syntaxes: tex, html, typst, office; a syntax "
                             "left out is dropped, the family's own included). Repeat for more families")
    parser.add_argument("--pagebreak", nargs="*", default=None, metavar="KIND",
                        help="carry page breaks into every output format: each spelling of the named families becomes "
                             "the format's own (LaTeX \\newpage, Typst #pagebreak, a CSS break, a Word break ...). "
                             "Families: comment (<!-- pagebreak -->, <!-- pdfmd: pagebreak -->), tex (\\newpage, "
                             "\\clearpage ...), html (a CSS-break or class=pagebreak div), div (::: pagebreak), typst "
                             "(#pagebreak()), word (a raw Word break); bare: all. On, every family, in the pdfmd and obsidian flavours (off with flavour: pandoc); also "
                             "pdfmd-options.pagebreak (true, false or a list) and pdfmd --setup")
    parser.add_argument("--no-pagebreak", action="store_true",
                        help="no page-break carrying for this run, whatever pdfmd-options.pagebreak says")
    parser.add_argument("--linebreak", nargs="*", default=None, metavar="KIND",
                        help="carry line breaks into every output format, everywhere (without it: inside table cells only): each "
                             "spelling of the named families becomes the format's own line break (LaTeX \\\\, Typst \\, a Word "
                             "break, HTML <br />). Families: html (<br>, <br/>), tex (\\newline, \\linebreak), typst "
                             "(#linebreak()), word (a raw Word break), context (\\crlf); bare: all. Also pdfmd-options.linebreak "
                             "(auto, true, false or a list) and pdfmd --setup")
    parser.add_argument("--no-linebreak", action="store_true",
                        help="no line-break carrying for this run, whatever pdfmd-options.linebreak says")
    parser.add_argument("--markup", nargs="*", default=None, metavar="KIND",
                        help="carry spellings other Markdown dialects share into every output: callouts (> [!NOTE], "
                             "> [!warning] Title, ::: note) become a box (LaTeX, Typst), a styled div (HTML, EPUB) or a "
                             "quote with a bold title (the rest); toc ([TOC], [[_TOC_]], <!-- toc -->) is the table "
                             "of contents where it stands; center (<center>, <div align=center>, ::: center) centres the "
                             "text; highlight (==text==) marks it; underline (<u>text</u>) underlines it; keep (::: keep) holds blocks on one page; landscape (::: landscape) puts them on landscape pages; appendix (\\appendix, <!-- appendix -->, "
                             "{.appendix}) letters the sections after it; space (\\vspace{1cm}, \\bigskip, <br>) is vertical space; bare: all kinds. On, except space, in the pdfmd and obsidian flavours (off with flavour: pandoc); also "
                             "pdfmd-options.markup (true, false or a list) and pdfmd --setup")
    parser.add_argument("--show-comments", action="store_true", default=None,
                        help="show the <!-- comments --> of the text in the output instead of dropping them: a box labelled "
                             "Comment (LaTeX, Typst, HTML, EPUB), a real Word comment (docx); the Markdown family keeps them as "
                             "they are. pdfmd's own markers (<!-- pdfmd: ... -->, <!-- pagebreak -->) stay invisible. Off by "
                             "default; also pdfmd-options.show-comments and pdfmd --setup")
    parser.add_argument("--no-show-comments", dest="show_comments", action="store_false",
                        help="do not show comments in this run, whatever pdfmd-options.show-comments says")
    parser.add_argument("--flavour", "--flavor", dest="flavour", metavar="NAME", type=str.casefold,
                        help="the flavour of Markdown the files are written in: obsidian (%%%%comments%%%% hidden, more of its syntax in "
                             "each release), pdfmd (%%%%comments%%%% hidden; the rest of pdfmd's own syntax follows), pandoc (strict "
                             "Pandoc: nothing added), gfm, commonmark, or auto (the default: obsidian inside a vault, a folder with "
                             ".obsidian/ above the document, pdfmd elsewhere). A Pandoc reader such as gfm+smart is taken as the reader "
                             "with the flavour on auto, like --from. Also pdfmd-options.flavour (or reader) and pdfmd --setup")
    parser.add_argument("--unclosed-comment", dest="unclosed_comment", metavar="WORD", type=str.casefold, choices=core.UNCLOSED_WORDS,
                        help="what a %%%% with no closing %%%% does: hide (the default in an Obsidian vault, as Obsidian does: the rest "
                             "of the note is the comment) or keep (the default elsewhere: it stays text); both warn; also pdfmd-options.unclosed-comment "
                             "and pdfmd --setup")
    parser.add_argument("--no-markup", action="store_true",
                        help="no universal markup for this run, whatever pdfmd-options.markup says")
    parser.add_argument("--gfm-scripts", choices=("unicode", "html", "drop", "ascii"), default=None, metavar="MODE",
                        help="with --to gfm (flat Markdown) or --to txt: how subscripts and superscripts are written -- unicode "
                             "(H2O -> H\u2082O; `_(..)`/`^(..)` for what has no Unicode form; the default), html "
                             "(<sub>/<sup>; unicode in a text file), drop (the plain text) or ascii (`_2`, `^(2+)`). Also "
                             "`pdfmd-options: {gfm: {scripts: ...}}` (`txt:` for text)")
    parser.add_argument("--ascii-missing", choices=("question", "escape", "drop", "fail"), default=None, metavar="MODE",
                        help="with --to ascii: what a character with no ASCII form becomes -- question (`?`, the "
                             "default), escape (`\\u65e5`), drop (nothing) or fail (no file is written). Also "
                             "`pdfmd-options: {ascii: {missing: ...}}`")
    parser.add_argument("--ascii-stdio", nargs="+", metavar="ARG", help=argparse.SUPPRESS)
    parser.add_argument("--gfm-math", choices=("dollars", "fenced"), default=None, metavar="MODE",
                        help="with --to gfm: math as `$..$` / `$$..$$` (default; GitHub, VS Code and Obsidian read it) "
                             "or as ```math fences (GitHub's older form). Also `pdfmd-options: {gfm: {math: ...}}`")
    parser.add_argument("--init-vscode", action="store_true",
                        help="write .vscode/tasks.json here with pdfmd tasks (build, build and open, watch, extract "
                             "tables) for VS Code; never overwrites one")
    parser.add_argument("--extract-tables", action="store_true",
                        help="rewrite FILE so that each of its tables (pipe, simple, multiline or grid) is a `.csv` block "
                             "reading tables/<name>.csv (--tables-inline: the data inside the document instead), the "
                             "caption and alignment kept as block attributes, after checking that Pandoc reads the same "
                             "tables back. Names come from the captions, else table1, table2... (--table-names a,b,c "
                             "gives them; the count must match). The old file is backed up first; --dry-run only shows")
    parser.add_argument("--extract-inline-csv", action="store_true",
                        help="with --extract-tables (implied): also move the data of `.csv` blocks that hold it inside "
                             "the document into tables/<name>.csv files. Off by default. A table, or a block, with "
                             "`<!-- pdfmd: ignore -->` on the line above it (or under its caption) is left as it is")
    parser.add_argument("--expand-tables", action="store_true",
                        help="the reverse of --extract-tables: every `.csv` block of FILE becomes an ordinary pipe table "
                             "(all its rows), its caption= the line under it. The CSV files are left where they are")
    parser.add_argument("--csv", action=argparse.BooleanOptionalAction, default=None,
                        help="build a table from a `::: {.csv}` div (on by default); --no-csv leaves the div as written, "
                             "a plain div with its text. Also `pdfmd-options: {csv: off}` (or `csv: {enabled: false}`), "
                             "or --setup")
    parser.add_argument("--csv-note", type=csv_note_argument, default=None, metavar="MODE",
                        help="the note under a `::: {.csv}` table that was cut: short (default; the fact only: \"showing the first 7 "
                             "and the last 3 of 11 rows\"), off (none; the \u2026 row still marks the cut) or full (adds how to show "
                             "more). The advice is in the warning on stderr whatever this says. A div's note= wins. "
                             "Also `pdfmd-options: {csv: {note: off}}`, or --setup")
    parser.add_argument("--csv-rows", type=csv_count_argument, default=None, metavar="N|all",
                        help="how many data rows a `::: {.csv}` table shows when its div does not say (default 10). "
                             "Also `pdfmd-options: {csv: {rows: N}}`, or --setup")
    parser.add_argument("--csv-cols", type=csv_count_argument, default=None, metavar="N|all",
                        help="how many columns a `::: {.csv}` table shows when its div does not say (default 7). "
                             "Also `pdfmd-options: {csv: {cols: N}}`, or --setup")
    parser.add_argument("--table-keep", type=table_keep_argument, default=None, metavar="N",
                        help="keep a Markdown table of up to N body rows on one page, for a Lua filter that reads "
                             "`tablekeep` (nulabreport.lua; 0 lets every table break). Also `pdfmd-options: "
                             "{table-keep: N}`, or --setup")
    parser.add_argument("--view", action="store_true",
                        help="read the document in the terminal: styled text (bold, italic, code, box-drawn tables, lists, "
                             "math as text) wrapped to the window, through a pager when it is longer. = `--to ansi -o -` "
                             "+ a pager. Takes files, `-` or a pipe, else the Markdown files here, else what you type "
                             "(Ctrl-D ends it)")
    parser.add_argument("--rewrite", action=argparse.BooleanOptionalAction, default=None,
                        help="replace an older output of the same name (the default); --no-rewrite writes `report (1).pdf` "
                             "(the first free number) and leaves the old file alone. Also `pdfmd-options: {rewrite: false}`, "
                             "`{rewrite-name: \"{stem}-{n}{ext}\"}` for the name, or --setup. A watch (-w) always rewrites")
    parser.add_argument("--pager", action=argparse.BooleanOptionalAction, default=None,
                        help="with --view: use $PDFMD_PAGER / $PAGER / the `pager_command` setting / `less -FRX` when stdout is a terminal "
                             "(the default); --no-pager prints it all. Also `pdfmd-options: {pager: false}` (and "
                             "`{pager_command: \"bat --paging=always\"}` for the command), or --setup")
    parser.add_argument("--calc", action=argparse.BooleanOptionalAction, default=None,
                        help="evaluate inline code followed by `{=}` (`2026 - 2006`{=} is 20) and the lines of a `::: calc` div "
                             "(`C = n / V = {ans:4sf}`); --no-calc leaves them as written. On by default; also "
                             "`pdfmd-options: {calc: {enabled: false}}` (or `calc: off`), or --setup")
    parser.add_argument("--calc-digits", type=calc_digits_argument, default=None, metavar="4sf|2dp",
                        help="how many figures a calculated value shows: 4sf (four significant figures), 2dp (two decimal "
                             "places). Unset: as R prints, up to 7 figures. `{ans:2dp}` in a span wins. Also "
                             "`pdfmd-options: {calc: {digits: 4sf}}`, or --setup")
    parser.add_argument("--calc-round", type=calc_round_argument, default=None, metavar="even|away",
                        help="how round() in a calculation settles an exact half: even (the default; 2.5 is 2, as R and Python "
                             "do) or away from zero (2.5 is 3). Also `pdfmd-options: {calc: {round: away}}`, or --setup")
    parser.add_argument("--calc-subs", action=argparse.BooleanOptionalAction, default=None,
                        help="a calculation shows its expression with the names replaced by their values in front of the result "
                             "(`ppm = C * V = 0.002 * 34.41 = 28.12`); the computation keeps the full values. {subs} on a line "
                             "forces it, {nosubs} stops it. Also `pdfmd-options: {calc: {subs: true}}`, or --setup")
    parser.add_argument("--calc-typeset", nargs="?", const="inline", choices=("inline", "display"), default=None, metavar="inline|display",
                        help="print each calculation as typeset maths instead of plain text: names with subscripts (C_EDTA becomes C with an "
                             "EDTA subscript), a centred dot for *, Greek letters. `--calc-typeset` (inline) keeps the label and the unit as "
                             "text in the line; `--calc-typeset display` makes each `::: calc` line a centred display formula with the label "
                             "and the unit inside it (it does not wrap). Works in the writers that have maths (LaTeX, Typst, HTML, Word...); "
                             "the others keep the text. Off by default; --no-calc-typeset turns it off. Also "
                             "`pdfmd-options: {calc: {typeset: true|display}}`, or --setup")
    parser.add_argument("--no-calc-typeset", dest="calc_typeset", action="store_const", const="off",
                        help="print calculations as plain text (the default); turns --calc-typeset, or the document's typeset setting, off")
    parser.add_argument("--calc-typeset-upright", metavar="PIECES", default=None,
                        help="pieces of a name a typeset calculation sets upright (\\mathrm), comma separated: V for V_el, e for c_e. The "
                             "default is a one-letter piece italic and a longer one upright. A piece is the letters of a name's base or "
                             "one word after an underscore. Also `pdfmd-options: {calc: {typeset-upright: [V]}}`, or --setup")
    parser.add_argument("--calc-typeset-italic", metavar="PIECES", default=None,
                        help="pieces of a name a typeset calculation sets italic, comma separated: el for V_el, DNA for k_DNA (a word of "
                             "several letters is one italic word, \\mathit). Also `pdfmd-options: {calc: {typeset-italic: [el]}}`, or --setup")
    parser.add_argument("--calc-noindent", nargs="?", const="all", choices=("lines", "all"), default=None, metavar="lines|all",
                        help="the first-line indent in a `::: calc` div: `lines` (the default) takes it off the paragraphs that hold a "
                             "calculation line and leaves the document's on the prose between them; `--calc-noindent` (all) takes it off "
                             "every paragraph of the div; --no-calc-noindent gives the whole div the document's own. An `indent=` on the "
                             "div wins, and so does a nested `::: indent` / `::: noindent` div. Also "
                             "`pdfmd-options: {calc: {noindent: lines|true|false}}`, or --setup")
    parser.add_argument("--no-calc-noindent", dest="calc_noindent", action="store_const", const="false",
                        help="a `::: calc` div keeps the document's first-line indent, calculation lines included")
    parser.add_argument("--calc-space", metavar="LENGTH", default=None,
                        help="the room above and below a `::: calc` div: a length (0.75em, 6pt, 2mm; pt mm cm in em) or off. "
                             "Default 0.75em. Also `pdfmd-options: {calc: {space: 0.75em}}`, or --setup")
    parser.add_argument("--calc-align", choices=core.CALC_ALIGNS, default=None,
                        help="the lines of a `::: calc` div flush left (the default) or centred. Also "
                             "`pdfmd-options: {calc: {align: center}}`, or --setup")
    parser.add_argument("--calc-constants", metavar="FILE", default=None,
                        help="a CSV file of named values the calculator knows before the document starts (columns "
                             "name,value[,digits[,note]]), looked for beside the document and its metadata files. Also "
                             "`pdfmd-options: {calc: {constants: tables/constants.csv}}`, or --setup")
    parser.add_argument("--calc-export", metavar="FILE", default=None,
                        help="after a build, write the calculator's names to this CSV (name,value,digits; the value of the last "
                             "definition of each name, at full precision), beside the document unless the path is absolute: "
                             "the mirror of --calc-constants, and a file it can read back. Also "
                             "`pdfmd-options: {calc: {export: results.csv}}`, or --setup")
    parser.add_argument("--color", choices=("auto", "always", "never"), default=None,
                        help="--to ansi / --view: escape codes always, never, or auto (a file and --view: yes; `-o -` "
                             "into a pipe: no; NO_COLOR turns auto off)")
    parser.add_argument("--width", type=core.ansi_width_argument, default=None, metavar="N",
                        help="--to ansi / --view: draw for N columns (default: the terminal's, else 120)")
    parser.add_argument("--table-numbers", metavar="1,3-4",
                        help="with --extract-tables: only these tables, by their position in the document "
                             "(1 is the first; ranges allowed); the others stay as they are, and --table-names "
                             "names just the chosen ones. In a document in parts it applies to each part")
    parser.add_argument("--table-names", metavar="A,B,C",
                        help="with --extract-tables: the file names for the tables, in the order they appear")
    parser.add_argument("--tables-dir", default="tables", metavar="DIR",
                        help="with --extract-tables: the folder for the CSV files, beside the document (default tables)")
    parser.add_argument("--tables-inline", action="store_true",
                        help="with --extract-tables: write each table's data inside its `.csv` block, no files")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --extract-tables, --expand-tables, --history-to-file, --history-to-notes or "
                             "--history-restore: show what would change and write nothing")
    parser.add_argument("--line-numbers", nargs="?", const="1", metavar="STEP",
                        help="number the lines of every code block (LaTeX builds); STEP numbers every STEP-th line. "
                             "Per block: {.numberLines startFrom=10 step=5}, {.noNumberLines}. Off unless asked; "
                             "`pdfmd-options: {line-numbers: true}` or --setup make it the default")
    parser.add_argument("--no-code-wrap", action="store_true",
                        help="let long code lines run on (LaTeX builds wrap them by default); per block: {wrap=false}")
    parser.add_argument("--apply-defaults", action=argparse.BooleanOptionalAction, default=None,
                        help="for a .typ or .html file built directly (which gets none of pdfmd's defaults): give it "
                             "the title, author, date, language, font, font size, paper and margin of its metadata "
                             "files, ahead of its own settings, so those win. `pdfmd-options: {apply-defaults: true}` "
                             "in the config, or --setup, makes it the default; --no-apply-defaults turns it off")
    parser.add_argument("--hybrid", action=argparse.BooleanOptionalAction, default=None,
                        help="make the PDF a LibreOffice 'hybrid PDF': it carries an OpenDocument copy of the document as "
                             "Original.odt (.odp, .ods), and LibreOffice opens the PDF as that editable document. An "
                             "Office file is converted by LibreOffice; anything else is built to .odt by pdfmd. "
                             "`pdfmd-options: {hybrid: true}` or --setup makes it the default")
    parser.add_argument("--doctor", action="store_true",
                        help="one report on everything pdfmd uses (Pandoc and engines, fonts, emoji, PDF "
                             "reading, OCR, config, cache) and the command that fixes each missing piece")
    parser.add_argument("--deep", action="store_true",
                        help="with --doctor: also build a small page with each installed engine (a few seconds "
                             "each), to find one that is installed but cannot make a PDF")
    parser.add_argument("--check-dependencies", action="store_true",
                        help="show Pandoc and supported PDF-engine availability, then exit")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="parallel workers in batch mode")
    parser.add_argument("-V", "--var", action="append", default=[], dest="variable", metavar="KEY=VALUE")
    parser.add_argument("-y", "--metadata-file", nargs="*", default=None, metavar="FILE",
                        help="metadata YAML file(s), 'all', or bare -y to disable discovery")
    parser.add_argument("--check-source", "--sources", dest="check_source", action="store_true",
                        help="say which PDFs carry their source (a PDF or a folder of them, default the working folder; "
                             "--recursive goes below it): reads only the attachment list, builds nothing. Exit 1 when one "
                             "does not. `pdfmd FILE.pdf --restore --list` shows what one carries")
    parser.add_argument("--preset", metavar="NAME", default=None,
                        help="take the global metadata from another file than metadata.yaml: NAME (or NAME.yaml) in the "
                             "presets/ folder beside the config file, or a path; `default` is metadata.yaml, `none` no "
                             "global metadata at all. Also `pdfmd-options: {preset: lab}`. With --setup it is the file the "
                             "'Every document' rows edit (made if it is not there). The presets there are: --presets")
    parser.add_argument("--global-metadata", action=argparse.BooleanOptionalAction, default=None,
                        help="--no-global-metadata: build without the global metadata of pdfmd --setup (and its presets), "
                             "--global-metadata: with it, whatever a document's `pdfmd-options: {global-metadata: false}` "
                             "or the config says. Also `options: {global-metadata: false}` in --setup")
    parser.add_argument("--presets", action="store_true",
                        help="list the presets (global metadata files, see --preset) and the one a build here would use")
    parser.add_argument("--kit", action="append", nargs="?", const="", default=None, metavar="KIT",
                        help="use this kit for the run: nulabreport, nulabreport:qca, nulabreport[qca], or a path; repeat it to stack "
                             "several. It replaces every `kit:` setting (the --kit-stack setting keeps some); `--kit none`, or "
                             "a bare --kit before another option, uses no kit. A kit is a folder with a `.kit` file. --kit builds with a kit; "
                             "--kits NAME describes it (what it sets, its modes, its files)")
    parser.add_argument("--kit-stack", default=None, metavar="LAYERS",
                        help="which kit settings --kit stacks on instead of replacing: all, or a list of global, preset, folder, "
                             "document (e.g. folder,document); off (default) replaces them all. Also `pdfmd-options: {kit-stack: ...}`")
    parser.add_argument("--kits", nargs="*", default=None, metavar="NAME",
                        help="list the kits there are (a kit is a folder with a `.kit` file: a document pipeline such as a "
                             "house style), or show the named ones (a name or a path) in full and check them; where kits are "
                             "looked for: a kits/ folder above the document, `kits:` in the config, the TeX tree")
    parser.add_argument("--metadata-precedence", choices=core.METADATA_PRECEDENCES, default=None,
                        help="which of two metadata files wins a key both set, pdfmd-options too: later (default, as "
                             "Pandoc takes them) or first. The document's own front matter beats both, the global "
                             "metadata.yaml (pdfmd --setup) is below both. Also `options: {metadata-precedence: first}` "
                             "in the config (pdfmd --setup)")
    parser.add_argument("-i", "--ignore", "--exclude", action="append", default=[], metavar="FILE",
                        help="exclude a Markdown file from report/book input (extension optional)")
    parser.add_argument("--exclude-unnumbered", action="store_true",
                        help="exclude Markdown files without a chapter field in report/book mode")
    parser.add_argument("--section", "--only", action="append", default=[], metavar="NAME",
                        dest="section",
                        help="build just these sections: in a parts-mode document (pdfmd-options: "
                             "{parts: auto}) parts named by file, by file without its numeric prefix, by "
                             "folder, or by number; in any Markdown document headings, named by their text "
                             "(case, spaces and spelling are forgiving) or {#id}: `name`, `##name` for a "
                             "level-2 heading, `parent/name`; repeat the flag or join with + or , (a+b). "
                             "`pdfmd report#intro` is shorthand for `pdfmd report --section intro`, and "
                             "so is naming a part's own path. (No short flag: -s is Pandoc's --standalone.)")
    parser.add_argument("--cache", dest="cache", action="store_true", default=None,
                        help="keep LaTeX's .aux files between builds in pdfmd's cache folder, so an "
                             "unchanged document settles in one engine pass and a part of a split "
                             "document built alone can reference the last full build's numbers "
                             "(pdfmd-options: {cache: {aux: true}} does this by default)")
    parser.add_argument("--cache-location", metavar="WHERE", choices=core.CACHE_LOCATIONS,
                        help="where the cache lives: global (~/.cache/pdfmd; default; a moved document still "
                             "finds its folder by what it recorded) or document (a .cache/pdfmd folder beside "
                             "the document, so it travels with it). Also `pdfmd-options: {cache: {location: "
                             "document}}` or the config file")
    parser.add_argument("--cache-plots", action="store_true",
                        help="also cache the pictures of a package that takes part in the picture cache (nulabreport >= 1.26.0 does; LuaLaTeX): each "
                             "plot is stored as a PDF after the build that first typesets it and reused by "
                             "the next, until the package, the preamble, the engine or the plot's data "
                             "file changes (pdfmd-options: {cache: {plots: true}} does this by default)")
    parser.add_argument("--seed-labels", metavar="MODE", choices=pdfmd_labels_modes(),
                        help="where a part (or a section) built alone takes the labels of the rest of the document "
                             "from, so a reference to them prints its number instead of ??: auto (default: the last "
                             "full build's .aux when the cache has one, then a scan of the whole document's LaTeX), "
                             "aux, scan, draft (a LaTeX pass over the whole document without output) or off. "
                             "Also `pdfmd-options: {seed-labels: scan}`")
    parser.add_argument("--seed-calc", metavar="MODE", choices=core.SEED_CALC_MODES,
                        help="where a part (or a section) built alone takes the calculator's names from: the whole "
                             "document is evaluated with the calculator only, not typeset, so a name has the value the "
                             "full build gives it at that place, defined above or below (auto, the default, or scan), "
                             "or off (a `name`{=} defined in a part left out is then undefined). "
                             "Also `pdfmd-options: {seed-calc: off}`")
    parser.add_argument("--clear-cache", nargs="?", const=True, default=False, metavar="WHAT",
                        help="delete pdfmd's cache folder for the given document (or all of it, with no "
                             "document), then exit; always safe. WHAT clears one part of the whole cache: builds "
                             "(the build records), documents (every document's own cache), stale (the document "
                             "caches and build records whose document is gone) or all; each with its size")
    parser.add_argument("--cache-info", action="store_true",
                        help="show pdfmd's cache folder and the size of each part (the documents' caches, the build "
                             "records, the shared folders), and how much of it is stale, then exit")
    parser.add_argument("--no-cache", dest="cache", action="store_false",
                        help="turn the cache off for this build, whatever pdfmd-options says")
    parser.add_argument("--split", type=Path, metavar="DIR",
                        help="cut a single-file document at its level-1 headings ('# ' or a line underlined with ===) into a scaffold plus "
                             "parts/ in a new folder DIR (the source is untouched; other files it "
                             "uses are symlinked in), and check that the parts read back as the "
                             "identical document. See 'A long document in parts' in the docs")
    parser.add_argument("--split-depth", type=int, default=1, metavar="N",
                        help="with --split: also cut at level-2 (N=2; '## ' or a line underlined with ---), level-3 (N=3) headings, each "
                             "cut section becoming a folder of parts, so that a subsection can be "
                             "built alone. Default 1: top-level sections only")
    parser.add_argument("--list-parts", action="store_true",
                        help="print what `--section`/`name#section` can name and exit: a parts-mode "
                             "document's parts in build order, or any other Markdown document's "
                             "headings and {#ids} with their lines")
    parser.add_argument("--no-auto", nargs="*", default=None, metavar="KIND",
                        help="disable pdfmd's own automatic per-document behavior. Bare --no-auto "
                             "disables all of it; or name one or more of: reader (the gfm switch "
                             "for front-matter-less documents), title (bare '# Title' promotion), "
                             "margin (geometry:margin=1in), mainfont (the STIX Two Text/DejaVu Serif "
                             "fallback), monofont (JetBrains Mono for code), font (mainfont and "
                             "monofont together), tablewidth (proportional pipe-table column widths), "
                             "standalone (the --to latex/beamer/context --standalone default), "
                             "metadata/yaml (auto-discovered --metadata-file), preamble/tex "
                             "(auto-included LaTeX preambles), lua (auto-included Lua filters), "
                             "unicode (fonts for text in other scripts, and the main font chosen for the "
                             "document's own script), "
                             "priority (choosing one of several Markdown files for a bare `pdfmd` by priority, name and age; off, "
                             "it stops with the list), "
                             "files (metadata+preamble+lua together), lookup (finding a document by "
                             "its title, alias, the start of its name or a looser spelling), texdirect (the direct-.tex-"
                             "compile path -- see 'Input formats' in the module docstring; disabling "
                             "it routes .tex input back through Pandoc the pre-v3.1.0 way), "
                             "officedirect (the direct office-document-to-PDF path, same section -- "
                             "disabling it on a .docx/.odt is an error in this version, not a route "
                             "back through Pandoc), typstdirect / htmldirect (a .typ / .html file is built by Typst / WeasyPrint "
                             "or a browser directly; off, it goes through Pandoc), pdfimages (PDF images in HTML builds), diagrams (```mermaid / ```d2 / ```dot blocks drawn by their tool), smiles (```smiles / ::: smiles blocks drawn as chemical structures), mathjax (MathJax typesets the math of WeasyPrint PDFs; off, KaTeX or text does), texpackages (mhchem or siunitx loaded for a document that uses \\ce or \\SI and does not load them), draftpictures (the draft pass of seed-labels: draft does not draw TikZ, chemfig or images), remotecsl (a csl: style named by URL fetched once and kept, with Pandoc's own csl/ folder and its default style as fallbacks), svg / remoteimages (SVG "
                             "converted, and remote images fetched, for LaTeX builds), crossref (the auto-detected --filter pandoc-crossref "
                             "for @fig:/@eq:/@tbl:/@sec:/@lst: syntax), citationengine (a document's own "
                             "pdfmd-options.citation-engine setting -- see 'Output formats' in the module "
                             "docstring; disabling this KIND always means plain --citeproc), csvtable "
                             "(the .csv-div table inclusion -- see 'CSV/TSV table inclusion' in the module "
                             "docstring), papersize (a document's own pagesize: front-matter key, "
                             "auto-translated to Pandoc's real papersize: variable since pagesize: alone "
                             "silently does nothing -- disabling this KIND leaves that typo uncorrected, "
                             "same as before this existed), kit / kpsewhich (a package's "
                             "<package>-pdfmd.yaml is read from the next place that has it when none sits beside "
                             "the .sty the document uses: a selected kit that ships the package, then the "
                             "installed copy; each takes one place off). An "
                             "explicit -y/-H/-f/-V/--from always wins over --no-auto metadata/preamble "
                             "regardless of this flag -- --no-auto only stops pdfmd from filling in or "
                             "discovering what's otherwise unset. Same KIND names work in a document's "
                             "own pdfmd-options.no-auto front matter (see the module docstring)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show each decision pdfmd made, with its reason, as it happens (AUTO YAML, AUTO TEX, "
                             "AUTO MARGIN ...). Default is three short lines: FOUND (the metadata, preamble, "
                             "filter and parts it picked up), DEFAULTS (what it applied because nothing said "
                             "otherwise: the global metadata of --setup, margin, fonts, packages), and "
                             "'AUTO: KIND KIND' for the rest, each cut at the screen's width. AUTO ENGINE and "
                             "AUTO MD always print in full")
    parser.add_argument("--which", nargs="*", default=None, metavar="NAME",
                        help="say what a bare `pdfmd` would build and why (every Markdown file of the folder, its priority and "
                             "name, what happened to it, and the rules in force with the files they came from), or which file "
                             "each NAME finds, and build nothing. With --newest, --all or --no-auto priority: as they would act")
    parser.add_argument("--newest", action="store_true",
                        help="bare `pdfmd` in a folder with several Markdown files builds the most recently changed one, "
                             "whatever their priorities and names say (documents marked `priority: never` stay out; "
                             "see --all). The setting `ranking: {by: [priority, newest]}` (the default) uses the time "
                             "only for documents of equal priority")
    parser.add_argument("--all", "--include-never", dest="include_never", action="store_true",
                        help="count the documents marked `priority: never` too: -b, -r and the viewer include them, and a "
                             "bare `pdfmd` ranks them as if they had no priority")
    parser.add_argument("--no-citeproc", action="store_true",
                        help="don't add --citeproc automatically when the document uses @citation "
                             "syntax (by default pdfmd adds it, so citations and the bibliography "
                             "render without any flag)")
    parser.add_argument("--full-paths", action="store_true",
                        help="print full/absolute paths in AUTO YAML/TEX/MD lines and (with -v) the "
                             "CMD line, instead of the default -- relative to the current directory, "
                             "falling back to absolute only for a path that isn't under it (a system "
                             "temp file, e.g.). The default reads fine from a shallow directory but "
                             "gets hard to read fast from a deep one; --full-paths is the escape hatch "
                             "for a copy-pasteable absolute path, or when cwd itself is ambiguous in a "
                             "script's own log. -v/--verbose (or --debug) already implies this -- more "
                             "detail is the point of asking for it -- so --full-paths on its own is "
                             "only needed to get full paths WITHOUT the rest of --verbose's output")
    parser.add_argument("--path-style", choices=core.PATH_STYLES, default=None,
                        help="how a path is written in a message: auto (default: relative to the current folder, up to 2 "
                             "`..` steps above it, else ~/... under your home folder, else absolute), relative (the same "
                             "without ~), home (~/... under your home folder), full (absolute, as --full-paths). Also "
                             "`options: {path-style: home, path-up: 2}` in the config and in a folder's settings (pdfmd --setup). "
                             "-v/--verbose gives full unless this is given")
    parser.add_argument("--path-up", type=int, default=None, metavar="N",
                        help="how many `..` steps above the current folder a path may still be written relative (default 2); "
                             "a folder further up is written ~/... or in full. Also `options: {path-up: N}` (pdfmd --setup)")
    parser.add_argument("--debug", action="store_true",
                        help="on ANY PDF-engine failure -- even one a later engine in the fallback "
                             "chain recovers from -- print the engine's full captured stderr inline, "
                             "not just the one-line reason every failure now shows by default (see "
                             "'WARN ... failed (...)' -- that short reason needs no flag at all). "
                             "Implies --verbose. Use this instead of guessing which engine to force "
                             "with --engine when a document's rendered output doesn't match what the "
                             "Markdown predicts and the short reason alone isn't enough to tell why")
    parser.add_argument("--bopen", nargs="?", const="all", default=None, metavar="SPEC",
                        help="in a batch (-b), open the finished files when it is done, which of them SPEC says: "
                             + core.BOPEN_HELP + " (fl15 = 8 first and 7 last; no SPEC = all). In a single-file build it is --open")
    parser.add_argument("--open", action="store_true",
                        help="open the finished file (via macOS 'open', Linux 'xdg-open' or Windows' default app) once "
                             "conversion succeeds. Applies to single-file and report/book mode, "
                             "each of which produce exactly one output; ignored in batch mode "
                             "(-b), which would otherwise pop open every file in the directory")
    parser.add_argument("--keep-aux", action="store_true",
                        help="for a direct .tex compile (see 'Input formats' in the module "
                             "docstring), keep .aux/.log/.out/etc. beside the source instead of "
                             "the v3.1.0-default scratch-directory cleanup that leaves only the "
                             "PDF -- use this to inspect a failing or suspicious compile's own "
                             ".log by hand. No effect on a Markdown (Pandoc-mediated) input")
    parser.add_argument("-w", "--watch", action="store_true",
                        help="recompile automatically whenever the source file, or anything in its "
                             "own directory/metadata subfolder, changes on disk -- polling, not a "
                             "filesystem-events library, so it can miss a change made and reverted "
                             "within one poll interval (WATCH_INTERVAL, 1 second). Single-file mode "
                             "only, not -b/--batch or -r/--report. Compiles once immediately, then "
                             "again on each detected change, until Ctrl+C")
    stamp_enable = parser.add_mutually_exclusive_group()
    stamp_enable.add_argument("--stamp", action="store_true", default=None,
                              help="on a successful compile, append/update a 'BUILD NOTES' HTML "
                                   "comment near the end of the .md source recording what compiled "
                                   "it and when -- invisible in the rendered output, visible in the "
                                   "source. Off by default; also settable (and this is where a "
                                   "shared default belongs) via pdfmd-options.stamp in a document's "
                                   "own front matter or a --metadata-file, which this always "
                                   "overrides when given. See --stamp-mode/--stamp-packages/"
                                   "--stamp-scope/--stamp-output for the rest of its settings")
    stamp_enable.add_argument("--no-stamp", action="store_true", default=None,
                              help="force stamping off for this run, overriding pdfmd-options.stamp "
                                   "even if a document or metadata file turns it on")
    parser.add_argument("--stamp-mode", choices=sorted(core.STAMP_MODES), default=None,
                        help="'replace' (default): overwrite the current stamp line in place. "
                             "'history': keep one live stamp line at the top (right under BUILD "
                             "NOTES) and demote the previous one into a 'Compile History:' list at "
                             "the end of the comment, newest-demoted-first -- both leave any other "
                             "hand-written notes in the block untouched. Switching back to 'replace' "
                             "later freezes rather than deletes an existing history list (warns)")
    parser.add_argument("--stamp-store", choices=sorted(core.STAMP_STORES), default=None,
                        help="where --stamp writes a compile: 'notes' (default) the document's BUILD NOTES block, 'file' "
                             "a NAME.hst history file beside the backups (the document is left alone), or 'both'")
    parser.add_argument("--history-to-file", action="store_true",
                        help="move pdfmd's own lines out of FILE's BUILD NOTES block(s) into NAME.hst (merged with what is "
                             "there); what anybody else wrote in the block stays. Backed up first; --dry-run only shows")
    parser.add_argument("--history-to-notes", action="store_true",
                        help="the reverse: the compiles in NAME.hst go into FILE's BUILD NOTES (newest on top, the rest as "
                             "the history list) and leave the file")
    parser.add_argument("--history", action="store_true",
                        help="list FILE's versions, newest first: its backups (in every folder and naming form pdfmd "
                             "knows), its git commits, and compiles recorded in its history; in a terminal the list "
                             "is navigable (a number: what differs, d N: diff, r N: restore). Shows the newest 15")
    parser.add_argument("--history-all", action="store_true", help="with --history: list every version")
    parser.add_argument("--history-diff", metavar="REF",
                        help="show what differs between FILE and one of its versions: a number from --history, a "
                             "backup's timestamp (any prefix), its file name, a commit hash, `latest` or `previous`")
    parser.add_argument("--history-restore", metavar="REF",
                        help="put a version back as FILE (REF as for --history-diff). The file as it is now is backed up "
                             "first, its BUILD NOTES and history stay those of the newest file, and a 'Restored' entry "
                             "is added to the history; --dry-run shows the difference without writing")
    parser.add_argument("--no-restored-note", action="store_true",
                        help="with --history-restore: leave no 'Restored ...' entry (also `stamp: {restored-note: false}`)")
    parser.add_argument("--init-backups", action="store_true",
                        help="switch on backups and a history file for FILE: `backup` and `stamp: {store: file}` go into its "
                             "front matter (or its metadata.yaml) with an AUTO GENERATED note, the folder is made "
                             "(.backups, or --backup-folder), and the file is backed up once. --global sets them in "
                             "the config for every document instead")
    parser.add_argument("--backup-folder", metavar="FOLDER", default=None,
                        help="with --init-backups: where the copies go (beside the document, or an absolute path); "
                             "default .backups")
    parser.add_argument("--global", dest="global_", action="store_true", help="with --init-backups: for every document")
    parser.add_argument("--merge-history", nargs="+", metavar="HST",
                        help="join NAME.hst files: every entry once, newest first (to -o FILE, else printed)")
    parser.add_argument("--stamp-packages", nargs="+", default=None, metavar="PKG",
                        help="LaTeX package name(s) (e.g. nulabreport) whose version to include in "
                             "the stamp line, found via 'kpsewhich PKG.sty' and that file's own "
                             "\\ProvidesPackage line. A named package is silently left out of the "
                             "line if it isn't actually \\usepackage'd by this document's preambles/ "
                             "header-includes, or if its version can't be determined this way. "
                             "Default: none -- the stamp line then names only pdfmd's own version")
    parser.add_argument("--stamp-scope", choices=sorted(core.STAMP_SCOPES), default=None,
                        help="when stamping actually happens: 'always' (default) -- every successful "
                             "compile, standalone/batch or as part of a report/book; 'report' -- only "
                             "when this document is compiled as one chapter of a -r/--report build, "
                             "not on its own; 'standalone' -- the opposite, only outside -r/--report")
    stamp_output = parser.add_mutually_exclusive_group()
    stamp_output.add_argument("--stamp-output", action="store_true", default=None,
                              help="name the rendered output file in a standalone/batch stamp line "
                                   "('Compiled to `report.pdf` with ...') -- a report/book chapter's "
                                   "stamp always names the shared output ('...as part of `book.pdf`') "
                                   "regardless of this flag")
    stamp_output.add_argument("--no-stamp-output", action="store_true", default=None,
                              help="never name the output file in a standalone/batch stamp line, "
                                   "even if pdfmd-options.stamp.include_output turned it on")
    stamp_pdf = parser.add_mutually_exclusive_group()
    stamp_pdf.add_argument("--stamp-pdf-metadata", action="store_true", default=None,
                           help="force PDF-metadata embedding on (it's already on by default -- see "
                                "--no-stamp-pdf-metadata); only useful to override a document/"
                                "metadata file that set pdf_metadata: false")
    stamp_pdf.add_argument("--no-stamp-pdf-metadata", action="store_true", default=None,
                           help="on by default, independently of --stamp/pdfmd-options.stamp.enabled "
                                "(which only gates the .md BUILD NOTES comment): embeds the same "
                                "package/pdfmd version info as two custom PDF Info-dictionary keys "
                                "(PdfmdVersions, PdfmdBuildDate) on every LaTeX-engine compile -- "
                                "inspectable with exiftool/pdfinfo, invisible on the rendered page "
                                "and in a normal 'Document Properties' panel, and additive (never "
                                "overwrites pdftitle/pdfauthor/etc., a document's own or Pandoc's). "
                                "This flag turns it off; --stamp-pdf-metadata forces it back on over "
                                "a document/metadata file that disabled it. No effect on a non-LaTeX "
                                "PDF engine (weasyprint, typst, ...), which has no equivalent "
                                "mechanism this reaches")
    stamp_partial = parser.add_mutually_exclusive_group()
    stamp_partial.add_argument("--stamp-partial", action="store_true", default=None,
                               help="a build of some parts or sections (`pdfmd @60`) leaves a 'partial' entry in the "
                                    "NAME.hst history (needs --stamp-store file or both): which parts it built and which of "
                                    "them changed since the last entry that saw them. Off by default (also "
                                    "`stamp: {partial: true}`)")
    stamp_partial.add_argument("--no-stamp-partial", action="store_true", default=None,
                               help="a partial build leaves nothing in the history (the default); overrides a document or "
                                    "metadata file that set `stamp: {partial: true}`")
    backup_enable = parser.add_mutually_exclusive_group()
    backup_enable.add_argument("--backup", action="store_true", default=None,
                               help="after a successful compile, copy the source to "
                                    ".backups/<name>.bak.YYYYMMDDHHMMSS beside it (skipped when the "
                                    "newest backup is already identical). Off by default; also "
                                    "settable via pdfmd-options.backup in a document's own front "
                                    "matter or a --metadata-file (with dir:/keep: there), which this "
                                    "overrides when given")
    backup_enable.add_argument("--no-backup", action="store_false", dest="backup", default=None,
                               help="force backups off for this run, overriding pdfmd-options.backup")
    parser.add_argument("--backup-format", default=None, metavar="FORMAT",
                        help="snapshot name for this run: a preset (compact: report.md.bak."
                             "20260924091500 [default], dashed: report.md.bak.20260924-091500, stem: "
                             "report_20260924-091500.md, suffix: report.md.20260924-091500.bak, short: "
                             "report.md.09-24_09-15-00.bak) or a template using {name}/{stem}/{ext} "
                             "plus strftime codes. Overrides pdfmd-options.backup.format")
    return parser

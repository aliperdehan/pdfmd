"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_labels.seed`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import time
from pathlib import Path

from pdfmd_base import core
from pdfmd_base import timed


# LaTeX side of the counter seeding: \pdfmdpart{key}, at the start of each part
# of a cache build, writes the counters' values into the .aux as
# \pdfmd@part{key}{section=2,figure=1,...} (\pdfmd@part is a no-op when the
# .aux is read back) and, if a partial build's seed file defined
# \pdfmd@st@key, runs it: the counters jump to what they were at that point
# of the last full build -- at EVERY selected part, so Discussion+Appendix
# keeps the Appendix's own number. Expandable throughout (\ifcsname), so it is safe inside
# \write, and counters a document does not have are skipped.
PARTS_MARKER_DEFS = r"""\makeatletter
\providecommand\pdfmd@part[2]{}
\newcommand\pdfmd@c[1]{\ifcsname c@#1\endcsname #1=\number\csname c@#1\endcsname,\fi}
\newcommand\pdfmdpart[1]{\immediate\write\@auxout{\string\pdfmd@part{#1}{%
  \pdfmd@c{section}\pdfmd@c{subsection}\pdfmd@c{subsubsection}\pdfmd@c{figure}%
  \pdfmd@c{table}\pdfmd@c{equation}\pdfmd@c{footnote}\pdfmd@c{reaction}\pdfmd@c{scheme}}}%
  \ifcsname pdfmd@st@#1\endcsname\csname pdfmd@st@#1\endcsname\fi}
\makeatother
"""


DRAFT_FLAGS = {"lualatex": "-draftmode", "pdflatex": "-draftmode", "xelatex": "-no-pdf"}   # a pass without output


# The draft pass only counts, so it does not draw (v3.27.23): a tikzpicture (pgfplots inside it too), \chemfig, a chemfig
# \schemestart...\schemestop and an image cost most of a nulabreport report's pass and step no counter (a figure's
# \caption is outside its picture). A picture is skipped up to its literal \end{tikzpicture}; the commands DRAFT_SKIP_COMMANDS
# (one argument after any optional ones) and the spans DRAFT_SKIP_SPANS (a start macro up to its stop macro) are dropped, and a
# package may add its own in `<package>-pdfmd.yaml` (`draft-skip:` with `commands:` and `spans:`). When that \end is hidden
# in a macro, the skip meets \end{<the environment around the picture>} or \end{document} first: it says so in the log,
# and build_label_scan runs the pass again with the pictures (draft_skip_problem). Needs LaTeX 2020-10 (\AddToHook).
DRAFT_SKIP_COMMANDS = ("chemfig",)


DRAFT_SKIP_SPANS = {"schemestart": "schemestop"}


DRAFT_SKIP_PICTURES = r"""% pdfmd: a pass that only counts the numbers, so the pictures are not drawn
\makeatletter
\ifdefined\AddToHook
\def\pdfmd@picenv{tikzpicture}\def\pdfmd@docenv{document}\let\pdfmd@outerenv\@empty
\AddToHook{env/tikzpicture/before}{\let\pdfmd@outerenv\@currenvir}
\long\def\pdfmd@skippic#1\end#2{\def\pdfmd@arg{#2}\let\pdfmd@next\pdfmd@skippic
  \ifx\pdfmd@arg\pdfmd@picenv\let\pdfmd@next\pdfmd@skippicdone\fi
  \ifx\pdfmd@arg\pdfmd@outerenv\let\pdfmd@next\pdfmd@skipfailed\fi
  \ifx\pdfmd@arg\pdfmd@docenv\let\pdfmd@next\pdfmd@skipfailed\fi
  \pdfmd@next}
\def\pdfmd@skippicdone{\end{tikzpicture}}
\def\pdfmd@skipfailed{\typeout{PDFMD-DRAFT-SKIP-FAILED}\end{tikzpicture}\expandafter\end\expandafter{\pdfmd@arg}}
\def\pdfmd@tikz{\ifx\@currenvir\pdfmd@picenv\let\endtikzpicture\relax\expandafter\pdfmd@skippic
  \else\let\endtikzpicture\pdfmd@endtikzpicture\expandafter\pdfmd@tikzpicture\fi}
\def\pdfmd@chemfig{\@ifstar\pdfmd@cf\pdfmd@cf}
\def\pdfmd@cf{\@ifnextchar[\pdfmd@cfopt\pdfmd@cfarg}
\def\pdfmd@cfopt[#1]{\@ifnextchar[\pdfmd@cfopt\pdfmd@cfarg}
\long\def\pdfmd@cfarg#1{}
@@SPANS@@\AtBeginDocument{%
  \@ifundefined{tikzpicture}{}{\let\pdfmd@tikzpicture\tikzpicture\let\pdfmd@endtikzpicture\endtikzpicture
    \let\tikzpicture\pdfmd@tikz}%
@@HOOKS@@  \@ifundefined{Gin@setfile}{}{\setkeys{Gin}{draft}}}
\fi
\makeatother
"""


PART_COUNTER_RE = re.compile(r"^\\pdfmd@part\{([^{}]*)\}\{([^{}]*)\}\s*$")


SEED_LABEL_RE = re.compile(r"^\\newlabel\{([^{}]*)\}(\{.*\})\s*$")


def package_draft_skips(md_path: Path, metadata_files: list[Path],
                        no_auto: list[str] | None = None) -> tuple[list[str], dict[str, str]]:
    """(commands, spans) the draft pass need not draw: DRAFT_SKIP_COMMANDS and DRAFT_SKIP_SPANS and what the packages the
    document loads add in their `<package>-pdfmd.yaml` (`draft-skip:`); names are letters only."""
    commands = list(DRAFT_SKIP_COMMANDS)
    spans = dict(DRAFT_SKIP_SPANS)
    for folder, package, _ in core.office_packages(md_path, metadata_files, None):
        helper = core.package_helper(folder, package, no_auto, md_path)
        wanted = helper[0].get("draft-skip") if helper else None
        if not isinstance(wanted, dict):
            continue
        for name in wanted.get("commands") or []:
            if isinstance(name, str) and re.fullmatch(r"[A-Za-z]+", name) and name not in commands:
                commands.append(name)
        for start, stop in (wanted.get("spans") or {}).items() if isinstance(wanted.get("spans"), dict) else ():
            if re.fullmatch(r"[A-Za-z]+", str(start)) and re.fullmatch(r"[A-Za-z]+", str(stop)):
                spans.setdefault(str(start), str(stop))
    return commands, spans


def draft_skip_text(commands, spans) -> str:
    """DRAFT_SKIP_PICTURES for these commands and spans."""
    definitions = "".join(f"\\long\\def\\pdfmd@span@{start}#1\\{stop}{{}}\n" for start, stop in spans.items())
    hooks = "".join(f"  \\@ifundefined{{{name}}}{{}}{{\\let\\{name}\\pdfmd@chemfig}}%\n" for name in commands)
    hooks += "".join(f"  \\@ifundefined{{{start}}}{{}}{{\\let\\{start}\\pdfmd@span@{start}}}%\n" for start in spans)
    return DRAFT_SKIP_PICTURES.replace("@@SPANS@@", definitions).replace("@@HOOKS@@", hooks)


def draft_skip_problem(log: Path, aux: Path, text: str) -> str | None:
    """Why a draft pass that skipped the pictures (DRAFT_SKIP_PICTURES) cannot be trusted, or None: a skip that met
    another environment's end first, a LaTeX error about the skip or a picture, or a label of the document's body that
    the pass did not define (the skip swallowed it). Ordinary errors of the document do not count: the pass with the
    pictures would have them too."""
    try:
        log_text = log.read_text(encoding="utf-8", errors="replace")
        aux_text = aux.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "it left no .aux"
    if "PDFMD-DRAFT-SKIP-FAILED" in log_text:
        return "a picture ends inside a macro"
    for block in re.findall(r"^!.*(?:\n.*){0,3}", log_text, re.MULTILINE):
        if "pdfmd@" in block or "tikzpicture" in block:
            return block.splitlines()[0].lstrip("! ").strip()
    defined = set(re.findall(r"^\\newlabel\{([^{}]*)\}", aux_text, re.MULTILINE))
    body = text[text.find("\\begin{document}"):]
    missing = sorted(set(re.findall(r"\\label\{([^{}]*)\}", body)) - defined)
    if missing:
        return f"{len(missing)} labels went missing ({missing[0]})"
    return None


def label_without_page(value: str) -> str:
    """A \\newlabel value with its page number left out (``??``): a pass that skipped the pictures has the right numbers
    but not the right pages. ``{{3}{12}{..}{..}{}}`` has the page second; so does cleveref's
    ``{{[table][3][]3}{[1][12][]12}{}{}{}}``, whose page group keeps its form (``[1][0][]??``) for \\cpageref."""
    groups, depth, start = [], 0, None
    inner = value[1:-1] if value.startswith("{") and value.endswith("}") else value
    for index, character in enumerate(inner):
        if character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(inner[start:index + 1])
    if len(groups) < 2:
        return value
    groups[1] = "{[1][0][]??}" if groups[0].startswith("{[") else "{??}"
    return "{" + "".join(groups) + "}"


def seed_labels_file(full_aux: Path, target: Path, pages: bool = True) -> int:
    """Write ``target`` (a .tex fragment) that defines every label of the last
    full build's .aux that a partial build does not define itself, and, per
    part, the counter values at its start (\\pdfmd@st@key, run by
    \\pdfmdpart), so a part's own numbers continue from the full report's
    instead of restarting at 1. Returns the number of labels; 0 writes
    nothing. Defining only the undefined is what keeps a part's own labels
    authoritative. ``pages=False`` leaves the labels' page numbers out
    (``??``), for a draft pass that skipped the pictures.
    """
    try:
        lines = full_aux.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    seeded = []
    counters = []
    for line in lines:
        match = SEED_LABEL_RE.match(line)
        if match:
            value = match.group(2) if pages else label_without_page(match.group(2))
            seeded.append(f"\\pdfmd@seed{{{match.group(1)}}}{value}")
            continue
        match = PART_COUNTER_RE.match(line)
        if match:
            sets = []
            for item in match.group(2).split(","):
                name, _, value = item.partition("=")
                if name.isalpha() and value.lstrip("-").isdigit():
                    sets.append(f"\\ifcsname c@{name}\\endcsname\\setcounter{{{name}}}{{{value}}}\\fi")
            counters.append(f"\\expandafter\\gdef\\csname pdfmd@st@{match.group(1)}\\endcsname{{{''.join(sets)}}}")
    if not seeded and not counters:
        return 0
    target.write_text(
        "\\makeatletter\n"
        "\\providecommand\\pdfmd@seed[2]{\\@ifundefined{r@#1}{\\expandafter\\gdef\\csname r@#1\\endcsname{#2}}{}}\n"
        + "\n".join(seeded + counters) + "\n\\makeatother\n", encoding="utf-8")
    return len(seeded)


def part_key(part: Path, parts_root: Path | None) -> str:
    """The name a part is recorded under in the .aux: its path under the parts
    folder, reduced to characters that are safe inside a TeX argument."""
    relative = part.relative_to(parts_root).as_posix() if parts_root else part.name
    return re.sub(r"[^A-Za-z0-9./_+-]", "-", relative)


def safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]", "-", name)


REF_USE_RE = re.compile(r"\\(?:auto|eq|page|name|vpage|[cCvV])?ref\*?\s*\{|(?<![\w@])@(?:sec|fig|tbl|eq|lst):")


def seed_labels_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """auto (default) | aux | scan | draft | off, from --seed-labels, else `pdfmd-options.seed-labels`."""
    try:
        import pdfmd_labels
    except ImportError:
        return "off"
    value = core.SEED_LABELS_CLI
    if value is None:
        sources = [core.frontmatter_pdfmd_options(md_path)]
        for metadata_file in core.metadata_files_by_priority(metadata_files):
            options = core.metadata_file_yaml(metadata_file).get("pdfmd-options")
            sources.append(options if isinstance(options, dict) else {})
        sources.append(core.config_options(md_path))
        for options in sources:
            if "seed-labels" in options:
                value = options["seed-labels"]
                break
    if value is None:
        return "auto"
    mode = {True: "auto", False: "off"}.get(value) if isinstance(value, bool) else str(value).strip().lower()
    if mode not in pdfmd_labels.MODES:
        raise SystemExit(f"{md_path}: unknown seed-labels value {value!r}. Valid: {', '.join(pdfmd_labels.MODES)}")
    return mode


SEED_CALC_MODES = ("auto", "scan", "off")


def seed_calc_mode(md_path: Path, metadata_files: list[Path]) -> str:
    """auto (default, same as scan) | scan | off, from --seed-calc, else `pdfmd-options.seed-calc`."""
    value = core.SEED_CALC_CLI
    if value is None:
        value = core.first_pdfmd_option(md_path, metadata_files, "seed-calc")
    if value is None:
        return "auto"
    mode = {True: "auto", False: "off"}.get(value) if isinstance(value, bool) else str(value).strip().lower()
    if mode not in SEED_CALC_MODES:
        raise SystemExit(f"{core.display_path(md_path)}: unknown seed-calc value {value!r}. Valid: {', '.join(SEED_CALC_MODES)}")
    return mode


def parts_range_text(parts: list[Path]) -> str:
    """`parts 10-50` for the NOTE of a build that took names from them (their numeric prefixes, else their stems)."""
    if not parts:
        return ""
    if len(parts) == 1:
        number = parts[0].stem.split("-")[0]
        return f"part {number if number.isdigit() else parts[0].stem}"
    numbers = [part.stem.split("-")[0] for part in (parts[0], parts[-1])]
    return ("parts " + "-".join(numbers)) if all(number.isdigit() for number in numbers) \
        else f"parts {parts[0].stem} to {parts[-1].stem}"


@timed("calc seed")
def build_calc_seed(md_path: Path, metadata_files: list[Path], selected: list[Path], inputs: list[Path],
                    scratch: Path, from_format: str | None, verbose: bool) -> tuple[Path | None, int, Path | None, int]:
    """The names a part built alone needs from the rest of the document (v3.30.19 for the parts above it, v3.31.44 for the parts
    below it; `pdfmd-options: {seed-calc: auto|scan|off}`). Pandoc reads ``inputs`` (the whole document in order, with a
    `pdfmd-calc-mark-in` / `-out` paragraph around each part built, see ``calc_marked_inputs``) with only calc.lua, to nowhere;
    calc.lua writes, at full precision and with its digits, each name's last definition above the part and its first definition
    below it, each evaluated in its own place in the whole document, and the build reads the two files back: the first as
    definitions above the document, the second as definitions after it, so a name counts from there only when nothing above or
    inside the part defines it (the full build's rule: the nearest definition above, else the first below). Nothing is stored
    between builds, so nothing can be stale.
    (the names above and how many, the names below and how many); a file is None when it has no names or cannot be made: the
    build goes on without."""
    nothing = (None, 0, None, 0)
    arguments = core.calc_filter_args(selected, metadata_files)       # [] when calc is off or the part holds no span or div
    if not arguments:
        return nothing
    if not any(core.CALC_SPAN_RE.search(core.EMBED_BLOCK_RE.sub("", core.read_text_best_effort(file)))
               for file in inputs if not file.name.startswith("pdfmd-calc-mark-") and file not in selected[1:]):
        return nothing
    halves = scratch / "calc-halves.tsv"
    cmd = ["pandoc", *(str(file.resolve()) for file in inputs), *(["-f", from_format] if from_format else []),
           "-t", "native", "-o", str(scratch / "calc-names.native"), *arguments, "-V", "pdfmd-calc-halves=" + str(halves)]
    cwd = core.pandoc_working_directory(md_path.parent)
    core.log_cmd(cmd, cwd, verbose)
    started = time.time()
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    except OSError as error:
        core.vprint(verbose, f"CALC      the names of the parts left out could not be evaluated ({error})")
        return nothing
    if done.returncode != 0 or not halves.is_file():
        core.vprint(verbose, "CALC      the names of the parts left out could not be evaluated; the build goes on without them")
        return nothing
    lines = {"A": [], "B": []}
    gaps = {}
    for line in halves.read_text(encoding="utf-8", errors="replace").splitlines():
        kind, _, rest = line.partition("\t")
        if kind in lines and rest.strip():
            lines[kind].append(rest)
        elif kind == "G":
            slot, _, name = rest.partition("\t")
            if slot.isdigit() and name:
                gaps.setdefault(int(slot), set()).add(name)
    if gaps:
        core.load_package("pdfmd_calc").warn_seed_gaps(gaps, inputs)
    files = []
    for kind, name in (("A", "calc-names.tsv"), ("B", "calc-names-below.tsv")):
        if lines[kind]:
            path = scratch / name
            path.write_text("\n".join(lines[kind]) + "\n", encoding="utf-8")
            files.append((path, len(lines[kind])))
        else:
            files.append((None, 0))
    core.vprint(verbose, f"CALC      {files[0][1]} names above and {files[1][1]} below the part evaluated in {time.time() - started:.1f} s")
    return files[0][0], files[0][1], files[1][0], files[1][1]


def calc_marked_inputs(scaffold: Path, parts: list[Path], built: list[Path], scratch: Path) -> list[Path]:
    """The whole document for the names-only pass of ``build_calc_seed``: the scaffold, then every part in order, a one-word
    paragraph before and after each part that is built (calc.lua notes where the built parts stand)."""
    mark_in, mark_out = scratch / "pdfmd-calc-mark-in.md", scratch / "pdfmd-calc-mark-out.md"
    mark_in.write_text("pdfmd-calc-mark-in\n", encoding="utf-8")
    mark_out.write_text("pdfmd-calc-mark-out\n", encoding="utf-8")
    inputs = [scaffold]
    for part in parts:
        inputs += [mark_in, part, mark_out] if part in built else [part]
    return inputs


class LabelScan:
    """The header files that make a partial build know the labels of the whole document (see above)."""

    def __init__(self, headers: list[Path], labels: int, steps: int, markers: bool, exact: bool = False,
                 skipped: int = 0):
        self.headers, self.labels, self.steps, self.skipped = headers, labels, steps, skipped
        self.exact = exact             # the numbers come from a LaTeX pass over the whole document (draft), not a count
        self.markers = markers         # whether the headers define \pdfmdpart (PARTS_MARKER_DEFS) too


def label_scan_wanted(mode: str, target_format: str, engines: list[str], presentation: bool, md_path: Path,
                      partial: bool, parts_mode: bool, texts: list[str]) -> bool:
    """Whether a build should take its missing labels from a scan: a partial build for a LaTeX engine; a part of a
    split document always (its numbers continue from the parts before it), a section of an ordinary document only when
    its text refers to something."""
    if mode not in ("auto", "scan", "draft") or not partial or presentation or md_path.suffix.lower() != ".md":
        return False
    if target_format != "pdf":                  # a .tex handed to the user stays the plain LaTeX of the part
        return False
    if not any(engine in core.LATEX_ENGINES and engine not in ("context", "latexmk", "tectonic")
                                          for engine in engines):
        return False
    return parts_mode or any(REF_USE_RE.search(text) for text in texts)


def select_wanted(mode: str, target_format: str, engines: list[str], presentation: bool, md_path: Path) -> bool:
    """Whether a partial build for a writer other than LaTeX numbers the whole document and keeps the part: HTML, Word,
    OpenDocument, Typst, EPUB, and PDF through an engine that is not LaTeX or a built-in renderer."""
    if mode not in ("auto", "scan", "draft") or presentation or md_path.suffix.lower() != ".md":
        return False
    if target_format in core.TEX_STANDALONE_FORMATS or target_format == core.ASSEMBLED_FORMAT:
        return False
    if target_format == "pdf":
        return not any(engine in core.LATEX_ENGINES or core.is_native_engine(engine) for engine in engines)
    return True


@timed("label scan")
def build_label_scan(md_path: Path, scratch: Path, font: str, engines: list[str], variables: list[str],
                     slide_level: int | None, pandoc_options: list[str], metadata_file, preamble_files,
                     from_format: str | None, no_auto: list[str] | None, stamp_overrides: dict,
                     trust_embedded: bool, all_parts: list[Path], parts_root: Path | None,
                     verbose: bool, draft: bool = False) -> "LabelScan | None":
    """Pandoc's LaTeX of the whole document, scanned (and, with ``draft``, run through the LaTeX engine once without
    output, whose .aux then gives the exact numbers). None when it cannot be made (the build goes on without)."""
    import pdfmd_labels
    started = time.time()
    tex_path = scratch / "labels-scan.tex"
    defs = scratch / "labels-defs.tex"
    markers = bool(all_parts and parts_root is not None)
    if markers:
        defs.write_text(PARTS_MARKER_DEFS, encoding="utf-8")
    draft_engine = next((engine for engine in engines if engine in DRAFT_FLAGS), None) if draft else None
    if draft and draft_engine is None:
        core.vprint(verbose, "LABELS    no engine here can run a draft pass (lualatex, xelatex, pdflatex); the scan alone is used")
    cheap = ["svg", "remoteimages", "pdfimages"]
    scan_no_auto = no_auto if (no_auto is not None and not no_auto) else [*(no_auto or []), *cheap]
    saved_build = dict(core.BUILD)
    saved_log = core.AUTO_LOG.snapshot()
    core.BUILD["scanning"] = True
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            built = core._convert_one(md_path, None, False, font, engines, variables, slide_level, pandoc_options,
                                 metadata_file, tex_path,
                                 [*(preamble_files or []), *([defs] if markers and draft_engine else [])],
                                 target_format="latex",
                                 from_format=from_format, no_auto=scan_no_auto, verbose=False, debug=False,
                                 stamp_overrides=stamp_overrides, keep_aux=False, extra_inputs=list(all_parts) or None,
                                 partial=False, cache_cli=False, skip_stamp=True, parts_root=parts_root,
                                 part_markers=bool(all_parts and parts_root), trust_embedded=trust_embedded)
    except (SystemExit, Exception) as error:  # noqa: BLE001 -- the scan is a convenience; the build must not die of it
        core.vprint(verbose, f"LABELS    the whole-document scan failed ({error}); references to parts left out stay ??")
        return None
    finally:
        core.BUILD.clear()
        core.BUILD.update(saved_build)                  # what the scan recorded (its scratch .tex) is not the build's
        core.AUTO_LOG.restore(saved_log)                # its summary went to nowhere and must not take the build's FOUND items
    if not built[1] or not tex_path.is_file():
        core.vprint(verbose, "LABELS    the whole-document scan failed; references to parts left out stay ??")
        return None
    result = pdfmd_labels.scan(tex_path.read_text(encoding="utf-8", errors="replace"))
    if not result.labels and not result.parts():
        return None
    seed = scratch / "labels-seed.tex"
    seed.write_text(pdfmd_labels.render(result), encoding="utf-8")
    core.vprint(verbose, f"LABELS    scanned the whole document in {time.time() - started:.1f} s: {result.labels} labels, "
          f"{result.steps} numbered items, {result.parts()} parts"
          + (f"; {result.skipped} labels left out (after a caption in an environment it does not know)"
             if result.skipped else ""))
    headers = [seed]
    exact = False
    if draft_engine is not None:
        metadata_list = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
        pandoc_cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_list, md_path.parent))
        began = time.time()
        command = [draft_engine, DRAFT_FLAGS[draft_engine], "-interaction=nonstopmode", "-output-directory",
                   core.tex_argument(scratch), core.tex_argument(tex_path)]
        whole = tex_path.read_text(encoding="utf-8", errors="replace")
        quick = not core.auto_disabled(no_auto, "draftpictures") and whole.count("\\begin{document}") == 1

        last_run: dict = {}

        def draft_pass(text: str) -> None:
            tex_path.write_text(text, encoding="utf-8")
            try:
                last_run["done"] = subprocess.run(command, cwd=pandoc_cwd,
                                                  env={**os.environ, **(core.tex_search_env(md_path.parent, pandoc_cwd, md_path) or {})},
                                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
            except (OSError, subprocess.SubprocessError) as error:
                core.vprint(verbose, f"LABELS    the draft pass could not run ({error}); the scan alone is used")

        if quick:
            draft_pass(whole.replace("\\begin{document}",
                                     draft_skip_text(*package_draft_skips(md_path, metadata_list, no_auto)) + "\\begin{document}"))
            problem = draft_skip_problem(scratch / "labels-scan.log", scratch / "labels-scan.aux", whole)
            if problem:
                core.vprint(verbose, f"LABELS    the draft pass without the pictures cannot be trusted ({problem}); "
                      "running it with them")
                quick = False
                draft_pass(whole)
        else:
            draft_pass(whole)
        aux_seed = scratch / "labels-aux-seed.tex"
        found = seed_labels_file(scratch / "labels-scan.aux", aux_seed, pages=not quick)
        if found:
            hook = scratch / "labels-aux-hook.tex"
            hook.write_text("\\AtBeginDocument{\\InputIfFileExists{\"%s\"}{}{}}\n" % aux_seed.as_posix(), encoding="utf-8")
            headers.insert(0, hook)
            exact = True
            core.vprint(verbose, f"LABELS    draft pass over the whole document{' (pictures not drawn, page numbers ??)' if quick else ''}: "
                  f"{found} labels in {time.time() - began:.1f} s")
        else:
            core.vprint(verbose, "LABELS    the draft pass left no .aux; the scan alone is used")
            done = last_run.get("done")
            if done is not None:
                tail = " | ".join(line.strip() for line in (done.stdout + done.stderr).splitlines()[-4:] if line.strip())
                core.vprint(verbose, f"LABELS    {draft_engine} exited {done.returncode}: {tail[:300]}")
    if markers:
        headers.insert(0, defs)
    return LabelScan(headers, result.labels, result.steps, markers, exact, result.skipped)

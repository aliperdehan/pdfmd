"""LaTeX itself: the preamble files pdfmd accepts (`is_latex_preamble`, `top_level_tikzpicture`), a front matter's literal
`header-includes:` kept as raw LaTeX (`wrap_latex_header_includes`), the front-matter keys a LaTeX package asks for as macros
(`package_latex_keys`, `document_latex_definitions`), why an engine failed (`engine_failure_reason`, `tex_failure_cause` with
`TEX_CAUSES` and `TEX_PACKAGES`, `tex_log_failure_reason`, `tex_log_dewrap`; `pandoc_refused_command` for a command line Pandoc
refuses, which no other engine changes, v3.33.44), the direct compile of a `.tex` without Pandoc with its
reruns and bibtex/biber pass (`compile_tex_direct`, `run_tex_engine`, `latex_engine_command`, `tex_bibliography_tool`,
`tex_wants_rerun`), and the standalone jobs of the picture cache (`render_plot_requests`, `plot_recorded_inputs`, `plot_preamble`,
`tex_tree_stamp`).

Moved out of `pdfmd.py` unchanged (v3.33.36, SPLIT.md), with `TEX_CAUSES`, `TEX_PACKAGES`, `MAX_TEX_DIRECT_PASSES`,
`TEX_RERUN_TRIGGERS`, `TEX_LOG_WRAP_WIDTH`, `AUX_CLEAN_SUFFIXES` and `PLOT_CTX_TWICE`, `PLOT_CTX_MARGIN` and `PLOT_CTX_PLAIN` (the
protocol they belong to is described in `pdfmd.py`, above `CACHE_HANDSHAKE`, which stays). `core` is the `pdfmd` module, bound by
`pdfmd.py` when it loads (the first binding wins); the pdfmd names the code uses (`ENGINE_FAMILY`, `LATEX_ENGINES`,
`TECTONIC_SEARCH_ENV`, `frontmatter_value`, `log_cmd`, `office_packages`, `package_helper`, `pdfmd_chain` (since v3.33.71), `record_engine`,
`report_engine_failure`, `run_probe`, `sha1_file`, `tex_argument`, `vprint` and `which`) are read as `core.X` when it runs;
`run_probe` and `which` are patched by tests as `pdfmd.X`. `render_plot_requests` and `compile_tex_direct` were decorated with
`pdfmd`'s `@timed`, which is defined far below the place where the package loads: `_timed` is the same decorator looked up at
call time (`core.timed(name)(function)`). `json` and `concurrent.futures` stay imported inside `render_plot_requests`.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from tempfile import mkdtemp, mkstemp
from textwrap import dedent

core = None


def _timed(name):
    """`core.timed(name)` for a function defined before `core.timed` exists: each call is wrapped when it is made."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return core.timed(name)(function)(*args, **kwargs)
        return wrapper
    return decorate


def is_latex_preamble(path: Path) -> bool:
    """Accept preamble snippets, but reject complete documents and TikZ images. A tikzpicture inside a definition
    (``\\newenvironment{plot}{\\begin{tikzpicture}}{\\end{tikzpicture}}``) belongs to a preamble: only one at the top
    level makes the file a picture (v3.27.25; any tikzpicture used to, so such a preamble was left out unannounced and
    the build stopped at the first use of the environment)."""
    text = path.read_text(encoding="utf-8-sig")
    forbidden = r"\\(?:documentclass|begin\s*\{document\}|end\s*\{document\})"
    return not (re.search(forbidden, text, re.IGNORECASE) or top_level_tikzpicture(text))


def top_level_tikzpicture(text: str) -> bool:
    """Whether ``text`` opens a tikzpicture outside every brace group (comments and escaped braces aside)."""
    depth = index = 0
    while index < len(text):
        character = text[index]
        if character == "\\":
            if depth == 0 and re.match(r"\\begin\s*\{tikzpicture\}", text[index:index + 40], re.IGNORECASE):
                return True
            index += 2
            continue
        if character == "%":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(0, depth - 1)
        index += 1
    return False


def wrap_latex_header_includes(text: str) -> str:
    """Protect literal YAML header-includes from Pandoc's Markdown parsing.

    A YAML literal block such as ``header-includes: |`` is parsed as Markdown.
    Therefore a LaTeX comment starting with ``%`` can be escaped to ``\\%``.
    Making the scalar a raw LaTeX fenced block preserves preamble commands.
    """
    front_matter = re.match(r"^(---\s*\n)(.*?)(\n(?:---|\.\.\.)\s*(?:\n|$))", text, re.DOTALL)
    if not front_matter:
        return text

    header = front_matter.group(2)
    lines = header.splitlines(keepends=True)
    rewritten: list[str] = []
    index = 0
    changed = False
    while index < len(lines):
        match = re.match(r"^(?P<indent>\s*)header-includes\s*:\s*\|[+-]?\s*(?:#.*)?(?:\r?\n)?$", lines[index])
        if not match:
            rewritten.append(lines[index])
            index += 1
            continue

        base_indent = len(match.group("indent"))
        block_start = index + 1
        index = block_start
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip(" \t")) <= base_indent:
                break
            index += 1
        block = "".join(lines[block_start:index])
        content = dedent(block)
        if re.search(r"(?m)^\s*```\{=latex\}\s*$", content):
            rewritten.extend(lines[block_start - 1:index])
            continue

        newline = "\r\n" if "\r\n" in block else "\n"
        child_indent = match.group("indent") + "  "
        wrapped = f"```{{=latex}}{newline}{content.rstrip()}{newline}```{newline}"
        indented = "".join(child_indent + line if line.strip() else line
                           for line in wrapped.splitlines(keepends=True))
        rewritten.append(lines[block_start - 1])
        rewritten.append(indented)
        changed = True

    if not changed:
        return text
    return front_matter.group(1) + "".join(rewritten) + front_matter.group(3) + text[front_matter.end():]


# Front-matter keys that are not pandoc variables but that a LaTeX package may want (package_latex_keys): each becomes
# \\renewcommand{\\<macro>}{<value>}, appended after the preambles so the preamble can supply a default with \\newcommand.
# A package says which in `<package>-pdfmd.yaml` beside its .sty (`latex-keys:`); until v3.28.37 one package's own
# vocabulary was a table here as well, and is gone: pdfmd names no package.
def package_latex_keys(md_path: Path, metadata_files: list[Path] | None = None,
                       no_auto: list[str] | None = None) -> dict[str, str]:
    """{front-matter key: macro name} the LaTeX packages of the document's preamble (or its metadata's header-includes)
    ask for in their `<package>-pdfmd.yaml` (`latex-keys:`)."""
    keys: dict[str, str] = {}
    for folder, package, _ in core.office_packages(md_path, metadata_files or [], None):
        helper = core.package_helper(folder, package, no_auto, md_path)
        wanted = helper[0].get("latex-keys") if helper else None
        if isinstance(wanted, dict):
            for key, macro in wanted.items():
                name = str(macro).lstrip("\\")
                if re.fullmatch(r"[A-Za-z@]+", name):
                    keys.setdefault(str(key), name)
    return keys


def document_latex_definitions(md_path: Path, metadata_files: list[Path] | None = None,
                               no_auto: list[str] | None = None) -> str:
    """Return \\renewcommand lines for the front-matter keys of the document's packages."""
    lines = []
    for key, macro in package_latex_keys(md_path, metadata_files, no_auto).items():
        value = core.frontmatter_value(md_path, key)
        if value:
            lines.append(f"\\renewcommand{{\\{macro}}}{{{value}}}")
    return "\n".join(lines)


def engine_failure_reason(stderr: str) -> str | None:
    """Pull the single most useful line out of a failed engine's stderr.

    Added 2026-09-17: before this, a failed engine only ever produced a bare
    "WARN ... {engine} failed; trying {next}..." with no hint why -- finding
    the actual cause meant rerunning by hand with --engine {engine} --verbose
    to see the raw LaTeX log, which is real friction for a mistake that's
    often one glance at the log away from obvious (an undefined environment,
    a missing package, a stray unescaped character). A LaTeX fatal error
    always starts its own line with '!' (e.g. '! LaTeX Error: ...'); Pandoc's
    own errors are usually 'Error producing PDF.' or 'pandoc: ...'. Preferring
    those over the raw tail keeps the one-line summary meaningful instead of
    a trailing context line like 'l.612 ...' or a blank line. Returns None
    for empty/whitespace-only stderr (nothing useful to show).
    """
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("!"):
            return line
    for line in lines:
        if line.startswith(("Error", "pandoc:", "pandoc.exe:")):
            return line
    return lines[-1] if lines else None


# Pandoc's exit code for a command line it refuses (PandocOptionError): an unknown option, one without its argument, a value it
# does not take. A fact of Pandoc's, not a setting.
PANDOC_OPTION_ERROR = 6


def pandoc_refused_command(result: subprocess.CompletedProcess) -> bool:
    """True when Pandoc stopped on its own command line, before any engine ran (`pdfmd doc.md --no-such-flag`): the next
    engine gets the same options and would fail the same way. A refused `--pdf-engine` value is the exception (an older
    Pandoc that does not know this engine): the next engine may be one it knows. An unknown option is never that, even
    one whose name starts with it (`--pdf-engines`)."""
    stderr = result.stderr or ""
    return result.returncode == PANDOC_OPTION_ERROR and ("Unknown option" in stderr or "--pdf-engine" not in stderr)


# What a failed TeX run's text says about WHY, for the causes whose log signature is known (signatures from
# real logs: a missing luaotfload, a missing package, a corrupt font database, an unwritable cache). First match wins.
TEX_CAUSES = (
    (r"no\s+writeable\s+cache\s+path", "the TeX cache folder is not writable",
     "set TEXMFVAR and TEXMFCACHE to a folder you can write to"),
    (r"luaotfload-database\.lua:\d+: \[string", "the LuaTeX font database is corrupt",
     "run `luaotfload-tool --update --force`, or delete the luatex-cache folders"),
    (r"module 'luaotfload-main' not found|not loadable: metric d", "the LuaTeX font loader (luaotfload) is missing",
     "install it (tlmgr install luaotfload; Debian/Ubuntu: apt install texlive-luatex), or use -e xelatex"),
    (r"File `([^']+\.sty)' not found", "the LaTeX package {0} is missing", None),
)
TEX_PACKAGES = {"lmodern.sty": ("lmodern", "lmodern"), "soul.sty": ("soul", "texlive-plain-generic"),
                "selnolig.sty": ("selnolig", "texlive-luatex"), "lua-ul.sty": ("lua-ul", "texlive-luatex"),
                "luacolor.sty": ("luacolor", "texlive-luatex")}


def tex_failure_cause(text: str) -> tuple[str, str] | None:
    """(cause, fix) for a failed TeX run whose text matches a known signature, else None."""
    for pattern, cause, fix in TEX_CAUSES:
        found = re.search(pattern, text)
        if not found:
            continue
        if fix is None:                                                  # a missing .sty: name the package that has it
            style = found.group(1)
            tl, distro = TEX_PACKAGES.get(style, (style.removesuffix(".sty"), None))
            fix = f"install it (tlmgr install {tl}" + (f"; Debian/Ubuntu: apt install {distro})" if distro else ")")
            return cause.format(style), fix
        return cause, fix
    return None


# Direct .tex compilation (v3.1.0): a real .tex input -- already a complete,
# independently compilable document with its own \documentclass/preamble --
# used to be handed to Pandoc anyway, which reads it with Pandoc's LaTeX
# reader and regenerates it through Pandoc's LaTeX writer before an engine
# ever sees it. That round-trip is lossy for exactly the raw LaTeX a .tex
# input is likely to contain on purpose (chemfig, tikz, custom macros) --
# see CHANGELOG-pdfmd.md v3.1.0. compile_tex_direct() instead runs a LaTeX
# engine straight on the file, handles the rerun-for-cross-references and
# bibtex/biber passes by hand (mirroring what latexmk already does
# internally for the two engines -- latexmk/tectonic -- that manage this
# themselves), and cleans up after itself the way tectonic always has:
# every engine writes into a scratch -output-directory, and only the
# finished PDF is copied back out, so the source directory is never left
# holding .aux/.log/.out/etc. --keep-aux (KEEP_AUX below) turns this off
# and restores the old in-place-with-leftovers behavior, for when a failed
# or suspicious compile needs its .log inspected by hand.
#
# Not attempted for "context": ConTeXt's CLI and markup are unrelated to
# the other five LATEX_ENGINES members, and a hand-written raw .tex file
# targeting it is not a realistic case this needs to cover.
MAX_TEX_DIRECT_PASSES = 5
TEX_RERUN_TRIGGERS = ("Rerun to get", "Please rerun LaTeX", "Rerun LaTeX")
# texmf.cnf's own max_print_line default -- see tex_log_dewrap()'s docstring.
TEX_LOG_WRAP_WIDTH = 79


def tex_wants_rerun(log_text: str) -> bool:
    """Whether a LaTeX engine's own .log is asking for another pass.

    Covers the standard hyperref/natbib/label-tracking messages
    (TEX_RERUN_TRIGGERS) -- the same signal latexmk itself watches for.
    """
    return any(trigger in log_text for trigger in TEX_RERUN_TRIGGERS)


def tex_log_dewrap(text: str, width: int = TEX_LOG_WRAP_WIDTH) -> str:
    """Undo a LaTeX engine's own hard line-wrap in its .log, mid-word,
    at ~max_print_line columns -- confirmed on this machine (kpsewhich
    -var-value=max_print_line) at 79, observed wrapping at 80 in
    practice. Any physical line at or past ``width`` is assumed
    continued verbatim (no space added) on the next; a real short
    line ends a logical line. Needed before any pattern match against
    the log: without it, a single sentence like "Fatal error occurred,
    no output PDF file produced!" is split across two physical lines
    with the break landing mid-word, and naive last-line/regex
    matching returns only the truncated tail (caught the hard way, by
    reading an actual failed compile's captured reason rather than
    trusting a clean synthetic one -- see CHANGELOG-pdfmd.md v3.1.0).
    """
    lines = text.split("\n")
    joined: list[str] = []
    buffer = ""
    for line in lines:
        buffer += line
        if len(line) >= width:
            continue
        joined.append(buffer)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return "\n".join(joined)


def tex_log_failure_reason(log_text: str) -> str | None:
    """Pull the single most useful line out of a failed direct-.tex compile.

    Dewraps first (see tex_log_dewrap), then prefers a classic ``! ...``
    LaTeX error line same as engine_failure_reason(); falls back to a
    ``-file-line-error``-style ``path:line: message`` line (used here
    since it names the offending source line directly), skipping the
    generic ``... Fatal error occurred, no output PDF file produced!``
    trailer every halted run ends with, which names no actual cause.
    """
    lines = [line.strip() for line in tex_log_dewrap(log_text).splitlines() if line.strip()]
    for line in lines:
        if line.startswith("!"):
            return line
    for line in lines:
        match = re.match(r".+:\d+:\s+(.+)", line)
        if match and "Fatal error occurred" not in line:
            return match.group(1)
    return lines[-1] if lines else None


def tex_bibliography_tool(text: str) -> str | None:
    """Detect which bibliography processor a raw .tex document needs, if any.

    biblatex (``\\usepackage{biblatex}``/``\\addbibresource``) is processed
    by biber; the older bibtex/natbib style (bare ``\\bibliography{...}``)
    by bibtex. Returns None for a document with no bibliography at all.
    """
    if re.search(r"\\addbibresource\{|\\usepackage(?:\[[^\]]*\])?\{biblatex\}", text):
        return "biber"
    if re.search(r"\\bibliography\{", text):
        return "bibtex"
    return None


def latex_engine_command(engine: str, tex_path: Path, output_dir: Path, search_folders: list[str] | None = None) -> list[str] | None:
    """Build one direct-compile pass's command line for ``engine``.

    lualatex/xelatex/pdflatex share an identical CLI shape and are run
    through compile_tex_direct's own manual rerun/bibliography loop.
    latexmk and tectonic already manage multi-pass compilation and
    bibtex/biber internally, so each gets a single wrapped call instead.
    Returns None for anything else (namely "context" -- see the module-
    level comment above compile_tex_direct).
    """
    if engine in {"lualatex", "xelatex", "pdflatex"}:
        return [engine, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                f"-output-directory={core.tex_argument(output_dir)}", core.tex_argument(tex_path)]
    if engine == "latexmk":
        return ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                f"-output-directory={core.tex_argument(output_dir)}", core.tex_argument(tex_path)]
    if engine == "tectonic":
        return ["tectonic", *[f"-Zsearch-path={folder}" for folder in search_folders or []],
                "-o", core.tex_argument(output_dir), core.tex_argument(tex_path)]
    return None


def run_tex_engine(engine: str, tex_path: Path, output_dir: Path,
                    verbose: bool, cwd: Path | None = None,
                    env: dict | None = None) -> tuple[bool, str]:
    """Run ``engine`` on ``tex_path`` to completion, output landing in
    ``output_dir``. Returns (success, one-line failure reason -- empty on
    success). Always run with cwd=tex_path.parent, so a raw \\input/
    \\includegraphics/\\bibliography relative path beside the source keeps
    resolving; only *output* is redirected via -output-directory/-o. ``cwd``
    and ``env`` override that for a .tex generated elsewhere from Markdown
    (the cache route): cwd is then Pandoc's own working directory and env
    carries TEXINPUTS, exactly as the Pandoc-run engine would have had.
    """
    work_dir = cwd or tex_path.parent
    log_path = output_dir / f"{tex_path.stem}.log"

    def log_text() -> str:
        return log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
        core.log_cmd(cmd, cwd, verbose)
        return subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd, env=env)

    engine_env = env
    cmd = latex_engine_command(engine, tex_path, output_dir,
                               [folder for folder in (engine_env or {}).get(core.TECTONIC_SEARCH_ENV, "").split(os.pathsep) if folder])
    if cmd is None:
        return False, f"{engine} is not supported for direct .tex compilation"

    if engine in ("latexmk", "tectonic"):
        # Both already handle reruns and bibtex/biber internally.
        result = run(cmd, work_dir, env=engine_env)
        if result.returncode != 0 or not (output_dir / f"{tex_path.stem}.pdf").exists():
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""
        return True, ""

    result = run(cmd, work_dir, env=engine_env)
    if result.returncode != 0:
        return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""

    bib_tool = tex_bibliography_tool(tex_path.read_text(encoding="utf-8-sig"))
    if bib_tool:
        # Run WITH cwd=output_dir (the .aux/.bcf's own directory), not
        # tex_path.parent: bibtex (and, defensively, biber too) is
        # subject to TeX's own "openout_any" file-writing security
        # policy, which -- at MacTeX's paranoid default -- refuses to
        # write a .bbl/.blg anywhere outside the current directory tree.
        # Pointing bibtex at a scratch -output-directory while running
        # it from the source directory silently tripped exactly that
        # check (caught by actually inspecting the rendered PDF's
        # citation, not just the exit code -- bibtex still printed a
        # "Not writing to ..." warning and returned nonzero, but the
        # compile otherwise looked like it had succeeded). BIBINPUTS
        # points bibtex back at the source directory to find the .bib
        # file, since it has no --input-directory flag of its own.
        bib_env = (engine_env or os.environ).copy()
        bib_env["BIBINPUTS"] = f"{work_dir}{os.pathsep}{tex_path.parent}{os.pathsep}{bib_env.get('BIBINPUTS', '')}"
        bib_cmd = (["biber", f"--input-directory={work_dir}", tex_path.stem] if bib_tool == "biber"
                   else ["bibtex", tex_path.stem])
        bib_result = run(bib_cmd, output_dir, env=bib_env)
        if bib_result.returncode != 0:
            print(f"WARN  {tex_path}: {bib_tool} reported errors; continuing"
                  + (f" ({bib_result.stderr.strip().splitlines()[-1]})" if bib_result.stderr.strip() else ""),
                  file=sys.stderr)
        result = run(cmd, work_dir, env=engine_env)
        if result.returncode != 0:
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""

    passes = 1
    while tex_wants_rerun(log_text()) and passes < MAX_TEX_DIRECT_PASSES:
        result = run(cmd, work_dir, env=engine_env)
        passes += 1
        if result.returncode != 0:
            return False, result.stderr.strip() or tex_log_failure_reason(log_text()) or ""
    # every run of the engine: `passes` starts at the run after bibtex/biber, so the one before it is added (v3.33.47)
    core.vprint(verbose, f"AUTO TEXDIRECT  {tex_path}: {engine}, {passes + (1 if bib_tool else 0)} pass(es)"
          + (f" + {bib_tool}" if bib_tool else ""))
    return True, ""


PLOT_CTX_TWICE = "@@runs=2@@"   # in the plain part: the job runs twice (positions a picture remembers)
PLOT_CTX_MARGIN = re.compile(r"@@margin=([0-9.]+(?:pt|bp|mm|cm|in|em|ex))@@")   # the page is the box plus this on every side (ink that overflows the box)
PLOT_CTX_PLAIN = "@@plain@@"   # in a request's context: what follows is TeX with ordinary catcodes


@lru_cache(maxsize=None)
def tex_tree_stamp() -> str:
    """When TeX Live's packages last changed: `tlmgr` rewrites its package database
    (tlpkg/texlive.tlpdb) on every install, update and removal, and the engine's
    version line names only the year. Empty elsewhere (MiKTeX, no kpsewhich)."""
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich:
        return ""
    try:
        done = core.run_probe([kpsewhich, "-var-value", "TEXMFROOT"])
        root = done.stdout.strip() if done else ""
        stat = (Path(root) / "tlpkg" / "texlive.tlpdb").stat() if root else None
    except OSError:
        return ""
    return f"{stat.st_size}:{stat.st_mtime_ns}" if stat else ""


def plot_preamble(preamble: str, own_headers: list[str]) -> str:
    """The preamble plots are keyed by and drawn with: the document's, without the
    headers pdfmd adds to one build only (a part's label replay, which names a
    temporary file; the counter markers). They draw nothing, and left in, every
    part built alone had a plot directory of its own."""
    for text in own_headers:
        text = text.strip()
        if text:                       # Pandoc writes a header's lines, then one newline
            preamble = preamble.replace(text + "\n", "") if text + "\n" in preamble else preamble.replace(text, "")
    return preamble


def plot_recorded_inputs(fls: Path, roots: list[Path]) -> dict[str, str]:
    """The user's own files a standalone plot job read (LaTeX -recorder), with
    their content hashes -- anything under the report's folders and the user's
    own TeX trees, nothing from TeX Live's (its package database is in the
    directory's key), nothing of the job's own."""
    found: dict[str, str] = {}
    try:
        lines = fls.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return found
    base = roots[0]
    for line in lines:
        if not line.startswith("INPUT "):
            continue
        candidate = Path(os.path.abspath(base / line[6:].strip()))
        if candidate.suffix in (".aux", ".fls") or not candidate.is_file():
            continue
        if candidate.parent == Path(os.path.abspath(fls.parent)):
            # the job's own .tex, deleted once it has run: a cache beside the document (`location: document`) is
            # under the report's folder, and recording it dropped every entry at the next build
            continue
        # normcase: TeX writes a Windows drive letter in lower case (d:/work/...) where the root is D:\work, and a
        # file it read under the report's folder was dropped as foreign, so a CSV edit showed as a stale plot
        if any(os.path.normcase(str(candidate)).startswith(os.path.normcase(str(root)) + os.sep) for root in roots):
            digest = core.sha1_file(candidate)
            if digest:
                found[str(candidate)] = digest
    return found


@_timed("plots")
def render_plot_requests(requests: dict[str, tuple[str, str, str]], plot_dir: Path, preamble: str,
                         engine: str, cwd: Path, env: dict | None, roots: list[Path],
                         verbose: bool, aliases: dict[str, list[str]] | None = None) -> tuple[int, int]:
    """Render each request not already stored; returns (rendered, failed). ``aliases``: the names a package gave the
    protocol's (cache_aliases): its render macro is defined and its box sizes written under them too."""
    aliases = aliases or {}
    import json
    from concurrent.futures import ThreadPoolExecutor
    todo = {key: value for key, value in requests.items()
            if not (plot_dir / f"{key}.dim").exists()}
    if not todo:
        return 0, 0

    def render(item) -> bool:
        key, (macro, args, ctx) = item
        job = plot_dir / f"r-{key}.tex"
        dim = plot_dir / f"r-{key}.dim"      # renamed to {key}.dim LAST: the commit marker
        ctx, _, plain = ctx.partition(PLOT_CTX_PLAIN)       # a scheme's settings need spaces kept: read outside expl3's catcodes
        passes = 2 if PLOT_CTX_TWICE in plain else 1       # a picture whose arrows point at its own nodes is typeset twice
        plain = plain.replace(PLOT_CTX_TWICE, "")
        found_margin = PLOT_CTX_MARGIN.search(plain)
        margin = found_margin.group(1) if found_margin else "0pt"
        plain = PLOT_CTX_MARGIN.sub("", plain)
        job.write_text(
            "\\def\\pdfmdCacheRender{}" + "".join(f"\\def\\{name}{{}}" for name in aliases.get("render", [])) + "\n" + preamble + "\\begin{document}\\makeatletter\n"
            "\\pagestyle{empty}\n\\ExplSyntaxOn\n" + ctx + "\n\\ExplSyntaxOff\n" + plain + "\n"
            "\\setbox\\z@\\hbox{" + macro + args + "}\n"
            "\\newwrite\\dimf\\immediate\\openout\\dimf=" + dim.name + "\n"
            "\\immediate\\write\\dimf{" + "".join(
                f"\\string\\gdef\\string\\{name}{{\\the\\{box}\\z@}}"
                for box, neutral in (("wd", "pdfmdCacheWd"), ("ht", "pdfmdCacheHt"), ("dp", "pdfmdCacheDp"))
                for name in (neutral, *aliases.get(box, []))) + "}\n"
            f"\\immediate\\write\\dimf{{\\string\\gdef\\string\\pdfmdCacheMargin{{{margin}}}}}\n"
            "\\ifdefined\\pdfmdCachePost\\immediate\\write\\dimf{\\string\\gdef\\string\\pdfmdCachePostStored"
            "{\\unexpanded\\expandafter{\\pdfmdCachePost}}}\\fi\n"
            "\\immediate\\closeout\\dimf\n"
            + (f"\\pagewidth=\\dimexpr\\wd\\z@+2\\dimexpr{margin}\\relax \\pageheight=\\dimexpr\\ht\\z@+\\dp\\z@+2\\dimexpr{margin}\\relax\n"
               if margin != "0pt" else "\\pagewidth=\\wd\\z@ \\pageheight=\\dimexpr\\ht\\z@+\\dp\\z@\\relax\n") +
            "\\hoffset=-1in \\voffset=-1in\n"
            "\\ifdefined\\ClearShipoutPictureBG\\ClearShipoutPictureBG\\fi\\ifdefined\\ClearShipoutPictureFG\\ClearShipoutPictureFG\\fi\n"
            + (f"\\shipout\\vbox{{\\kern{margin}\\hbox{{\\kern{margin}\\box\\z@\\kern{margin}}}\\kern{margin}}}\n"
               if margin != "0pt" else "\\shipout\\hbox{\\box\\z@}\n") + "\\end{document}\n", encoding="utf-8")
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", "-recorder",
               f"-output-directory={core.tex_argument(plot_dir)}", core.tex_argument(job)]
        core.log_cmd(cmd, cwd, verbose)
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd, env=env)
        for _ in range(passes - 1):
            if result.returncode != 0:
                break
            result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd, env=env)
        produced = plot_dir / f"r-{key}.pdf"
        ok = result.returncode == 0 and produced.exists() and dim.exists()
        if ok:
            produced.replace(plot_dir / f"{key}.pdf")
            (plot_dir / f"{key}.deps").write_text(
                json.dumps({**plot_recorded_inputs(plot_dir / f"r-{key}.fls", roots),
                            "__roots__": [str(root) for root in roots]}), encoding="utf-8")
            dim.replace(plot_dir / f"{key}.dim")
        else:
            for suffix in (".dim", ".pdf", ".deps"):
                (plot_dir / f"{key}{suffix}").unlink(missing_ok=True)
            core.vprint(verbose, f"AUTO CACHE  plot {key[:8]} failed to render: "
                  + (tex_log_failure_reason(result.stdout) or result.stdout[-300:].strip()))
        for leftover in plot_dir.glob(f"r-{key}.*"):
            leftover.unlink(missing_ok=True)
        return ok

    workers = max(1, min(4, os.cpu_count() or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(render, todo.items()))
    return sum(results), len(results) - sum(results)


AUX_CLEAN_SUFFIXES = (".aux", ".toc", ".out", ".lof", ".lot", ".bbl", ".blg", ".bcf", ".run.xml",
                      ".fls", ".fdb_latexmk", ".log", ".pdf")


@_timed("LaTeX (direct)")
def compile_tex_direct(tex_path: Path, output: Path, engines: list[str],
                       keep_aux: bool, verbose: bool, debug: bool,
                       aux_dir: Path | None = None, cwd: Path | None = None,
                       env: dict | None = None) -> tuple[bool, str]:
    """Compile a standalone .tex document directly, without Pandoc.

    See the module-level comment above for why, and this file's docstring
    ("Input formats") for the user-facing summary. ``engines`` is the
    already-resolved fallback chain (from select_engines/resolve_engines);
    only its LATEX_ENGINES members other than "context" are usable here --
    a chain left with none (e.g. a document/metadata pdf-engine restricted
    to the "html" family) is reported as a failure rather than silently
    falling back to the old, lossier Pandoc round-trip.
    """
    tex_engines = [engine for engine in engines if engine in core.LATEX_ENGINES and engine != "context"]
    if not tex_engines:
        return False, (f"{tex_path}: no LaTeX engine available for direct .tex compilation "
                       "(need one of lualatex/xelatex/pdflatex/latexmk/tectonic)")

    failed_families: set[str] = set()
    failed_engines: list[str] = []
    last_reason = ""
    for engine_index, engine in enumerate(tex_engines):
        log_tail = ""
        family = core.ENGINE_FAMILY.get(engine, engine)
        if family in failed_families:
            print(f"SKIP  {tex_path}: {engine} shares the {family} engine with an earlier "
                  f"failure; skipping", file=sys.stderr)
            continue
        # aux_dir: a persistent directory (the cache route) -- LaTeX's own
        # .aux/.toc/.out survive between builds, so an unchanged document
        # settles in one pass instead of two or three. Never discarded here.
        scratch = None if (keep_aux or aux_dir) else Path(mkdtemp(prefix="pdfmd-tex-"))
        output_dir = aux_dir if aux_dir else (tex_path.parent if scratch is None else scratch)
        # --keep-aux compiles in place: TeX opens the PDF itself and removes it when it stops, so the PDF already there
        # is kept aside for the run and put back when it fails (v3.33.71: a stopped build leaves the old PDF as it was)
        in_place = output_dir / f"{tex_path.stem}.pdf"
        kept, ok = None, False
        if scratch is None and not aux_dir and in_place.is_file():
            handle, name = mkstemp(prefix=f".{tex_path.stem}.pdfmd-kept-", suffix=".pdf", dir=output_dir)   # beside it: os.replace
            os.close(handle)
            kept = Path(name)
            shutil.copy2(in_place, kept)
        try:
            ok, reason = run_tex_engine(engine, tex_path, output_dir, verbose, cwd=cwd, env=env)
            if not ok and aux_dir:
                # A poisoned cache (a half-written .aux from an interrupted or
                # failed build) must never trap the user: wipe LaTeX's own
                # files for this document and retry once from scratch.
                for leftover in output_dir.glob(f"{tex_path.stem}.*"):
                    if leftover.name.endswith(AUX_CLEAN_SUFFIXES):
                        leftover.unlink(missing_ok=True)
                core.vprint(verbose, f"AUTO CACHE  {tex_path.stem}: first attempt failed; retrying with a clean aux")
                ok, reason = run_tex_engine(engine, tex_path, output_dir, verbose, cwd=cwd, env=env)
            if ok:
                produced = output_dir / f"{tex_path.stem}.pdf"
                output.parent.mkdir(parents=True, exist_ok=True)
                # --keep-aux compiles straight into tex_path.parent, so
                # ``produced`` and ``output`` are the same file whenever
                # no -o/--out redirected the output elsewhere -- shutil
                # refuses to "copy" a file onto itself.
                if produced.resolve() != output.resolve():
                    shutil.copy2(produced, output)
                where = ("in place (--keep-aux)" if keep_aux else
                         f"in the cache {output_dir}" if aux_dir else "in a scratch directory, then discarded")
                core.vprint(verbose, f"AUTO TEXDIRECT  {tex_path}: compiled with {engine} {where}")
                core.record_engine(engine, failed_engines)
                return True, ""
            last_reason = reason
            try:              # the log says whether the document or the engine failed (pdfmd_chain.failure_kind)
                log_tail = (output_dir / f"{tex_path.stem}.log").read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        finally:
            if kept is not None:
                if not ok:
                    os.replace(kept, in_place)
                else:
                    kept.unlink(missing_ok=True)
            if scratch is not None:
                shutil.rmtree(scratch, ignore_errors=True)
        failed_families.add(family)
        failed_engines.append(engine)
        remaining = [e for e in tex_engines[engine_index + 1:] if core.ENGINE_FAMILY.get(e, e) not in failed_families]
        fake_result = subprocess.CompletedProcess(args=[engine], returncode=1, stdout=log_tail, stderr=last_reason)
        if core.pdfmd_chain.engine_failed(str(tex_path), engine, fake_result, remaining, debug):   # engine-fallback (v3.33.71)
            break
    return False, last_reason

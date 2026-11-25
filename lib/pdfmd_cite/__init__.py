"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_cite`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from tempfile import mkstemp

from pdfmd_base import core

from pdfmd_base import pandoc_run
from pdfmd_cite.aliases import apply as apply_citation_aliases


# pdfmd-options.citation-engine: "citeproc" (the default -- a document only
# needs this key at all to opt into something else), "natbib", or
# "biblatex". Routes a LaTeX-family PDF target's (or --to latex/beamer/
# context's) bibliography through Pandoc's own --natbib/--biblatex flags
# (native biber/bibtex, handled by the engine's own bibliography tooling)
# instead of --citeproc (which renders citations into the LaTeX Pandoc
# generates directly, using a CSL style, and never touches biber/bibtex at
# all). Meaningless for a non-LaTeX target (HTML/typst/docx/office) --
# silently ignored there, same as e.g. LaTeX-only geometry/monofont
# defaults already are. See convert_via_native_bibliography()'s own
# docstring for the real complication this runs into for a PDF target
# specifically: confirmed empirically that Pandoc's own PDF-making
# pipeline, when it calls a LaTeX engine directly via --pdf-engine=, never
# actually runs bibtex/biber itself (only --pdf-engine=latexmk does, since
# latexmk manages that on its own) -- lualatex/xelatex/pdflatex all leave
# citations undefined with a bare --natbib/--biblatex. Routed around by
# generating a complete standalone .tex via Pandoc first (same as the
# TEX_STANDALONE_FORMATS branch already does for --to latex), then handing
# it to compile_tex_direct()'s own engine+bibtex/biber rerun loop instead
# of letting Pandoc invoke the engine itself.
CITATION_ENGINES = frozenset({"citeproc", "natbib", "biblatex"})


def frontmatter_citation_engine(md_path: Path, metadata_files: list[Path] = ()) -> str | None:
    """Read pdfmd-options.citation-engine -- see the module comment above.

    Document's own front matter wins over a linked metadata file's,
    checked in the same metadata_files order as frontmatter_engine(), same
    precedence rule. No legacy bare-top-level spelling to support here
    (unlike pdf-engine/engine) -- this is a brand new key with no existing
    documents written against an older spelling.
    """
    options = core.frontmatter_pdfmd_options(md_path)
    value = options.get("citation-engine")
    if value is not None:
        return str(value).casefold()
    for metadata_file in core.metadata_files_by_priority(metadata_files):
        data = core.metadata_file_yaml(metadata_file)
        options = data.get("pdfmd-options")
        value = options.get("citation-engine") if isinstance(options, dict) else None
        if value is not None:
            return str(value).casefold()
    value = core.config_options(md_path).get("citation-engine")
    return str(value).casefold() if value is not None else None


CSL_FALLBACKS = ("default", "error")


CSL_FETCH_DAYS = 30


CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")


def open_url(request, timeout: float):
    """urllib's urlopen, and once more with the system's CA bundle (else certifi's) when this Python has no certificates
    of its own: a python.org Python on macOS has none until its "Install Certificates" step runs, and every https fetch
    failed with CERTIFICATE_VERIFY_FAILED (v3.27.27; found fetching a csl: style)."""
    import ssl, urllib.error, urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as error:
        if not isinstance(getattr(error, "reason", None), ssl.SSLCertVerificationError):
            raise
        cafile = next((path for path in CA_BUNDLES if os.path.isfile(path)), None)
        if cafile is None:
            try:
                import certifi
                cafile = certifi.where()
            except ImportError:
                raise error from None
        return urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context(cafile=cafile))


def document_csl(sources: list[Path], metadata_files: list[Path]) -> str | None:
    """The document's CSL file, including the pdfmd-options alias."""
    from pdfmd_bibliography import csl_option

    alias, _ = csl_option(Path(sources[0]), metadata_files) if sources else (None, None)
    return alias or root_csl(sources, metadata_files)


def root_csl(sources: list[Path], metadata_files: list[Path]) -> str | None:
    """The `csl:` Pandoc takes from the files: the last source's front matter, else the winning metadata file's."""
    for source in reversed(sources):
        value = core.front_matter_dict(core.read_text_best_effort(Path(source))).get("csl")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for path in core.metadata_files_by_priority(metadata_files):
        value = core.metadata_file_yaml(path).get("csl")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def csl_fallback(md_path: Path, metadata_files: list[Path]) -> str:
    """`pdfmd-options.csl-fallback`: default (Pandoc's default style, with a WARN) or error."""
    value = core.first_pdfmd_option(md_path, metadata_files, "csl-fallback")
    mode = str(value).strip().casefold() if value is not None else "default"
    if mode not in CSL_FALLBACKS:
        raise SystemExit(f"{md_path}: unknown csl-fallback value {value!r}. Valid: {', '.join(CSL_FALLBACKS)}")
    return mode


def fetch_csl(url: str) -> tuple[str | None, str]:
    """(the style's text, "") or (None, why)."""
    import urllib.error, urllib.request  # here, not at the top: only this needs it (start-up time, v3.32.55)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": f"pdfmd/{core.PDFMD_VERSION}"})
        with open_url(request, 20) as response:
            data = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return None, f"{error.code} {error.reason}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        return None, str(getattr(error, "reason", error)) or type(error).__name__
    text = data.decode("utf-8", errors="replace")
    if "<style" not in text[:4000]:
        return None, "what it sent is not a CSL style"
    return text, ""


def remote_csl(url: str, md_path: Path, metadata_files: list[Path]) -> Path | None:
    """The local file for a `csl:` URL (see above); None leaves the URL to Pandoc."""
    name = Path(urllib.parse.urlparse(url).path).name or "style.csl"
    name = name if name.lower().endswith(".csl") else name + ".csl"
    folder = core.cache_root() / "csl"
    cached = folder / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}-{name}"
    if cached.is_file() and time.time() - cached.stat().st_mtime < CSL_FETCH_DAYS * 86400:
        return cached
    text, why = core.fetch_csl(url)
    if text is not None:
        folder.mkdir(parents=True, exist_ok=True)
        core.atomic_write_text(cached, text)
        print(f"AUTO CSL   {url} -> {core.display_path(cached)}")
        return cached
    if cached.is_file():
        when = time.strftime("%Y-%m-%d", time.localtime(cached.stat().st_mtime))
        print(f"NOTE  {core.display_path(md_path)}: {url} could not be fetched ({why}); using the copy fetched on {when}")
        return cached
    data_dir = core.pandoc_user_data_dir()
    own = next((place / name for place in ((data_dir / "csl", data_dir) if data_dir else ()) if (place / name).is_file()),
               None)
    if own is not None:
        print(f"WARN  {core.display_path(md_path)}: {url} could not be fetched ({why}); using Pandoc's own "
              f"{core.display_path(own)} instead", file=sys.stderr)
        return own
    if csl_fallback(md_path, metadata_files) == "error":
        raise SystemExit(f"{core.display_path(md_path)}: the citation style {url} could not be fetched ({why}), and Pandoc's "
                         f"csl/ folder has no {name} (pdfmd-options: {{csl-fallback: error}})")
    default = folder / "pandoc-default.csl"
    if not default.is_file():
        try:
            done = pandoc_run(["pandoc", "--print-default-data-file", "default.csl"], capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=60)
        except (OSError, subprocess.SubprocessError):
            done = None
        if done is None or done.returncode != 0 or "<style" not in done.stdout:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        core.atomic_write_text(default, done.stdout)
    print(f"WARN  {core.display_path(md_path)}: {url} could not be fetched ({why}) and Pandoc's csl/ folder has no {name}; "
          "the citations use Pandoc's default style (Chicago author-date). pdfmd-options: {csl-fallback: error} stops "
          "instead", file=sys.stderr)
    return default


def csl_args(sources: list[Path], metadata_files: list[Path], pandoc_options: list[str],
             no_auto: list[str] | None, *, citeproc: bool = True) -> list[str]:
    """Select a plain path for the pdfmd-options alias or a remotely cached CSL style."""
    from pdfmd_args import metadata_command_layers
    from pdfmd_bibliography import csl_option

    if not sources:
        return []
    source = Path(sources[0])
    alias, _ = csl_option(source, metadata_files)
    options = pandoc_options[:pandoc_options.index("--")] if "--" in pandoc_options else pandoc_options
    cli = None
    tokens = iter(options)
    for option in tokens:
        if option == "--csl":
            cli = next(tokens, "")
        elif option.startswith("--csl="):
            cli = option.partition("=")[2]
        elif option in ("-M", "--metadata", "-V", "--variable"):
            next(tokens, None)
    metadata, _ = metadata_command_layers(options)[0]
    cli_metadata = metadata.get("csl")
    root = root_csl(sources, metadata_files)
    choices = [(key, value) for key, value in (("--csl", cli), ("command-line csl metadata", cli_metadata),
                                               ("pdfmd-options.csl", alias), ("root csl", root))
               if isinstance(value, str) and value]
    if len(choices) > 1:
        from pdfmd_bibliography.sources import locate, resource_folders

        folders = resource_folders([Path(item) for item in sources], metadata_files)

        def identity(path: str) -> Path | str:
            if re.match(r"^https?://", path, re.I):
                return path
            try:
                return locate(path, folders).resolve()
            except (OSError, RuntimeError, ValueError):
                return path

        key, value = choices[0]
        winner = identity(value)
        conflicts = [f"{other_key} {other!r}" for other_key, other in choices[1:]
                     if identity(other) != winner]
        if conflicts:
            print(f"WARN  {core.display_path(source)}: {key} {value!r} overrides {', '.join(conflicts)}", file=sys.stderr)
    if cli is not None or "csl" in metadata:
        return []
    value = alias or root
    if citeproc and value and re.match(r"^https?://", value, re.I) and not core.auto_disabled(no_auto, "remotecsl"):
        local = remote_csl(value, source, metadata_files)
        if local is not None:
            return ["--csl", str(local)]
    return ["--csl", alias] if alias is not None else []


BIB_ENTRY_START_RE = re.compile(r"^[ \t]*@[ \t]*([A-Za-z]+)[ \t]*([{(])", re.MULTILINE)


def bib_entry_end(text: str, opener_index: int) -> int | None:
    """The index just past the entry whose opening `{` or `(` is at ``opener_index``, or None."""
    opener = text[opener_index]
    closer = "}" if opener == "{" else ")"
    depth = 0
    position = opener_index
    while position < len(text):
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return position + 1
        position += 1
    return None


def parse_bibliography(text: str) -> tuple[list[dict], str]:
    """The entries of a BibTeX/BibLaTeX file -- {kind, key, text, gap} with ``gap`` the
    text between the previous entry and this one -- and the text after the last."""
    items: list[dict] = []
    position = previous = 0
    while True:
        match = BIB_ENTRY_START_RE.search(text, position)
        if match is None:
            break
        end = bib_entry_end(text, match.end() - 1)
        if end is None:
            position = match.end()
            continue
        kind = match.group(1).lower()
        key = (text[match.end():end - 1].split(",", 1)[0].strip() if kind not in ("string", "preamble", "comment")
               else None)
        start = text.index("@", match.start())
        items.append({"kind": kind, "key": key, "text": text[start:end], "gap": text[previous:start]})
        previous = position = end
    return items, text[previous:]


def convert_via_native_bibliography(md_path: Path, output: Path, effective_from: str | None,
                                    metadata_files: list[Path], variables: list[str],
                                    pandoc_options: list[str], lua_filters: list[Path],
                                    preamble_files: list[Path], title_source: Path,
                                    pdf_meta_snippet_text: str | None, citation_engine: str,
                                    presentation: bool, slide_level: int | None, shift_heading: bool,
                                    font: str, document_font: bool, mainfont_auto: bool,
                                    geometry_needed: bool, monofont_needed: bool,
                                    tablewidth_auto: bool, width_filter: Path, csv_filter: Path,
                                    no_auto: list[str] | None, engines: list[str], keep_aux: bool,
                                    verbose: bool, debug: bool, named_reader=None, before_citeproc=()) -> tuple[bool, str]:
    """Route a PDF compile's bibliography through Pandoc's own --natbib/
    --biblatex instead of --citeproc, for pdfmd-options.citation-engine.

    Not as simple as adding --natbib/--biblatex next to the usual
    --pdf-engine=<engine> pandoc invocation: confirmed empirically (a real
    document, `pandoc ... --pdf-engine=lualatex --natbib`) that Pandoc's
    own PDF-making pipeline never runs bibtex/biber at all when it invokes
    a LaTeX engine directly this way -- citations come out undefined
    ("Citing ? here.") regardless of engine, EXCEPT --pdf-engine=latexmk,
    since latexmk is the one engine in the chain that manages bibtex/biber
    itself. Rather than restrict this feature to latexmk only, this
    generates a complete standalone .tex via Pandoc first (mirroring
    convert_one's own TEX_STANDALONE_FORMATS branch, just always writing
    to a scratch file instead of the real --to latex output) and hands it
    to compile_tex_direct() -- which already runs exactly the
    rerun-until-stable + automatic bibtex/biber loop this needs, for
    ANY of lualatex/xelatex/pdflatex/latexmk/tectonic, not just latexmk.
    No missing-glyph mainfont retry here, for the same reason
    TEX_STANDALONE_FORMATS doesn't have one either: that needs an actual
    compile's output to react to, and by the time compile_tex_direct runs,
    this function itself is done inspecting anything Pandoc produced.
    """
    # The intermediate .tex has to live NEXT TO md_path, not in an unrelated
    # scratch directory: compile_tex_direct() (and, before that, bibtex/
    # biber) run with cwd=tex_path.parent, so a relative `\bibliography{}`/
    # `\addbibresource{}` -- or any raw \input/\includegraphics -- only
    # resolves if that's the document's own real directory. Caught directly:
    # a first version of this using a throwaway mkdtemp() scratch directory
    # compiled without error but left the citation completely unresolved
    # ("Citing ? here.") because bibtex/biber could never find refs.bib
    # relative to a /tmp path that had nothing to do with the source
    # document -- same class of bug as the openout_any one in v3.1.0,
    # just from the opposite direction (wrong directory, not wrong
    # security policy).
    #
    # NOT dot-prefixed, unlike prepared_latex_inputs()'s own temp files:
    # this one gets compiled directly as a LaTeX jobname (by
    # compile_tex_direct), and a leading dot breaks that outright --
    # confirmed with a standalone repro (`lualatex .hidden.tex`): LaTeX
    # derives its jobname from the input filename up to the FIRST period,
    # which is empty for a dotfile, so it silently ignores
    # -output-directory and tries to write ITS OWN .log next to the
    # source instead, tripping the exact same openout_any=p wall a second,
    # unrelated way. prepared_latex_inputs()'s temp files never hit this
    # because they're only ever Pandoc INPUT (--metadata-file/a title
    # source) -- Pandoc has no concept of "jobname" to derive.
    def note(kind: str, detail: str) -> None:
        core.vprint(verbose, f"AUTO {kind}  {detail}")

    nativebib_font = core.mainfont_choice([md_path], metadata_files, variables, font or None, document_font,
                                     mainfont_auto, no_auto, note)
    fd, tex_path_str = mkstemp(suffix=".tex", prefix=f"{md_path.stem}-pdfmd-nativebib-",
                               dir=md_path.parent)
    os.close(fd)
    tex_path = Path(tex_path_str)
    try:
        with core.prepared_latex_inputs([title_source, *core.pandoc_metadata_order(metadata_files)], True,
                                       named_reader=named_reader, effective_reader=effective_from) as prepared, \
                core.document_header_file(md_path, bool(preamble_files) or core.has_embedded_preamble(md_path) or bool(pdf_meta_snippet_text),
                                         metadata_files, no_auto) as header_file, \
                core.pdf_metadata_header_file(pdf_meta_snippet_text) as pdf_meta_file, \
                core.script_fallback([md_path], metadata_files, variables, preamble_files, nativebib_font, None,
                                no_auto, note) as (fonts_header, fonts_filter):
            source, *prepared_metadata = prepared
            cmd = ["pandoc", str(source), "-o", str(tex_path), "-t", "beamer" if presentation else "latex",
                  "--standalone"]
            if effective_from:
                cmd += ["-f", effective_from]
            for metadata in prepared_metadata:
                cmd += ["--metadata-file", str(metadata)]
            pandoc_cwd = core.pandoc_working_directory(core.metadata_cwd(metadata_files, md_path.parent))
            cmd += core.resource_path_option(md_path.parent, pandoc_cwd, metadata_files)
            if presentation and slide_level is not None:
                cmd += ["--slide-level=" + str(slide_level)]
            first_font = nativebib_font
            if first_font:
                cmd += core.font_args("mainfont", first_font)
                cmd += core.mathfont_args(first_font, md_path, metadata_files, variables, font or None, no_auto, None, note)
            else:
                cmd += core.document_font_args([md_path], metadata_files, variables)
            if geometry_needed:
                cmd += ["-V", f"geometry:margin={core.DEFAULT_MARGIN}"]
            if monofont_needed:
                cmd += core.font_args("monofont", core.default_monofont())
            for variable in core.paper_variables(md_path, metadata_files, variables, None, core.paper_kind("tex", no_auto))[0]:
                cmd += ["-V", variable]
            if shift_heading:
                cmd += ["--shift-heading-level-by=-1"]
            if "--citeproc" in pandoc_options:
                cmd += before_citeproc
            cmd += pandoc_options
            apply_citation_aliases(cmd, md_path, metadata_files)
            cmd += core.paragraph_spacing_latex_args(md_path, metadata_files)
            if preamble_files:
                for preamble_file in preamble_files:
                    cmd += ["--include-in-header", str(preamble_file)]
            if pdf_meta_file is not None:
                cmd += ["--include-in-header", str(pdf_meta_file)]
            if fonts_header is not None:
                cmd += ["--include-in-header", str(fonts_header)]
            # Last, so a document's own header-includes can override anything
            # the shared preamble/pdf-meta files above defined (Pandoc would
            # otherwise drop it entirely; see document_header_file). Added
            # whenever header_file exists, not only when preamble_files is
            # non-empty -- pdf_meta_file alone is enough to trigger the drop
            # this guards against (see document_header_includes()'s own
            # docstring for the 2026-09-20 fix this is part of).
            if header_file is not None:
                cmd += ["--include-in-header", str(header_file)]
            cmd += core.document_filter_args(md_path, md_path, metadata_files, no_auto, csv_filter, pandoc_options,
                                             citation_engine=citation_engine, named_reader=named_reader)
            if "--citeproc" not in pandoc_options:
                cmd += before_citeproc
            if "--natbib" not in pandoc_options and "--biblatex" not in pandoc_options:
                cmd.append(f"--{citation_engine}")
                cmd += core.fullcite_pre_args(md_path, metadata_files, pandoc_options, citation_engine)    # `\\fullcite{}`, not citeproc
            if fonts_filter is not None:
                cmd += ["--lua-filter", str(fonts_filter)]
            if tablewidth_auto:
                cmd += core.width_filter_args(width_filter)
            cmd += core.cellalign_args(md_path, metadata_files)
            cmd += core.tblr_header_args(md_path, metadata_files)
            cmd += core.code_filter_args(no_auto, [md_path, title_source], metadata_files) + core.image_filter_args(no_auto, [md_path, title_source], metadata_files)
            core.hoist_code_header(cmd)
            cmd += core.markup_header_args(md_path, metadata_files, cmd)
            core.keep_header_includes(cmd, [md_path], metadata_files, pandoc_options, header_file)
            for lua_filter in lua_filters:
                cmd += ["--lua-filter", str(lua_filter)]
            cmd += core.deferred("pdfmd_filters.hidden", "finish_args")()
            cmd += core.deferred("pdfmd_bibliography", "native_path_args")(cmd)
            cmd = core.headers_as_metadata(cmd)
            core.log_cmd(cmd, pandoc_cwd, verbose)
            result = pandoc_run(cmd, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd)
        if result.returncode != 0 or not tex_path.exists():
            return False, result.stderr.strip() or "pandoc failed to produce an intermediate .tex"
        where = f"kept at {tex_path} (--keep-aux)" if keep_aux else "discarded after compiling"
        core.vprint(verbose, f"AUTO CITATIONENGINE  {md_path}: routing bibliography through --{citation_engine} "
               f"instead of --citeproc; intermediate .tex {where}")
        return core.compile_tex_direct(tex_path, output, engines, keep_aux, verbose, debug,
                                       document_directory=md_path.parent)
    finally:
        # Under --keep-aux, leave the intermediate .tex for inspection too --
        # it's the one artifact from THIS function (compile_tex_direct's own
        # --keep-aux already leaves the resulting .aux/.log/.out beside it).
        if not keep_aux:
            tex_path.unlink(missing_ok=True)

#!/usr/bin/env python3
"""Convert Markdown documents to PDF with Pandoc.

Examples:
    pdfmd report
    pdfmd slides -p
    pdfmd /path/to/report.md -d
    pdfmd Downloads -b -f "DejaVu Serif"
    pdfmd book -r -o book.pdf
    pdfmd chapter.md -y metadata.yaml
    pdfmd book -r -y
"""
import argparse
from fnmatch import fnmatchcase
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from shutil import which
from tempfile import NamedTemporaryFile
from textwrap import dedent
from typing import Iterator

PREAMBLE = r"\setcounter{MaxMatrixCols}{20}"
DEFAULT_FONT = "DejaVu Serif"
DEFAULT_VARS = []
AUTO_METADATA_DISABLED = object()

# Engines are tried in this order only when the user did not request one.
# An explicit --engine is never overridden.
PDF_ENGINES = (
    "lualatex", "xelatex", "pdflatex", "typst", "weasyprint",
    "wkhtmltopdf", "prince", "context", "pdfroff",
)
LATEX_ENGINES = frozenset({"lualatex", "xelatex", "pdflatex", "context"})
PREAMBLE_FILENAMES = ("preamble.tex", "latex-preamble.tex")


def installed_engines() -> list[str]:
    """Return PDF engines that are currently executable, in fallback order."""
    return [engine for engine in PDF_ENGINES if which(engine)]


def select_engines(requested: str | None, presentation: bool) -> list[str]:
    """Select installed engines in fallback order, or explain what is missing."""
    if requested:
        if which(requested):
            return [requested]
        raise SystemExit(
            f"Requested PDF engine '{requested}' was not found on PATH. "
            "Install it or choose one listed by --check-dependencies."
        )

    candidates = installed_engines()
    if presentation:
        # Pandoc's Beamer writer requires a TeX-family engine.
        candidates = [engine for engine in candidates if engine in LATEX_ENGINES]
    if candidates:
        return candidates

    kind = "a LaTeX/ConTeXt engine for Beamer" if presentation else "a PDF engine"
    raise SystemExit(
        f"No supported {kind} was found. Install Pandoc and one of: "
        + ", ".join(PDF_ENGINES)
        + ". Run --check-dependencies for a status report."
    )


def dependency_report() -> bool:
    """Print executable availability and return whether conversion can run."""
    pandoc = which("pandoc")
    print(f"{'OK  ' if pandoc else 'MISS'}  pandoc" + (f"  ({pandoc})" if pandoc else ""))
    for engine in PDF_ENGINES:
        path = which(engine)
        print(f"{'OK  ' if path else 'MISS'}  {engine}" + (f"  ({path})" if path else ""))
    return bool(pandoc and installed_engines())


def has_header_include_option(options: list[str]) -> bool:
    """Return whether the caller already explicitly supplied Pandoc's -H option."""
    return any(option in {"-H", "--include-in-header"}
               or option.startswith("--include-in-header=")
               for option in options)


def is_latex_preamble(path: Path) -> bool:
    """Accept preamble snippets, but reject complete documents and TikZ images."""
    text = path.read_text(encoding="utf-8-sig")
    forbidden = r"\\(?:documentclass|begin\s*\{document\}|end\s*\{document\}|begin\s*\{tikzpicture\})"
    return not bool(re.search(forbidden, text, re.IGNORECASE))


def preamble_candidates(directory: Path, document_stem: str) -> list[Path]:
    """Return intentionally named generic and document-specific preambles."""
    stem = document_stem.casefold()
    candidates: list[Path] = []
    for path in directory.glob("*.tex"):
        name = path.name.casefold()
        if name in PREAMBLE_FILENAMES:
            candidates.append(path)
            continue
        if (name == f"{stem}.tex" or name in {f"{stem}_preamble.tex", f"{stem}-preamble.tex"}
                or re.fullmatch(r"(?:latex-)?preamble-[^.]+\.tex", name)):
            candidates.append(path)
    # Generic files load first; document-specific settings then override them.
    def priority(path: Path) -> tuple[int, str]:
        name = path.name.casefold()
        if name == "preamble.tex":
            return (0, name)
        if name == "latex-preamble.tex":
            return (1, name)
        if name.startswith("preamble-") or name.startswith("latex-preamble-"):
            return (2, name)
        return (3, name)
    return sorted(candidates, key=priority)


def find_preambles(directory: Path, document_stem: str, options: list[str]) -> list[Path]:
    """Find safe, intentionally named LaTeX preambles beside a document."""
    if has_header_include_option(options):
        return []
    return [path.resolve() for path in preamble_candidates(directory, document_stem)
            if is_latex_preamble(path)]


def announce_preambles(preambles: list[Path]) -> None:
    for preamble in preambles:
        print(f"AUTO TEX   {preamble}")
    if len(preambles) > 1:
        print("WARN  Multiple preambles discovered; later files may override earlier definitions.",
              file=sys.stderr)


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


@contextmanager
def prepared_latex_inputs(paths: list[Path], latex_engine: bool) -> Iterator[list[Path]]:
    """Yield temporary, corrected inputs for LaTeX-family renders when needed."""
    temporary_paths: list[Path] = []
    prepared: list[Path] = []
    try:
        for path in paths:
            text = path.read_text(encoding="utf-8-sig")
            corrected = wrap_latex_header_includes(text) if latex_engine else text
            if corrected == text:
                prepared.append(path)
                continue
            with NamedTemporaryFile("w", encoding="utf-8", suffix=path.suffix,
                                    prefix=f".{path.stem}.pdfmd-", dir=path.parent,
                                    delete=False) as temporary:
                temporary.write(corrected)
                temporary_path = Path(temporary.name)
            temporary_paths.append(temporary_path)
            prepared.append(temporary_path)
        yield prepared
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


def latin_candidates(value: str) -> list[str]:
    """Return common Cyrillic spellings for a Latin name."""
    value = value.lower()
    replacements = (
        ("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("zh", "ж"),
        ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
        ("yu", "ю"), ("ya", "я"), ("ai", "ай"), ("oi", "oй"), ("oy", "ой"),
    )
    variants = [value]
    for latin, cyrillic in replacements:
        variants = [item.replace(latin, cyrillic) for item in variants]
    letter_map = str.maketrans({
        "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
        "g": "г", "h": "х", "i": "и", "j": "й", "k": "к", "l": "л",
        "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
        "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
        "y": "ы", "z": "з",
    })
    variants += [item.translate(letter_map) for item in variants]
    variants.append(value.translate(letter_map))
    variants.append(value.replace("ai", "ай").translate(letter_map))
    variants.append(value.replace("ai", "аи").translate(letter_map))
    return list(dict.fromkeys(variants))


def cyrillic_candidates(value: str) -> list[str]:
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "shch", "ы": "y", "э": "e", "ю": "yu",
        "я": "ya",
    }
    return ["".join(table.get(letter, letter) for letter in value.lower())]


def name_candidates(value: str) -> list[str]:
    value = Path(value).stem
    candidates = [value]
    if re.search("[А-Яа-яЁё]", value):
        candidates += cyrillic_candidates(value)
    else:
        candidates += latin_candidates(value)
    candidates = list(dict.fromkeys(candidates))
    return candidates + [f"Пробный {item}" for item in candidates]


def find_wildcard_markdown(value: Path) -> Path | None:
    """Resolve one case-insensitive wildcard pattern to a Markdown file."""
    pattern = value.name
    if not any(character in pattern for character in "*?["):
        return None
    directory = value.parent if str(value.parent) not in {"", "."} else Path.cwd()
    if not directory.is_dir():
        return None

    # Without an extension, match the Markdown stem, so '*scrutiny' naturally
    # finds 'CAS001-CAS002-CAS003_cassirer_scrutiny.md'.
    match_name = bool(Path(pattern).suffix)
    normalized_pattern = pattern.casefold()
    matches = [file for file in directory.glob("*.md")
               if fnmatchcase((file.name if match_name else file.stem).casefold(), normalized_pattern)]
    if not matches:
        raise FileNotFoundError(f"No Markdown file matches wildcard pattern '{value}'")
    if len(matches) > 1:
        names = ", ".join(file.name for file in sorted(matches))
        raise FileNotFoundError(f"Wildcard pattern '{value}' matches multiple Markdown files: {names}")
    return matches[0]


def find_markdown(value: Path, recursive: bool = False) -> Path:
    if value.exists() and value.is_file():
        return value
    wildcard_match = find_wildcard_markdown(value)
    if wildcard_match:
        return wildcard_match
    directory = value if value.is_dir() else Path.cwd()
    requested = value.name if value.suffix != ".pdf" else value.stem
    requested = Path(requested).stem
    search_dirs = [directory]
    if recursive:
        search_dirs = [directory] + [item for item in directory.rglob("*") if item.is_dir()]
    files = {
        unicodedata.normalize("NFC", file.stem).casefold(): file
        for folder in search_dirs for file in folder.glob("*.md")
    }
    for candidate in name_candidates(requested):
        normalized = unicodedata.normalize("NFC", candidate).casefold()
        if normalized in files:
            return files[normalized]
    available = ", ".join(sorted(files))
    raise FileNotFoundError(f"Could not find Markdown file for '{value}'. Available: {available or 'none'}")


def has_mainfont(md_path: Path, variables: list[str]) -> bool:
    if any(variable.startswith("mainfont=") for variable in variables):
        return True
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    return bool(front_matter and re.search(r"^mainfont\s*:", front_matter.group(1), re.MULTILINE))


def missing_glyph_warning(output: str) -> bool:
    return bool(re.search(
        r"missing character|Missing character|Unicode character .* not set|font .* not found",
        output,
    ))


def contains_citations(md_path: Path) -> bool:
    """Detect bracketed, bare, and suppress-citation Pandoc syntax."""
    text = md_path.read_text(encoding="utf-8-sig")
    return bool(re.search(r"(?<![\w@])(?:-?@[-\w:.]+)", text))


def frontmatter_value(md_path: Path, key: str) -> str | None:
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else None


def yaml_autoinclude(path: Path) -> bool:
    """Return whether automatic discovery may select this YAML file."""
    text = path.read_text(encoding="utf-8-sig")
    return not bool(re.search(r"^\s*autoinclude\s*:\s*(?:false|no|0)\s*$", text, re.IGNORECASE | re.MULTILINE))


def yaml_order(path: Path, fallback: int = 0) -> tuple[bool, Decimal | int]:
    match = re.search(r"^\s*yamlorder\s*:\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$",
                      path.read_text(encoding="utf-8-sig"), re.IGNORECASE | re.MULTILINE)
    if not match:
        return (False, fallback)
    return (True, Decimal(match.group(1)))


def order_metadata(paths: list[Path]) -> list[Path]:
    """Apply yamlorder where present while preserving explicit order otherwise."""
    if any(yaml_order(path)[0] for path in paths):
        return [path for _, path in sorted(
            enumerate(paths), key=lambda item: (
                yaml_order(item[1], item[0])[1], item[0]))]
    return paths


def resolve_yaml(directory: Path, value: str) -> Path:
    path = Path(value)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(Path.cwd() / path)
        candidates.append(directory / path)
        if not path.suffix:
            candidates.extend((Path.cwd() / path.with_suffix(".yaml"),
                               directory / path.with_suffix(".yaml")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Metadata file not found: {value}")


def find_metadata(directory: Path, requested: list[str] | None, report: bool = False,
                  document_class: str | None = None,
                  document_stem: str | None = None) -> Path | list[Path] | object | None:
    """Choose metadata files, supporting explicit stacks and automatic discovery."""
    if requested == []:
        return AUTO_METADATA_DISABLED
    if requested is not None:
        if requested == ["all"]:
            candidates = [item for item in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
                          if item.name.lower() != "defaults.yaml" and yaml_autoinclude(item)]
            return order_metadata(candidates)
        return order_metadata([resolve_yaml(directory, value) for value in requested])
    candidates = [item for item in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
                  if item.name.lower() != "defaults.yaml" and yaml_autoinclude(item)]
    metadata = next((item for item in candidates if item.name.lower() == "metadata.yaml"), None)
    document_metadata = ([item for item in candidates
                          if document_stem and item.stem.casefold() == document_stem.casefold()]
                         if document_stem else [])
    if document_metadata:
        # metadata.yaml is the shared base; document-named YAML overrides it.
        selected = ([metadata] if metadata and metadata not in document_metadata else []) + document_metadata
        return order_metadata(selected)
    if report:
        preferred = next((item for item in candidates if item.name.lower() == "report.yaml"), None)
        preferred = preferred or next((item for item in candidates if item.name.lower() == "book.yaml"), None)
        if preferred:
            return order_metadata(([metadata] if metadata else []) + [preferred])
    if metadata:
        return metadata
    if document_class:
        matching = [item for item in candidates if item.stem.casefold() == document_class.casefold()]
        if len(matching) == 1:
            return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(item.name for item in candidates)
        raise ValueError(f"Multiple YAML files found in {directory}: {names}; use -y FILE or bare -y")
    return None


def chapter_value(md_path: Path):
    """Read the scalar chapter value from a Markdown YAML header."""
    text = md_path.read_text(encoding="utf-8-sig")
    front_matter = re.match(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.DOTALL)
    if not front_matter:
        return None
    match = re.search(r"^chapter\s*:\s*(.*?)\s*$", front_matter.group(1), re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return None if value.casefold() in {"", "null", "none", "exclude", "excluded"} else value


def has_chapter_field(md_path: Path) -> bool:
    return bool(re.search(r"^chapter\s*:", md_path.read_text(encoding="utf-8-sig"), re.MULTILINE))


def chapter_order(md_path: Path):
    """Sort chapters by explicit front-matter precedence.

    The order is: always-first, first, numeric values, letter-prefixed values,
    unnumbered files, last, always-last. Numeric values may be negative or
    decimal; letter-prefixed values sort by their letter prefix and number.
    """
    value = chapter_value(md_path)
    name = md_path.name.casefold()
    if value is None:
        return (4, "", Decimal(0), Decimal(0), name)
    normalized = value.casefold()
    if normalized == "always-first":
        return (0, "", Decimal(0), Decimal(0), name)
    if normalized == "first":
        return (1, "", Decimal(0), Decimal(0), name)
    if normalized == "last":
        return (5, "", Decimal(0), Decimal(0), name)
    if normalized == "always-last":
        return (6, "", Decimal(0), Decimal(0), name)
    relative = re.fullmatch(r"(before|after)\s+(-?(?:\d+(?:\.\d*)?|\.\d+))", normalized)
    if relative:
        offset = Decimal(0) if relative.group(1) == "before" else Decimal(2)
        return (2, "", Decimal(relative.group(2)), offset, name)
    try:
        return (2, "", Decimal(value), Decimal(1), name)
    except InvalidOperation:
        lettered = re.fullmatch(r"([a-z]+)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", normalized)
        if lettered:
            return (3, lettered.group(1), Decimal(lettered.group(2)), Decimal(1), name)
        return (3, normalized, Decimal(0), Decimal(1), name)


def excluded_by_cli(md_path: Path, exclusions: list[str]) -> bool:
    candidates = {md_path.name.casefold(), md_path.stem.casefold(), str(md_path).casefold()}
    for exclusion in exclusions:
        value = Path(exclusion)
        names = {value.name.casefold(), value.stem.casefold(), str(value).casefold()}
        if candidates & names:
            return True
    return False


def report_sources(paths: list[Path], exclusions: list[str], exclude_unnumbered: bool = False,
                   recursive: bool = False) -> tuple[list[Path], list[Path]]:
    files = []
    for path in paths:
        if path.is_dir():
            files.extend(path.rglob("*.md") if recursive else path.glob("*.md"))
        elif path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
    all_files = sorted(set(files))
    excluded = [file for file in all_files if chapter_value(file) is None and has_chapter_field(file)]
    excluded += [file for file in all_files if excluded_by_cli(file, exclusions) and file not in excluded]
    if exclude_unnumbered:
        excluded += [file for file in all_files
                     if file not in excluded and not has_chapter_field(file)]
    included = [file for file in all_files if file not in excluded]
    return sorted(included, key=chapter_order), excluded


def pdf_path(path: Path) -> Path:
    """Add Pandoc's expected PDF suffix when the user omitted it."""
    return path if path.suffix else path.with_suffix(".pdf")


def convert_one(md_path: Path, out_dir: Path | None, presentation: bool, font: str,
                engines: list[str], variables: list[str], slide_level: int | None,
                pandoc_options: list[str],
                metadata_file: Path | list[Path] | None = None,
                output_file: Path | None = None,
                preamble_files: list[Path] | None = None) -> tuple[Path, bool, str]:
    output = output_file or ((out_dir / f"{md_path.stem}.pdf") if out_dir else md_path.with_suffix(".pdf"))
    output.parent.mkdir(parents=True, exist_ok=True)
    document_font = has_mainfont(md_path, variables)
    explicit_font = document_font or bool(font)

    metadata_files = metadata_file if isinstance(metadata_file, list) else ([metadata_file] if metadata_file else [])
    result = None
    for engine_index, engine in enumerate(engines):
        with prepared_latex_inputs([md_path, *metadata_files], engine in LATEX_ENGINES) as prepared:
            source, *prepared_metadata = prepared

            def run(selected_font: str | None, fallback: bool = False):
                cmd = ["pandoc", str(source), "-o", str(output), "--pdf-engine=" + engine]
                for metadata in prepared_metadata:
                    cmd += ["--metadata-file", str(metadata)]
                pandoc_cwd = metadata_files[0].parent if metadata_files else md_path.parent
                if presentation:
                    cmd += ["-t", "beamer"]
                    if slide_level is not None:
                        cmd += ["--slide-level=" + str(slide_level)]
                if selected_font:
                    cmd += ["-V", f"mainfont={selected_font}"]
                if fallback and not any(variable.startswith("mainfontfallback=") for variable in variables):
                    cmd += ["-V", f"mainfontfallback={DEFAULT_FONT}"]
                for variable in variables:
                    cmd += ["-V", variable]
                cmd += pandoc_options
                if preamble_files and engine in LATEX_ENGINES:
                    for preamble_file in preamble_files:
                        cmd += ["--include-in-header", str(preamble_file)]
                if contains_citations(md_path) and "--citeproc" not in pandoc_options and "--no-citeproc" not in pandoc_options:
                    cmd.append("--citeproc")
                return subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)

            result = run(None if document_font else font, fallback=document_font)
            combined_output = result.stdout + result.stderr
            if not explicit_font and result.returncode == 0 and missing_glyph_warning(combined_output):
                result = run(font or DEFAULT_FONT)
        if result.returncode == 0:
            break
        if engine_index + 1 < len(engines):
            print(f"WARN  {md_path}: {engine} failed; trying {engines[engine_index + 1]}...", file=sys.stderr)
    assert result is not None
    return md_path, result.returncode == 0, result.stderr[-3000:]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Markdown files to PDF with Pandoc.")
    parser.add_argument("path", type=Path, nargs="*", help="Markdown name, files, or directory (default: current directory)")
    parser.add_argument("-p", "--presentation", action="store_true", help="create Beamer slides")
    parser.add_argument("--slide-level", type=int, help="Beamer heading level used for slide breaks")
    parser.add_argument("-b", "--batch", action="store_true", help="convert all Markdown files")
    parser.add_argument("-r", "--report", "--book", action="store_true",
                        help="combine all Markdown files in PATH into one PDF")
    parser.add_argument("--recursive", action="store_true",
                        help="include Markdown files in subdirectories (report/book mode)")
    parser.add_argument("-o", "--out", type=Path,
                        help="output directory (batch) or PDF filename (report/book)")
    parser.add_argument("-d", "-cwd", "--cwd", "--destination-cwd", action="store_true",
                        dest="destination_cwd",
                        help="save PDFs in the current working directory")
    parser.add_argument("-f", "--font", default=None, help="font to use if glyph fallback is needed")
    parser.add_argument("-e", "--engine", help="PDF engine to use (default: first installed supported engine)")
    parser.add_argument("--check-dependencies", action="store_true",
                        help="show Pandoc and supported PDF-engine availability, then exit")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="parallel workers in batch mode")
    parser.add_argument("-V", "--var", action="append", default=[], dest="variable", metavar="KEY=VALUE")
    parser.add_argument("-y", "--metadata-file", nargs="*", default=None, metavar="FILE",
                        help="metadata YAML file(s), 'all', or bare -y to disable discovery")
    parser.add_argument("-i", "--ignore", "--exclude", action="append", default=[], metavar="FILE",
                        help="exclude a Markdown file from report/book input (extension optional)")
    parser.add_argument("--exclude-unnumbered", action="store_true",
                        help="exclude Markdown files without a chapter field in report/book mode")
    return parser


def main() -> None:
    args, pandoc_options = build_parser().parse_known_args()
    if args.check_dependencies:
        raise SystemExit(0 if dependency_report() else 1)
    if not which("pandoc"):
        raise SystemExit("Pandoc was not found on PATH. Install Pandoc, then run --check-dependencies.")
    paths = args.path or [Path.cwd()]
    variables = DEFAULT_VARS + args.variable
    engines = select_engines(args.engine, args.presentation)
    if args.batch and args.report:
        raise SystemExit("Choose either --batch or --report/--book, not both")
    if args.presentation and args.report:
        raise SystemExit("--presentation cannot be combined with --report/--book")
    if args.report:
        files, excluded = report_sources(paths, args.ignore, args.exclude_unnumbered, args.recursive)
        if not files:
            raise SystemExit("No Markdown files found for the report")
        try:
            document_class = (frontmatter_value(files[0], "documentclass")
                              or frontmatter_value(files[0], "class"))
            metadata_directory = paths[0] if len(paths) == 1 and paths[0].is_dir() else files[0].parent
            metadata = find_metadata(metadata_directory.resolve(), args.metadata_file, report=True,
                                     document_class=document_class, document_stem=files[0].stem)
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(str(error))
        output = pdf_path(args.out) if args.out else Path.cwd() / "book.pdf"
        if output.is_dir():
            output = output / "book.pdf"
        output = output.resolve()
        metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
        pandoc_cwd = metadata_files[0].parent if metadata_files else files[0].parent
        preambles = find_preambles(files[0].parent, files[0].stem, pandoc_options)
        announce_preambles(preambles)
        # Reports need one Pandoc invocation, so retry each usable engine here.
        result = None
        for engine_index, engine in enumerate(engines):
            with prepared_latex_inputs([*files, *metadata_files], engine in LATEX_ENGINES) as prepared:
                prepared_files = prepared[:len(files)]
                prepared_metadata = prepared[len(files):]
                cmd = ["pandoc", *map(str, prepared_files), "-o", str(output), "--pdf-engine=" + engine]
                if metadata is not AUTO_METADATA_DISABLED:
                    for metadata_file in prepared_metadata:
                        cmd += ["--metadata-file", str(metadata_file)]
                for variable in variables:
                    cmd += ["-V", variable]
                cmd += pandoc_options
                if preambles and engine in LATEX_ENGINES:
                    for preamble in preambles:
                        cmd += ["--include-in-header", str(preamble)]
                if (any(contains_citations(file) for file in files)
                        and "--citeproc" not in pandoc_options
                        and "--no-citeproc" not in pandoc_options):
                    cmd.append("--citeproc")
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=pandoc_cwd)
            if result.returncode == 0:
                break
            if engine_index + 1 < len(engines):
                print(f"WARN  REPORT: {engine} failed; trying {engines[engine_index + 1]}...", file=sys.stderr)
        assert result is not None
        for file in files:
            if not has_chapter_field(file):
                print(f"[WARNING] unnumbered Markdown included: {file}")
            print(f"OK    {file}")
        for file in excluded:
            print(f"SKIP  {file}")
        if metadata is not AUTO_METADATA_DISABLED:
            for metadata_file in metadata_files:
                label = "AUTO YAML" if args.metadata_file is None else "YAML"
                print(f"{label}  {metadata_file}")
        print(f"{'OK  ' if result.returncode == 0 else 'FAIL'}  REPORT  {output}")
        if result.stderr:
            print(result.stderr[-3000:])
        if result.returncode:
            raise SystemExit(1)
        return
    metadata_by_dir = {}
    def metadata_for(file, document_class=None):
        directory = file.parent.resolve()
        cache_key = (directory, file.stem.casefold())
        if cache_key not in metadata_by_dir:
            metadata_by_dir[cache_key] = find_metadata(directory, args.metadata_file,
                                                        document_class=document_class,
                                                        document_stem=file.stem)
            discovered = metadata_by_dir[cache_key]
            if args.metadata_file is None and discovered is not None and discovered is not AUTO_METADATA_DISABLED:
                paths = discovered if isinstance(discovered, list) else [discovered]
                for path in paths:
                    print(f"AUTO YAML  {path}")
        value = metadata_by_dir[cache_key]
        return None if value is AUTO_METADATA_DISABLED else value
    if args.batch:
        if len(paths) != 1 or not paths[0].is_dir():
            raise SystemExit("Batch mode requires one directory path")
        files = sorted(paths[0].rglob("*.md"))
        output = Path.cwd() if args.destination_cwd else (args.out.resolve() if args.out else None)
        if output:
            output.mkdir(parents=True, exist_ok=True)
        jobs = max(1, args.jobs)
        def preamble_for(file):
            preambles = find_preambles(file.parent, file.stem, pandoc_options)
            announce_preambles(preambles)
            return preambles
        work = lambda file: convert_one(file, output, args.presentation, args.font, engines, variables, args.slide_level, pandoc_options, metadata_for(file), preamble_files=preamble_for(file))
        results = []
        if jobs > 1:
            with ProcessPoolExecutor(max_workers=jobs) as executor:
                futures = [executor.submit(convert_one, file, output, args.presentation, args.font, engines, variables, args.slide_level, pandoc_options, metadata_for(file), None, preamble_for(file)) for file in files]
                results = [future.result() for future in as_completed(futures)]
                results.sort(key=lambda result: result[0].name.casefold())
        else:
            results = [work(file) for file in files]
    else:
        try:
            if len(paths) != 1:
                raise FileNotFoundError("Single-file mode accepts one Markdown name or path")
            source = find_markdown(paths[0])
        except FileNotFoundError as error:
            raise SystemExit(str(error))
        if args.out:
            requested_output = Path.cwd() / args.out.name if args.destination_cwd else args.out.resolve()
            output_file = pdf_path(requested_output)
        else:
            output_file = Path.cwd() / f"{source.stem}.pdf" if args.destination_cwd else None
        document_class = (frontmatter_value(source, "documentclass")
                          or frontmatter_value(source, "class"))
        try:
            metadata = metadata_for(source, document_class=document_class)
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(str(error))
        preambles = find_preambles(source.parent, source.stem, pandoc_options)
        announce_preambles(preambles)
        results = [convert_one(source, None, args.presentation, args.font, engines, variables, args.slide_level, pandoc_options, metadata, output_file, preambles)]
    failures = [result for result in results if not result[1]]
    for source, ok, error in results:
        print(f"{'OK  ' if ok else 'FAIL'}  {source}")
        if error:
            print(error)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

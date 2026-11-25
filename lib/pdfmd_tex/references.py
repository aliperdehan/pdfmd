r"""Project-local references inside TeX files read with \input."""

from __future__ import annotations

import os
import re
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfmd_base import core


INPUT = r"input|InputIfFileExists"
ASSET = (r"includegraphics\*?|includepdf|pgfplotstableread|pgfplotstabletypeset|lstinputlisting|verbatiminput|csvreader"
         r"|addplot\+?(?:\s*\[[^\]\n]*\])?\s*table")
REFERENCE = re.compile(
    r"\\begin\{(verbatim\*?|Verbatim|lstlisting|minted)\}.*?\\end\{\1\}"
    r"|\\verb\*?([^A-Za-z@\s])[^\n]*?\2|\\[\\%]|%[^\n]*"
    rf"|\\(?P<command>{INPUT}|{ASSET})(?:\s*\[[^\]\n]*\])?\s*\{{(?P<name>[^{{}}\n]+)\}}",
    re.S,
)
HAS_INPUT = re.compile(r"\\(?:" + INPUT + r")\s*\{")
TEX_COMMANDS = {"input", "InputIfFileExists"}
GRAPHIC_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg")
SOURCE_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd", ".qmd", ".txt", ".tex", ".latex", ".yaml", ".yml")


def markdown_tex(text: str) -> str:
    """Mask ordinary code while exposing the contents of explicit raw TeX."""
    from pdfmd_check.lint import blank, mask_code
    from pdfmd_tex.inputs import RAW_FENCE_RE, RAW_INLINE_RE

    def expose(found, group, format_group):
        if found[format_group] not in ("tex", "latex"):
            return found[0]
        return (blank(text[found.start():found.start(group)]) + found[group]
                + blank(text[found.end(group):found.end()]))

    pieces = list(text)
    for pattern, group, format_group in ((RAW_FENCE_RE, 3, 2), (RAW_INLINE_RE, 1, 2)):
        for found in pattern.finditer(text):
            pieces[found.start():found.end()] = expose(found, group, format_group)
    return mask_code("".join(pieces))[0]


class IncludedPaths:
    def __init__(self, document: Path, cwd: Path, stack: ExitStack, warned: set):
        self.document = document.resolve()
        self.cwd = cwd.resolve()
        self.stack = stack
        self.warned = warned
        self.scratch: Path | None = None
        self.saved = 0
        self.fragments: dict[Path, Path] = {}
        self.active: set[Path] = set()

    def save(self, text: str, name: str) -> Path:
        if self.scratch is None:
            self.scratch = Path(self.stack.enter_context(TemporaryDirectory(prefix="pdfmd-tex-inputs-")))
        self.saved += 1
        folder = self.scratch / str(self.saved)
        folder.mkdir()
        path = folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def lookup(self, name: str, command: str, source: Path, nested: bool) -> Path | None:
        if any(char in name for char in "\\#%{}$^~") or "://" in name:
            return None                        # macro, TeX syntax, or a URL
        absolute = Path(name).is_absolute()
        directories = [self.cwd, self.document, source.parent]
        if nested:
            directories = [source.parent, self.document, self.cwd]
        extensions = ("",)
        if not Path(name).suffix:
            if command in TEX_COMMANDS:
                extensions += (".tex",)
            elif command.startswith("includegraphics"):
                extensions += GRAPHIC_EXTENSIONS
            elif command == "includepdf":
                extensions += (".pdf",)
        found = {}
        for folder in dict.fromkeys(directories):
            match = next((folder / (name + ext) for ext in extensions if (folder / (name + ext)).is_file()), None)
            if match is not None:
                found[folder] = match
            if absolute:
                break
        if nested and not absolute and source.parent != self.document:
            local, main = found.get(source.parent), found.get(self.document)
            if local is not None and main is not None and local.resolve() != main.resolve():
                pair = local, main
                if pair not in self.warned:
                    self.warned.add(pair)
                    print(f"WARN  TeX input path: {core.under_home(local)} and {core.under_home(main)} both exist; "
                          f"using {core.under_home(local)}", file=sys.stderr)
        return next(iter(found.values()), None)

    def rewrite(self, text: str, source: Path, *, nested: bool = False, markdown: bool = False) -> str:
        if not nested and not HAS_INPUT.search(text):
            return text
        visible = markdown_tex(text) if markdown else text
        result = []
        start = 0
        for match in REFERENCE.finditer(visible):
            command = match["command"]
            if command is None or (not nested and command not in TEX_COMMANDS):
                continue
            left, right = match.span("name")
            name = text[left:right].strip()
            path = self.lookup(name, command, source, nested)
            if path is None:
                continue
            if command in TEX_COMMANDS:
                updated = self.fragment(path)
                if not nested and updated == path:
                    continue
                path = updated
            elif not nested:
                continue
            result.extend((text[start:left], path.as_posix()))
            start = right
        return "".join(result) + text[start:]

    def fragment(self, path: Path) -> Path:
        if path in self.fragments:
            return self.fragments[path]
        if path in self.active:
            return path
        self.active.add(path)
        try:
            text = path.read_text(encoding="utf-8-sig")
            revised = self.rewrite(text, path, nested=True)
        except (OSError, UnicodeDecodeError):
            return path
        finally:
            self.active.remove(path)
        variant = self.save(revised, path.name) if text != revised else path
        self.fragments[path] = variant
        return variant

    def source(self, path: Path, markdown: bool = False) -> Path:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return path
        revised = self.rewrite(text, path.resolve(), markdown=markdown)
        return self.save(revised, path.name) if revised != text else path


@contextmanager
def tex_source(path: Path, document: Path, cwd: Path, warned: set[tuple[Path, Path]]):
    with ExitStack() as stack:
        yield IncludedPaths(document, cwd, stack, warned).source(path)


@contextmanager
def pandoc_sources(command: list[str], document: Path, cwd: Path, warned: set[tuple[Path, Path]]):
    """Prepare only Pandoc's source and header arguments for the duration of a build."""
    with ExitStack() as stack:
        paths = IncludedPaths(document, cwd, stack, warned)
        revised = list(command)
        inputs = {index: "" for index in range(1, command.index("-o"))} if "-o" in command else {}
        for index, word in enumerate(command[:-1]):
            if word in ("-H", "--include-in-header", "--metadata-file"):
                inputs[index + 1] = ""
            elif word.startswith(("--include-in-header=", "--metadata-file=")):
                inputs[index] = word.split("=", 1)[0] + "="
            elif word.startswith("-H") and len(word) > 2:
                inputs[index] = "-H"
        for index, prefix in inputs.items():
            path = cwd / command[index][len(prefix):]
            suffix = path.suffix.lower()
            if suffix not in SOURCE_EXTENSIONS:
                continue
            prepared = paths.source(path, markdown=suffix not in (".tex", ".latex"))
            if prepared != path:
                revised[index] = prefix + os.fspath(prepared)
        yield revised

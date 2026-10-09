"""Starting points for new documents: `pdfmd --init TEMPLATE [NAME]` (v3.26.17).

A template is a folder of files (or one Markdown file). Copying it into a new folder replaces `{{name}}`, `{{title}}`,
`{{author}}`, `{{date}}` and `{{year}}` in the text files and `__name__` in file names; any other `{{...}}` stays as it
is. `description.txt` (one line, for the list) and `next.txt` (what to type next) belong to the template and are not
copied. The templates that come with pdfmd are in `data/`; your own go in a `templates/` folder of pdfmd's config folder
(one folder or one .md file each), or anywhere, named by path. pdfmd.py works without this package.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".yaml", ".yml", ".bib", ".tex", ".csv", ".tsv", ".json", ".lua", ".css",
                 ".typ", ".csl", ".html", ".sty", ".cls", ".bst", ""}
OWN_FILES = {"description.txt", "next.txt"}
SKIPPED = {".DS_Store", "__pycache__", ".git"}
PLACEHOLDER_RE = re.compile(r"\{\{\s*(name|title|author|date|year)\s*\}\}")


class TemplateError(ValueError):
    pass


def builtin() -> dict[str, Path]:
    return {folder.name: folder for folder in sorted(DATA.iterdir()) if folder.is_dir() and not folder.name.startswith(("_", "."))} \
        if DATA.is_dir() else {}


def user_templates(folder: Path) -> dict[str, Path]:
    """The templates in `folder`: each subfolder, and each .md file (its name without the extension)."""
    found: dict[str, Path] = {}
    if folder.is_dir():
        for item in sorted(folder.iterdir()):
            if item.name.startswith((".", "_")):
                continue
            if item.is_dir():
                found[item.name] = item
            elif item.suffix.lower() in (".md", ".markdown"):
                found[item.stem] = item
    return found


def describe(template: Path) -> str:
    if template.is_dir():
        note = template / "description.txt"
        if note.is_file():
            return note.read_text(encoding="utf-8").strip().splitlines()[0] if note.read_text(encoding="utf-8").strip() else ""
        count = sum(1 for item in template.rglob("*") if item.is_file() and item.name not in OWN_FILES)
        return f"{count} file(s)"
    return "one Markdown file"


def find(spec: str, user_folder: Path | None) -> Path | None:
    """The template `spec` names: one of yours, a built-in one, or a folder / .md file given by path."""
    if user_folder is not None:
        mine = user_templates(user_folder)
        if spec in mine:
            return mine[spec]
    if spec in builtin():
        return builtin()[spec]
    candidate = Path(spec).expanduser()
    if candidate.is_dir() or (candidate.is_file() and candidate.suffix.lower() in (".md", ".markdown")):
        return candidate
    return None


def fill(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda found: values.get(found.group(1), found.group(0)), text)


def plan(template: Path, target: Path, values: dict[str, str]) -> list[tuple[Path, Path]]:
    """[(source file, destination)] for `template`: a folder goes into `target` (a folder), a .md file becomes `target`."""
    if template.is_file():
        return [(template, target)]
    pairs = []
    for source in sorted(template.rglob("*")):
        relative = source.relative_to(template)
        if not source.is_file() or any(part in SKIPPED for part in relative.parts) or relative.as_posix() in OWN_FILES:
            continue
        parts = [part.replace("__name__", values["name"]) for part in relative.parts]
        pairs.append((source, target.joinpath(*parts)))
    return pairs


def create(template: Path, target: Path, values: dict[str, str]) -> list[Path]:
    """Copy `template` to `target` (a new folder, or for a one-file template the new .md file); nothing that is already
    there is touched: TemplateError names what would be."""
    pairs = plan(template, target, values)
    if not pairs:
        raise TemplateError(f"the template {template.name} has no files")
    clash = [destination for _, destination in pairs if destination.exists()]
    if clash:
        raise TemplateError("these already exist, so nothing was written: " + ", ".join(str(item) for item in clash))
    written = []
    for source, destination in pairs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in TEXT_SUFFIXES:
            try:
                destination.write_text(fill(source.read_text(encoding="utf-8"), values), encoding="utf-8", newline="\n")
                written.append(destination)
                continue
            except UnicodeDecodeError:
                pass
        shutil.copyfile(source, destination)
        written.append(destination)
    return written


def next_step(template: Path, values: dict[str, str]) -> str:
    hint = template / "next.txt" if template.is_dir() else None
    if hint is not None and hint.is_file():
        return fill(hint.read_text(encoding="utf-8").strip(), values)
    return f"pdfmd {values['name']}"

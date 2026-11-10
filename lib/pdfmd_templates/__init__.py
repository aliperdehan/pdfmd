"""Starting points for new documents: `pdfmd --init TEMPLATE [NAME]` (v3.26.17).

A template is a folder of files (or one Markdown file). Copying it into a new folder replaces `{{name}}`, `{{title}}`,
`{{author}}`, `{{date}}` and `{{year}}` in the text files and `__name__` in file names; any other `{{...}}` stays as it
is. `description.txt` (one line, for the list) and `next.txt` (what to type next) belong to the template and are not
copied. The templates that come with pdfmd are in `data/`; your own go in a `templates/` folder of pdfmd's config folder
(one folder or one .md file each), or anywhere, named by path.

`init_command` is `pdfmd --init` itself, moved out of `pdfmd.py` unchanged (v3.33.2, SPLIT.md). `core` is the `pdfmd`
module, bound by `pdfmd.py` when it loads (the first binding wins); the command reads `core.config_root` and
`core.display_path` when it runs.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

core = None

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
    # Escape placeholders that form a double-quoted YAML front-matter scalar.
    parts = re.split(r"(?m)^---[ \t]*$", text, maxsplit=2)
    if len(parts) == 3 and not parts[0].strip():
        scalar = re.compile(r'(?m)^([ \t]*(?:[^:#\n]+):[ \t]*")(' + PLACEHOLDER_RE.pattern + r')(")([ \t]*(?:#.*)?)$')
        def quote(found):
            value = values.get(found.group(3))
            return found.group(0) if value is None else found.group(1) + json.dumps(value, ensure_ascii=False)[1:-1] + found.group(4) + found.group(5)
        parts[1] = scalar.sub(quote, parts[1])
        text = "---".join(parts)
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
                text = fill(source.read_text(encoding="utf-8"), values)
                with open(destination, "w", encoding="utf-8", newline="\n") as handle:       # (Path.write_text has no newline= before 3.10)
                    handle.write(text)
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


# --- pdfmd --init: a new document from a template (v3.26.17) -----------------------------------------------

def git_user_name() -> str:
    try:
        done = subprocess.run(["git", "config", "user.name"], capture_output=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def init_command(args) -> int:
    """`pdfmd --init [TEMPLATE] [NAME]`: list the templates, or copy one into a new folder (a new .md file for a template
    that is one file). Nothing that exists is overwritten."""
    folder = core.config_root() / "templates"
    mine = user_templates(folder)
    spec = args.init
    if not spec:
        print("Templates (pdfmd --init TEMPLATE [NAME]):")
        for name, path in builtin().items():
            print(f"  {name:<10} {describe(path)}")
        for name, path in mine.items():
            print(f"  {name:<10} {describe(path)}  (yours)")
        print(f"\nYour own: a folder, or one .md file, in {core.display_path(folder)}; or name any folder or .md file by path.")
        return 0
    template = find(spec, folder)
    if template is None:
        names = ", ".join([*builtin(), *mine])
        print(f"No template called '{spec}'. The templates are: {names}. A folder or .md file can be named by its path.",
              file=sys.stderr)
        return 1
    given = args.path[0] if args.path else None
    default = template.stem if template.is_file() else template.name
    target = Path(given) if given is not None else Path(default)
    if template.is_file() and target.suffix.lower() not in (".md", ".markdown"):
        target = target.with_name(target.name + ".md")
    name = re.sub(r"[^\w.-]+", "-", (target.stem if template.is_file() else target.name) or default).strip("-") or "document"
    variables = {}
    for variable in args.variable or []:
        match = re.match(r"^([^:=]+)[:=](.*)$", variable)
        if match:
            variables[match.group(1)] = match.group(2)
    now = datetime.now()
    values = {"name": name, "title": variables.get("title") or re.sub(r"[-_]+", " ", name).strip().title(),
              "author": variables.get("author") or git_user_name() or "Your Name",
              "date": variables.get("date") or now.strftime("%Y-%m-%d"), "year": str(now.year)}
    try:
        written = create(template, target, values)
    except TemplateError as error:
        print(f"--init: {error}", file=sys.stderr)
        return 1
    for path in written:
        print(f"CREATED  {core.display_path(path)}")
    step = next_step(template, values)
    if template.is_dir() and target.resolve() != Path.cwd().resolve():
        step = step if step.startswith("cd ") else f"cd {target} && {step}"
    print(f"NEXT     {step}")
    return 0

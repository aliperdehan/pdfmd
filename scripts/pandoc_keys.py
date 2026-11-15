#!/usr/bin/env python3
"""Derive the shipped top-level option clashes from installed Pandoc and Quarto (no network).

Run with --check to report drift without writing. Pandoc's installed roff manual is required; --manual names another copy.
Quarto's optional --quarto-schema is its all-schema-definitions.json; without a reliable front-matter schema, routed
inputs cannot use top-level options. Neither tool nor its documentation is consulted during a document build.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "lib" / "pdfmd_args" / "pandoc_keys.json"


def pandoc(*args):
    return subprocess.run(["pandoc", *args], check=False, capture_output=True, text=True)


def manual_path():
    executable = Path(shutil.which("pandoc") or "pandoc").resolve()
    candidates = [executable.parent.parent / "share/man/man1/pandoc.1",
                  Path("/opt/homebrew/share/man/man1/pandoc.1"), Path("/usr/local/share/man/man1/pandoc.1"),
                  Path("/usr/share/man/man1/pandoc.1")]
    return next((p for p in candidates if p.is_file()), None)


def quarto_schema_path():
    executable = shutil.which("quarto")
    if executable:
        path = Path(executable).resolve().parent.parent / "share/editor/tools/yaml/all-schema-definitions.json"
        if path.is_file():
            return path
    return None


def template_keys():
    """Inspect every writer and recursively load partials embedded in its default template."""
    partials, writers = {}, []

    def expand(text):
        result = text
        for name in re.findall(r"\$([\w.-]+)\(\)\$", text):
            if name not in partials:
                partials[name] = ""  # a recursive partial cannot loop forever
                found = pandoc("--print-default-data-file", "templates/" + name)
                if found.returncode:
                    raise SystemExit(f"Cannot read Pandoc template partial {name}: {found.stderr}")
                partials[name] = expand(found.stdout)
            result += "\n" + partials[name]
        return result

    keys = set()
    found = pandoc("--list-output-formats")
    if found.returncode:
        raise SystemExit(found.stderr)
    for writer in found.stdout.split():
        template = pandoc("-D", writer)
        if template.returncode:
            continue  # this writer has no default template
        writers.append(writer)
        text = re.sub(r"\$[\w.-]+\(\)\$", "", expand(template.stdout))
        keys.update(re.findall(r"\$([\w-]+)(?:\$|\.)", text))
        keys.update(re.findall(r"\$(?:if|for)\(([\w-]+)", text))
    return sorted(keys - {"if", "else", "endif", "for", "endfor", "sep"}), writers


def documented_keys(text):
    """Variables, citation/EPUB/Jupyter metadata, YAML metadata examples, and fields explicitly named elsewhere."""
    sections = []
    # The manual is shipped with Pandoc; use its headings rather than an independently maintained list of keys.
    for heading in (".SS Variables\n", ".SH CITATIONS\n", ".SS EPUB Metadata\n", ".SH JUPYTER NOTEBOOKS\n"):
        if heading not in text:
            raise SystemExit(f"Unsupported Pandoc manual: missing {heading.strip()}")
        tail = text.split(heading, 1)[1]
        section = tail.split("\n.SH ", 1)[0] if heading != ".SS EPUB Metadata\n" else tail.split("\n.SS ", 1)[0]
        # In the Variables section only list labels declare keys; CSS properties and element names in descriptions do not.
        if heading == ".SS Variables\n":
            section = "\n".join(re.findall(r"\.TP\n([^\n]+)", section))
        sections.append(section)
    prose = re.sub(r"^\.[A-Z]+[^\n]*", "", text, flags=re.MULTILINE)
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(prose.split())):
        if re.search(r"metadata (?:field|key)", sentence):
            sections.append(sentence)
    keys = set()
    for section in sections:
        plain = section.replace(r"\-", "-")
        keys.update(re.findall(r"\\f\[CR\]([A-Za-z][A-Za-z0-9_-]*)\\f\[R\]", plain))
        keys.update(re.findall(r"^([A-Za-z][A-Za-z0-9_-]*):", plain, re.MULTILINE))
    return sorted(keys)


def quarto_keys(path):
    if path is None:
        return None
    definitions = json.loads(path.read_text(encoding="utf-8"))

    def keys(schema, seen=frozenset()):
        result = set(schema.get("properties", {}))
        if schema.get("type") == "ref":
            reference = schema["$ref"]
            if reference not in seen:
                result.update(keys(definitions[reference], seen | {reference}))
        for operator in ("anyOf", "allOf", "oneOf"):
            for child in schema.get(operator, []):
                result.update(keys(child, seen))
        return result

    try:
        found = keys(definitions["front-matter"])
    except (KeyError, TypeError) as error:
        raise SystemExit(f"Unrecognised Quarto front-matter schema: {error}") from error
    # These structural anchors verify that this is a front-matter schema, rather than a format-only subset.
    if not {"engine", "format", "execute", "jupyter", "knitr", "filters"} <= found:
        raise SystemExit("Incomplete Quarto front-matter schema")
    return sorted(found)


def generate(manual, quarto_schema):
    templates, writers = template_keys()
    return {"pandoc": pandoc("--version").stdout.splitlines()[0], "writers": writers,
            "template_keys": templates, "documented_keys": documented_keys(manual.read_text(encoding="utf-8")),
            "quarto_keys": quarto_keys(quarto_schema)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--manual", type=Path, default=manual_path())
    parser.add_argument("--quarto-schema", type=Path, default=quarto_schema_path())
    parser.add_argument("--output", type=Path, default=TARGET)
    args = parser.parse_args()
    if args.manual is None:
        parser.error("Pandoc's installed manual was not found; use --manual")
    data = generate(args.manual, args.quarto_schema)
    if args.check:
        shipped = json.loads(args.output.read_text(encoding="utf-8"))
        # A machine without Quarto can still check every Pandoc key. A local schema, when present, must match too.
        if args.quarto_schema is None:
            data["quarto_keys"] = shipped["quarto_keys"]
        if data != shipped:
            raise SystemExit("Pandoc/Quarto key data drifted; regenerate with scripts/pandoc_keys.py")
        print("Pandoc/Quarto key data matches the installed sources")
    else:
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

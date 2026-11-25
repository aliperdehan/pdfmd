"""The --excerpts remainder has its own parser and never enters the build path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from pdfmd_base import core
from pdfmd_log import emit
from .discovery import context, discover, bibliography
from .markers import canonical, locations, prefix_setting
from .pages import printed_page
from .record import RecordConflict, RecordError, RecordMissing, positive, read, update, validate
from . import sources


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can echo a passage on conversion/unknown-option errors. Keep diagnostics structural.
        raise UsageError("invalid arguments; use pdfmd --excerpts --help")


def parser():
    common = Parser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="answer as JSON (also on failure)")
    common.add_argument("--in", dest="place", default=argparse.SUPPRESS, metavar="PATH", help="document or project folder")
    common.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS, help="show further record files ignored")
    result = Parser(prog="pdfmd --excerpts", parents=[common], description="Local excerpt records, checks and Markdown citation detachment.",
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = result.add_subparsers(dest="action", required=True, parser_class=Parser)
    for action in ("list", "show", "where", "add", "edit", "remove", "sources", "export", "detach", "check",
                   "reanchor", "renumber", "rekey", "import"):
        sub = actions.add_parser(action, parents=[common])
        if action == "list":
            sub.description = "List excerpt records as a table. Use --json for complete records."
            sub.add_argument("--key")
            sub.add_argument("--unused", action="store_true")
            sub.add_argument("--problems", action="store_true", help="only records with excerpt check problems")
        if action == "reanchor":
            sub.add_argument("key")
        if action == "rekey":
            sub.add_argument("old")
            sub.add_argument("new")
        if action == "import":
            sub.description = ("Import positioned PDF annotations and list Skim text notes without positions. "
                               "When text notes are listed, --json gives separate records and not-imported arrays.")
            sub.add_argument("file", metavar="FILE.pdf")
            sub.add_argument("--key", required=True, help="the key already registered for this source PDF")
            sub.add_argument("--dry-run", action="store_true", help="preview the new records without writing")
        if action in ("show", "where", "edit", "remove"):
            sub.add_argument("id", type=int)
        if action in ("add", "edit"):
            for name in ("key", "page", "locator", "note", "label", "quoting", "remark", "file"):
                sub.add_argument("--" + name)
            sub.add_argument("--kind", choices=("text", "area", "remark"))
            # Preserve option order: each PDF page starts a part, boxes attach to it;
            # each --text starts another part when the current one already has text.
            for name in ("text", "pdf-page", "box"):
                sub.add_argument("--" + name, action="append")
        if action == "remove":
            choices = sub.add_mutually_exclusive_group()
            choices.add_argument("--force", action="store_true")
            choices.add_argument("--detach", action="store_true", help="detach citations before removing the record")
        if action == "detach":
            sub.add_argument("--all", action="store_true", help="detach every excerpt marker in the files")
            sub.add_argument("items", nargs="+", metavar="ID ... FILE")
        if action == "sources":
            verbs = sub.add_subparsers(dest="verb", parser_class=Parser)
            add = verbs.add_parser("add", parents=[common])
            add.add_argument("key")
            add.add_argument("file")
            add.add_argument("--pages", help='JSON anchors, e.g. [[2,"41"]], or labels')
            match = verbs.add_parser("match", parents=[common])
            match.add_argument("directory", nargs="?")
            match.add_argument("--apply", action="store_true")
        if action == "export":
            sub.add_argument("-o", "--out", metavar="FILE")
    result.epilog = action_summary(actions)
    return result


def action_summary(actions) -> str:
    """Every action with its own options, made from the parsers themselves (so `pdfmd --excerpts --help` names every
    option the guide does, and cannot drift from what the actions accept)."""
    def words(sub):
        found = []
        for item in sub._actions:
            if isinstance(item, argparse._SubParsersAction) or "--help" in item.option_strings:
                continue
            if not item.option_strings:
                found.append(item.dest.upper())
            elif max(item.option_strings, key=len) not in ("--json", "--in", "--verbose"):
                name = max(item.option_strings, key=len)
                found.append(f"[{name}]" if item.nargs == 0 else f"[{name} {(item.metavar or item.dest).upper()}]")
        return " ".join(found)
    lines = ["actions and their options (each also takes --json and --in PATH):"]
    for name, sub in actions.choices.items():
        verbs = [item for item in sub._actions if isinstance(item, argparse._SubParsersAction)]
        if verbs:
            lines += [f"  {name} {verb} {words(verb_parser)}".rstrip() for verb, verb_parser in verbs[0].choices.items()]
        else:
            lines.append(f"  {name} {words(sub)}".rstrip())
    return "\n".join(lines)


def parts(arguments):
    """Keep repeated --pdf-page/--box/--text association, including hand-typed pieces."""
    result, current = [], None
    tokens = iter(arguments)
    for token in tokens:
        name, equals, value = token.partition("=")
        if name not in ("--text", "--pdf-page", "--box"):
            continue
        value = value if equals else next(tokens, "")
        if name == "--pdf-page":
            try:
                number = int(value)
            except ValueError:
                raise UsageError("pdf-page must be a positive integer") from None
            if not positive(number):
                raise UsageError("pdf-page must be a positive integer")
            current = {"pdf-page": number}
            result.append(current)
        elif name == "--box":
            if current is None or "pdf-page" not in current:
                raise UsageError("--box needs a preceding --pdf-page")
            try:
                box = [float(number) for number in value.split(",")]
            except ValueError:
                raise UsageError("box must contain four coordinates") from None
            current.setdefault("boxes", []).append(box)
        else:
            if current is None or "text" in current:
                current = {}
                result.append(current)
            current.update({"text": value.replace("\n", " ").replace("\r", " "), "text-from": "typed"})
    return result


def find(data, ident):
    record = next((item for item in data["excerpts"] if item["id"] == ident), None)
    if record is None:
        raise RecordMissing(f"excerpt {ident} is not in excerpts.json")
    return record


def record_fields(args, arguments):
    fields = {key: value for key in ("key", "page", "locator", "note", "label", "quoting", "kind", "file")
              if (value := getattr(args, key)) is not None}
    if args.remark is not None:
        if args.key is not None or args.kind not in (None, "remark"):
            raise UsageError("--remark cannot name a source or another kind")
        fields.update(kind="remark", note=args.remark)
    if any(getattr(args, key) is not None for key in ("text", "pdf_page", "box")):
        fields["parts"] = parts(arguments)
    return fields


def save_record(path, fields, prefix, *, ident=None, remark=False, guard=None):
    def save(data):
        original = find(data, ident) if ident is not None else None
        record = {**(original if original is not None else
                     {"id": data["next-id"], "kind": "text", "page": "", "parts": []}), **fields}
        if remark:
            record.pop("key", None)
            record.pop("page", None)
        if record["kind"] != "remark" and not record.get("key"):
            raise UsageError("add needs --key or --remark")
        if original is not None:
            original.clear()
            original.update(record)
            return original
        data["excerpts"].append(record)
        data["next-id"] += 1
        validate(data)
        if "page" not in fields and record.get("parts"):
            number = record["parts"][0].get("pdf-page")
            if number is not None:
                source = data["sources"].get(record.get("key"), {})
                if record.get("file"):
                    source = source.get("more", {}).get(record["file"], {})
                hint = Path(source["file"]).expanduser() if source.get("file") else None
                file = path.parent / hint if hint else None
                record["page"] = printed_page(source.get("pages"), number, file)
        current = record["id"]
        markers = [f"[{canonical(current, None, prefix)}]"]
        if record.get("key"):
            markers.append(f"[{canonical(current, record['key'], prefix)}]")
        return {"id": current, "markers": markers}
    return update(path, save, guard=guard)


def add_source(path, key, file, mapping, *, guard=None):
    source = sources.identity(file, path.parent, mapping)

    def add(data):
        old = data["sources"].get(key, {})
        # An extra file needs a supplement name; never silently replace the primary.
        if old.get("file") and (path.parent / old["file"]).resolve() != file:
            raise RecordConflict("key already has a different source; name a supplement in excerpts.json")
        data["sources"][key] = {**old, **source}
        return data["sources"][key]
    return update(path, add, guard=guard)


def remove_record(path, ident, place, entries, *, force=False, detach=False, guard=None):
    def remove(current):
        from .detach import files
        record = find(current, ident)
        # Re-scan inside the record lock, so concurrent record writers cannot race this decision.
        if not force:
            cited = locations(Path(place).expanduser().resolve(), path, entries, current, guard=guard, show=str)
            documents = [Path(item["file"]) for item in cited if item["id"] == ident]
            if documents and not detach:
                raise RecordConflict(f"excerpt {ident} is cited; use --detach or --force")
            if documents:
                files(documents, {ident}, selected_path=path, data=current, guard=guard)
        current["excerpts"].remove(record)
        return {"removed": ident}
    return update(path, remove, guard=guard)


def problem_answers(problems):
    return [{"file": item.file, "line": item.line, "severity": item.severity, "code": item.code,
             "message": item.message} for item in problems]


def sheet(data, places):
    lines = ["# Excerpt review", ""]
    keys = sorted({item.get("key", "") for item in data["excerpts"]})
    for key in keys:
        lines += ["## " + (key or "Remarks"), ""]
        for record in sorted(data["excerpts"], key=lambda item: item["id"]):
            if record.get("key", "") != key:
                continue
            lines += [f"### Excerpt {record['id']}" + (" — " + record["page"] if record.get("page") else ""), ""]
            for field in ("label", "locator", "quoting", "note"):
                if record.get(field):
                    lines += [field.capitalize() + ": " + record[field], ""]
            for part in record.get("parts", []):
                if part.get("text"):
                    lines += ["> " + part["text"].replace("\n", "\n> "), ""]
            cited = [f"{place['file']}:{place['line']}" for place in places if place["id"] == record["id"]]
            lines += ["Cited: " + (", ".join(cited) or "not cited"), ""]
    return "\n".join(lines)


def execute(args, arguments):
    if args.action == "detach":
        from .detach import files
        ids, names = set(), list(args.items)
        while names and names[0].isdecimal():
            ids.add(int(names.pop(0)))
        if not names or args.all == bool(ids) or 0 in ids:
            raise UsageError("detach needs IDs or --all, followed by Markdown files")
        selected = discover(*context(args.place)) if args.place != "." else None
        return files(names, ids or None, selected_path=selected)

    document, metadata = context(args.place)
    if args.action == "check":
        from .checks import file_problem, project_checks
        try:
            path = discover(document, metadata, args.verbose)
            data = read(path)
        except RecordError as error:
            problems = [file_problem(document, str(error))]
        except OSError:
            problems = [file_problem(document, "cannot read the record file")]
        else:
            problems = project_checks(args.place, path, data)[0]
        return problem_answers(problems)
    path = discover(document, metadata, args.verbose)
    if args.action == "import":
        from .import_pdf import import_annotations
        records, not_imported = import_annotations(path, args.file, args.key, dry_run=args.dry_run)
        return {"records": records, "not-imported": not_imported} if not_imported else records
    if args.action == "reanchor":
        from .anchors import reanchor
        return reanchor(path, args.key)
    if args.action in ("renumber", "rekey"):
        from .repairs import renumber, rekey
        return renumber(args.place, path) if args.action == "renumber" else rekey(args.place, path, args.old, args.new)
    prefix = prefix_setting(document, metadata)
    if args.action in ("add", "edit"):
        return save_record(path, record_fields(args, arguments), prefix,
                           ident=getattr(args, "id", None), remark=args.remark is not None)
    if args.action == "sources" and args.verb == "add":
        try:
            mapping = ("labels" if args.pages == "labels" else json.loads(args.pages)) if args.pages is not None else None
        except ValueError:
            raise UsageError("--pages needs JSON anchors or labels") from None
        return add_source(path, args.key, Path(args.file).expanduser().resolve(), mapping)

    data = read(path, create=args.action == "sources" and args.verb == "match")
    if args.action == "show":
        return find(data, args.id)
    if args.action == "sources":
        if args.verb is None:
            return sources.states(data, path.parent)
        directory = Path(args.directory).expanduser().resolve() if args.directory else document.parent
        if not directory.is_dir():
            raise RecordError("source search directory does not exist")
        proposals = sources.match(bibliography(document, metadata), directory, path.parent)
        if args.apply:
            if any(not proposal["apply"] for proposal in proposals):
                raise RecordError("source matches need a choice; review sources match and use sources add")
            def apply(current):
                for proposal in proposals:
                    candidate = proposal["candidates"][0]
                    key = proposal["key"]
                    old = current["sources"].get(key, {})
                    if old.get("file") and (path.parent / old["file"]).resolve() != (path.parent / candidate["file"]).resolve():
                        raise RecordError("source match would replace a different file; review excerpts.json")
                    current["sources"][key] = {**old, **sources.identity(path.parent / candidate["file"], path.parent, candidate.get("pages"))}
                return proposals
            return update(path, apply)
        return proposals
    if args.action == "list" and args.problems:
        from .checks import project_checks
        _, used, affected = project_checks(args.place, path, data)
        return [item for item in sorted(data["excerpts"], key=lambda item: item["id"])
                if item["id"] in affected and (args.key is None or args.key == item.get("key"))
                and (not args.unused or item["id"] not in used)]
    if args.action == "remove":
        return remove_record(path, args.id, args.place, bibliography(document, metadata) if not args.force else {},
                             force=args.force, detach=args.detach)
    if args.action == "list" and not args.unused:
        return [item for item in sorted(data["excerpts"], key=lambda item: item["id"])
                if args.key is None or args.key == item.get("key")]
    places = locations(Path(args.place).expanduser().resolve(), path, bibliography(document, metadata), data)
    if args.action == "where":
        find(data, args.id)
        return [place for place in places if place["id"] == args.id]
    if args.action == "list":
        used = {place["id"] for place in places}
        return [item for item in sorted(data["excerpts"], key=lambda item: item["id"])
                if (args.key is None or args.key == item.get("key")) and (not args.unused or item["id"] not in used)]
    result = sheet(data, places)
    if args.out:
        output = Path(args.out).expanduser().resolve()
        source_files = [path, *(path.parent / source["file"] for source in data["sources"].values() if source.get("file"))]
        source_files += [path.parent / extra["file"] for source in data["sources"].values()
                         for extra in source.get("more", {}).values() if extra.get("file")]
        if output in [item.resolve() for item in source_files]:
            raise RecordError("export cannot overwrite the record file or a source PDF")
        core.atomic_write_text(output, result, newline="\n")
    return {"markdown": result}


def print_records(records):
    """Print a compact record index, using terminal cells for alignment and clipping."""
    if not records:
        print("No excerpt records.")
        return

    from pdfmd_ansi.text import char_width, clean, text_width

    def shorten(value, width):
        if text_width(value) <= width:
            return value
        remaining = width - 1  # reserve a cell for the ellipsis
        for end, char in enumerate(value):
            remaining -= char_width(char)
            if remaining < 0:
                return value[:end] + "…"

    # Use only known summary fields. Passages, annotations and unknown extensions stay in the full record.
    fields = ["id", "key", "page", "kind"]
    fields += [key for key in ("locator", "label", "file", "created") if any(key in record for record in records)]
    rows = [fields] + [[clean(" ".join(str(record.get(key, "")).split())) for key in fields] for record in records]
    natural = [max(map(text_width, column)) for column in zip(*rows)]
    width = shutil.get_terminal_size().columns if sys.stdout.isatty() else 80
    widths = list(map(len, fields))
    gaps = len(fields) - 1
    gap = "  " if sum(widths) + 2 * gaps <= width else " "
    available = max(len(fields), width - len(gap) * gaps)
    if sum(widths) > available:
        widths = [1] * len(fields)
    for _ in range(min(available, sum(natural)) - sum(widths)):
        column = min((i for i in range(len(fields)) if widths[i] < natural[i]), key=widths.__getitem__)
        widths[column] += 1

    for row in rows:
        cells = [shorten(value, limit) for value, limit in zip(row, widths)]
        line = gap.join(value + " " * (limit - text_width(value)) for value, limit in zip(cells, widths))
        print(shorten(line.rstrip(), width))


def command(arguments):
    # Records and answers are UTF-8 (passages in any script): a pipe on Windows is the ANSI code page otherwise, which
    # cannot write Cyrillic or Greek and makes `—` a byte no UTF-8 reader takes (as `pdfmd --doc` already does)
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty() and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass
    want_json = "--json" in arguments
    try:
        args = parser().parse_args(arguments)
        args.place = getattr(args, "place", ".")
        args.verbose = getattr(args, "verbose", False)
        answer = execute(args, arguments)
    except (UsageError, RecordError, OSError, UnicodeError) as error:
        code = 2 if isinstance(error, UsageError) else 1
        # OS messages can contain local paths; the command's public diagnostic stays structural.
        message = str(error) if isinstance(error, (UsageError, RecordError)) else "cannot read or write an excerpt command file"
        if want_json:
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print("excerpts: " + message, file=sys.stderr)
        return code
    if want_json:
        print(json.dumps(answer, ensure_ascii=False))
    elif args.action == "list":
        print_records(answer)
    elif args.action == "export":
        if not args.out:
            print(answer["markdown"], end="")
        else:
            print("Excerpt review written.")
    elif args.action == "add":
        print(str(answer["id"]) + " " + " ".join(answer["markers"]))
    elif args.action == "import" and isinstance(answer, dict):
        if answer["records"]:
            print(json.dumps(answer["records"], ensure_ascii=False, indent=2))
        for note in answer["not-imported"]:
            print(f"{note['heading']} ({note['status']})")
            print(note["text"])
    elif args.action == "check":
        for item in answer:
            place = f"{item['file']}:{item['line']}" if item["line"] else item["file"]
            emit(item['severity'], item['code'], f"{place}: {item['severity']}: {item['message']}  [{item['code']}]")
        if not answer:
            print("CHECK  excerpts: no problems")
    else:
        print(json.dumps(answer, ensure_ascii=False, indent=2))
    if args.action == "check":
        return int(any(item["severity"] != "note" for item in answer))
    if args.action == "reanchor":
        return int(any(item["state"] in ("missing", "review") for item in answer))
    return 0

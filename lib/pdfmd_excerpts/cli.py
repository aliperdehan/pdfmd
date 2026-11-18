"""The --excerpts remainder has its own parser and never enters the build path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pdfmd_base import core
from .discovery import context, discover, bibliography
from .markers import locations
from .pages import printed_page
from .record import RecordError, positive, read, update
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
    result = Parser(prog="pdfmd --excerpts", parents=[common], description="Local excerpt records; no build changes in P1b.",
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = result.add_subparsers(dest="action", required=True, parser_class=Parser)
    for action in ("list", "show", "where", "add", "edit", "remove", "sources", "export"):
        sub = actions.add_parser(action, parents=[common])
        if action == "list":
            sub.add_argument("--key")
            sub.add_argument("--unused", action="store_true")
            sub.add_argument("--problems", action="store_true", help="requires the P1d checks (not available yet)")
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
            choices.add_argument("--detach", action="store_true", help="requires the P1c resolver (not available yet)")
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
        raise RecordError(f"excerpt {ident} is not in excerpts.json")
    return record


def make_record(args, arguments, data, path, original=None):
    record = dict(original) if original else {"id": data["next-id"], "kind": "text", "page": "", "parts": []}
    for key in ("key", "page", "locator", "note", "label", "quoting", "kind", "file"):
        value = getattr(args, key)
        if value is not None:
            record[key] = value
    if args.remark is not None:
        if args.key is not None or args.kind not in (None, "remark"):
            raise UsageError("--remark cannot name a source or another kind")
        record["kind"], record["note"] = "remark", args.remark
        record.pop("key", None)
        record.pop("page", None)
    if any(getattr(args, key) is not None for key in ("text", "pdf_page", "box")):
        record["parts"] = parts(arguments)
    if record["kind"] != "remark" and not record.get("key"):
        raise UsageError("add needs --key or --remark")
    if args.page is None and not original and record.get("parts"):
        number = record["parts"][0].get("pdf-page")
        source = data["sources"].get(record.get("key"), {})
        if record.get("file"):
            source = source.get("more", {}).get(record["file"], {})
        if number is not None:
            hint = Path(source["file"]).expanduser() if source.get("file") else None
            record["page"] = printed_page(source.get("pages"), number, path.parent / hint if hint else None)
    return record


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
    document, metadata = context(args.place)
    path = discover(document, metadata, args.verbose)
    entries = bibliography(document, metadata)
    if args.action == "add":
        def add(data):
            record = make_record(args, arguments, data, path)
            data["excerpts"].append(record)
            data["next-id"] += 1
            ident = record["id"]
            markers = [f"[@x:{ident}]"]
            if record.get("key"):
                markers.append(f"[@{record['key']}#{ident}]")
            return {"id": ident, "markers": markers}
        return update(path, add)
    if args.action == "edit":
        def edit(data):
            record = find(data, args.id)
            replacement = make_record(args, arguments, data, path, record)
            record.clear()
            record.update(replacement)
            return record
        return update(path, edit)
    if args.action == "sources" and args.verb == "add":
        try:
            mapping = ("labels" if args.pages == "labels" else json.loads(args.pages)) if args.pages is not None else None
        except ValueError:
            raise UsageError("--pages needs JSON anchors or labels") from None
        source = sources.identity(Path(args.file).expanduser().resolve(), path.parent, mapping)
        def add_source(data):
            old = data["sources"].get(args.key, {})
            # An extra file needs a supplement name; never silently replace the primary.
            if old.get("file") and (path.parent / old["file"]).resolve() != Path(args.file).expanduser().resolve():
                raise RecordError("key already has a different source; name a supplement in excerpts.json")
            data["sources"][args.key] = {**old, **source}
            return data["sources"][args.key]
        return update(path, add_source)

    data = read(path, create=args.action == "sources" and args.verb == "match")
    if args.action == "show":
        return find(data, args.id)
    if args.action == "sources":
        if args.verb is None:
            return sources.states(data, path.parent)
        directory = Path(args.directory).expanduser().resolve() if args.directory else document.parent
        if not directory.is_dir():
            raise RecordError("source search directory does not exist")
        proposals = sources.match(entries, directory, path.parent)
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
        raise UsageError("--problems needs P1d excerpt checks; not available in P1b")
    if args.action == "remove":
        if args.detach:
            raise UsageError("--detach needs the P1c resolver; not available in P1b")
        def remove(current):
            record = find(current, args.id)
            # Re-scan inside the record lock, so concurrent record writers cannot race this decision.
            if not args.force:
                cited = locations(Path(args.place).expanduser().resolve(), path, entries)
                if any(place["id"] == args.id for place in cited):
                    raise RecordError(f"excerpt {args.id} is cited; use --force (detach follows in P1c)")
            current["excerpts"].remove(record)
            return {"removed": args.id}
        return update(path, remove)
    if args.action == "list" and not args.unused:
        return [item for item in sorted(data["excerpts"], key=lambda item: item["id"])
                if args.key is None or args.key == item.get("key")]
    places = locations(Path(args.place).expanduser().resolve(), path, entries)
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


def command(arguments):
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
    elif args.action == "export":
        if not args.out:
            print(answer["markdown"], end="")
        else:
            print("Excerpt review written.")
    elif args.action == "add":
        print(str(answer["id"]) + " " + " ".join(answer["markers"]))
    else:
        print(json.dumps(answer, ensure_ascii=False, indent=2))
    return 0

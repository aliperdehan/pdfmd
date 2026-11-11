"""The Word, OpenDocument and PowerPoint build that `pdfmd.py` drives: where a house style's profile, defaults and reference document
are looked for (`office_package_folders`, `office_defaults_sources`, `find_office_profile`, `find_reference_doc`), the Pandoc arguments
of an office build (`OfficeArguments`), the Pandoc runs and what finishes the file afterwards (`run_office_pandoc`,
`build_office_pandoc`, `office_finish`, `office_properties`), the LaTeX that is drawn as pictures (`office_render_fragments`,
`office_convert_asset`), `--check-docx` (`check_docx_command`, `print_office_check`, `describe_fragment`) and `--init-reference`
(`init_reference`).

Moved out of `pdfmd.py` unchanged (v3.33.27, SPLIT.md). `core` is the `pdfmd` module, bound when the module is first loaded (a
stand-in in `pdfmd.py` loads it on the first call; the first binding wins); the pdfmd names the code uses (`LATEX_ENGINES`,
`OFFICE_REFERENCE_EXTENSIONS`, `__file__` -- `pdfmd.py` itself, which `--check-docx` runs as a child --, `accessory_directories`,
`cache_root`, `config_root`, `display_path`, `find_markdown`, `installed_engines`, `log_cmd`, `office_module`, `office_packages`,
`office_pdfmd_command`, `package_helper`, `package_places`, `run_tex_engine`, `tex_search_env`, `vprint` and `which`) are read as
`core.X` when it runs. `core.cache_root`, `core.config_root` and `core.which` are patched by tests as `pdfmd.X`. `office_finish`,
`run_office_pandoc`, `OfficeArguments` and the rest that `pdfmd.py` or `lib/pdfmd_report` call are reached through the stand-ins there.
`__file__` in this module is its own; `office_module()` stays in `pdfmd.py` and loads the package's `__init__`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    from pdfmd_yaml_support import yaml
except ImportError:                                # pragma: no cover -- incomplete installation
    yaml = None

core = None


def office_package_folders(md_path: Path, metadata_files: list[Path], no_auto: list[str] | None = None
                           ) -> list[tuple[Path, str]]:
    """(folder, package) of each local LaTeX package the preamble loads; see office_packages."""
    return [(folder, package) for folder, package, _ in core.office_packages(md_path, metadata_files, no_auto)]


def office_defaults_sources(folder: Path, package: str, no_auto: list[str] | None = None) -> list[tuple[dict, Path]]:
    """(mapping, its file) for each place a package keeps defaults of a Word/ODT build, best first:
    `<package>-office.yaml` (beside the `.sty`, in `office/` or `pdfmd/`), then the `office:` section of
    `<package>-pdfmd.yaml`."""
    sources: list[tuple[dict, Path]] = []
    if yaml is None:
        return sources
    for place in core.package_places(folder):
        candidate = place / f"{package}-office.yaml"
        if candidate.is_file():
            try:
                data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                data = None
            if isinstance(data, dict):
                sources.append((data, candidate))
    helper = core.package_helper(folder, package, no_auto)
    if helper and isinstance(helper[0].get("office"), dict):
        sources.append((dict(helper[0]["office"]), helper[1]))
    return sources


def find_office_profile(md_path: Path, metadata_files: list[Path], options: dict,
                        packages: list[tuple[Path, str]] = ()) -> Path | None:
    """A house style's Word profile: `office: {profile: FILE}`, else `<name>-office.lua`, `office.lua` or
    `<package>-office.lua` (of a package the document loads) beside the document, in its metadata/ folder or beside its
    metadata files, else in the config folder. A Lua file that says which of the style's own macros mean what in a Word file."""
    named = options.get("profile")
    if isinstance(named, str) and named.strip():
        path = Path(named).expanduser()
        path = path if path.is_absolute() else md_path.parent / path
        if not path.is_file():
            raise SystemExit(f"{md_path}: office.profile {named!r} does not exist")
        return path.resolve()
    folders = [*core.accessory_directories(md_path.parent, md_path.stem)]
    folders += [path.parent for path in metadata_files if path.parent not in folders]
    folders.append(core.config_root())
    for folder in folders:
        for name in (f"{md_path.stem}-office.lua", "office.lua", *(f"{package}-office.lua" for _, package in packages)):
            if (folder / name).is_file():
                return (folder / name).resolve()
    for folder, package in packages:
        for subfolder in core.package_places(folder):
            if (subfolder / f"{package}-office.lua").is_file():
                return (subfolder / f"{package}-office.lua").resolve()
    return None


def find_reference_doc(md_path: Path, metadata_files: list[Path], target: str, output: Path,
                       options: dict, packages: list[tuple[Path, str]] = ()) -> tuple[Path | None, str]:
    """(reference document, where it came from) for a docx/odt/pptx build, or (None, '')."""
    extensions = core.OFFICE_REFERENCE_EXTENSIONS[target]
    named = options.get("reference-doc")
    if isinstance(named, str) and named.strip():
        path = Path(named).expanduser()
        path = path if path.is_absolute() else md_path.parent / path
        if not path.is_file():
            raise SystemExit(f"{md_path}: office.reference-doc {named!r} does not exist")
        return path.resolve(), "office: reference-doc"
    folders = [*core.accessory_directories(md_path.parent, md_path.stem)]
    folders += [path.parent for path in metadata_files if path.parent not in folders]
    for folder in folders:
        for name in (f"{md_path.stem}-reference", "reference"):
            for extension in extensions:
                candidate = folder / f"{name}.{extension}"
                if candidate.is_file() and candidate.resolve() != output.resolve():
                    return candidate.resolve(), f"found {core.display_path(candidate)}"
    for extension in extensions:
        candidate = core.config_root() / f"reference.{extension}"
        if candidate.is_file():
            return candidate, f"found {candidate} (the config folder)"
    for folder, package in packages:
        for subfolder in core.package_places(folder):
            for name in (f"{package}-reference", "reference"):
                for extension in extensions:
                    candidate = subfolder / f"{name}.{extension}"
                    if candidate.is_file():
                        return candidate.resolve(), f"found {candidate} (shipped with the {package} package)"
    return None, ""


class OfficeArguments(list):
    """The Pandoc arguments an office build adds, and where its Lua filter reports what it left out."""
    report: Path | None = None
    filter_arguments: list[str] = []      # the Lua filter: added after every other filter
    scratch: Path | None = None
    context: dict = {}


def office_properties(arguments, md_path: Path, data: dict) -> None:
    """A Word, OpenDocument or PowerPoint file's properties, the LaTeX filter's or not (v3.28.5): none of pdfmd's own
    settings (`pdfmd-office-path`, `pdfmd-raw-cache`: folders of this machine) among its custom properties, no folder
    of this machine in a picture's description (the name of the file alone), and the title and authors a house style's
    cover took out of the metadata in an empty Title and Author."""
    output = ((getattr(arguments, "context", None) or {}).get("output"))
    module = core.office_module()
    if module is None or output is None or Path(output).suffix.lower() not in (".docx", ".odt", ".pptx") \
            or not Path(output).is_file():
        return
    kept = data.get("properties") if isinstance(data.get("properties"), dict) else {}
    title = kept.get("title") if isinstance(kept.get("title"), str) else None
    authors = [name for name in kept.get("author") or [] if isinstance(name, str)] if isinstance(
        kept.get("author"), list) else []
    # a picture pdfmd drew is a file in its cache, and Pandoc writes its source into a Word picture's description
    folders = []
    for folder in (Path.home(), core.cache_root(), Path(tempfile.gettempdir())):
        folders += [str(folder), str(folder.resolve())]
    try:
        module.finish_properties(Path(output), title, authors, folders)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
        print(f"WARN  {md_path}: could not finish the properties of {Path(output).name} ({error})", file=sys.stderr)


def office_finish(arguments, md_path: Path, verbose: bool) -> None:
    """After the Pandoc run: the file's properties finished (office_properties), and what the LaTeX filter could not
    make native said."""
    report = getattr(arguments, "report", None)
    data: dict = {}
    if report is not None and report.is_file():
        try:
            loaded = json.loads(report.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            pass
    office_properties(arguments, md_path, data)
    if not data:
        return
    left = data.get("left_over") or []
    done = int(data.get("math", 0)) + int(data.get("native", 0))
    if done:
        core.vprint(verbose, f"OFFICE  {md_path}: {data.get('math', 0)} formula(s) and {data.get('native', 0)} LaTeX piece(s) made native")
    if data.get("chem_calls"):
        core.vprint(verbose, f"OFFICE  {md_path}: \\ce and siunitx converted in {data['chem_calls']} call(s) of pdfmd_chem")
    if left:
        kinds: dict[str, int] = {}
        for item in left:
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        target = (getattr(arguments, "context", None) or {}).get("target", "docx")
        name = {"docx": "Word", "odt": "OpenDocument", "typst": "Typst", "html": "HTML"}.get(target, target)
        print(f"WARN  {md_path}: LaTeX the {name} output could not express: "
              + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items())), file=sys.stderr)
        for item in left[:20]:
            core.vprint(verbose, f"      {item['kind']}: {' '.join(item['tex'].split())[:110]}", file=sys.stderr)


def run_office_pandoc(cmd: list[str], output: Path, arguments, pandoc_cwd: Path, verbose: bool, debug: bool = False):
    """The Pandoc command of a docx/odt build (see build_office_pandoc), and then the one finishing every Word
    file it writes, the soffice route's included: the tables pdfmd styles are centred in the file itself."""
    result = build_office_pandoc(cmd, output, arguments, pandoc_cwd, verbose, debug)
    target = Path(cmd[cmd.index("-o") + 1]) if "-o" in cmd else None
    module = core.office_module()
    if result.returncode == 0 and module is not None and target is not None and target.suffix.lower() == ".odt":
        path = target if target.is_absolute() else pandoc_cwd / target
        if path.is_file():
            try:
                module.finish_odt(path)
            except (OSError, zipfile.BadZipFile, KeyError) as error:
                print(f"WARN  could not finish the styles of {path.name} ({error})", file=sys.stderr)
    if result.returncode == 0 and module is not None and target is not None and target.suffix.lower() == ".docx":
        path = target if target.is_absolute() else pandoc_cwd / target
        if path.is_file():
            try:
                module.centre_tables(path)
            except (OSError, zipfile.BadZipFile, KeyError) as error:
                print(f"WARN  could not centre the tables of {path.name} ({error})", file=sys.stderr)
            try:
                module.finish_markup(path)
            except (OSError, zipfile.BadZipFile, KeyError) as error:
                print(f"WARN  could not finish the markup of {path.name} ({error})", file=sys.stderr)
    return result


def build_office_pandoc(cmd: list[str], output: Path, arguments, pandoc_cwd: Path, verbose: bool, debug: bool = False):
    """Run the Pandoc command of a docx/odt build. With the LaTeX filter on it runs twice: once to list the
    fragments LaTeX must draw (compiled in the document's own preamble, cached), once to put their
    pictures in; a `.docx` is then finished (SVG beside the PNG, baselines, widths)."""
    def run(command: list[str]):
        core.log_cmd(command, pandoc_cwd, verbose)    # each run, the plain one too (v3.33.60: --verbose missed it)
        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=pandoc_cwd)

    module = core.office_module()
    context = arguments.context if hasattr(arguments, "context") else {}
    if module is None or not arguments.filter_arguments or not context or "-o" not in cmd:
        return run(cmd)
    scratch = arguments.scratch
    target = context["target"]
    first = list(cmd)
    if output.suffix.lower() == ".pdf":
        # the first run only lists fragments: write the engine's own source format instead of building a PDF
        engine = next((item.split("=", 1)[1] for item in first if item.startswith("--pdf-engine=")), "")
        if "--pdf-engine" in first:
            engine = first[first.index("--pdf-engine") + 1]
        first = [item for item in first if not item.startswith("--pdf-engine=")]
        if "--pdf-engine" in first:
            index = first.index("--pdf-engine")
            del first[index:index + 2]
        writer = "typst" if engine == "typst" else "html5"
        first += ["-t", writer]
        suffix = ".typ" if writer == "typst" else ".html"
    else:
        suffix = output.suffix
    first[first.index("-o") + 1] = str(scratch / f"pass1{suffix}")
    wanted_path = scratch / "wanted.json"
    first += ["-M", "pdfmd-office-mode=collect", "-M", f"pdfmd-office-wanted={wanted_path}"]
    result = run(first)
    if result.returncode != 0 or not wanted_path.is_file():
        return result
    try:
        items = json.loads(wanted_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    if os.environ.get("PDFMD_OFFICE_CHECK"):
        # `pdfmd --check-docx`: say what the Word file would draw as pictures; draw nothing
        print_office_check(context["md_path"], items, arguments.report)
        first_output = scratch / f"pass1{suffix}"
        if first_output.is_file():
            shutil.copyfile(first_output, output)
        return result
    if not items:
        return run(cmd)
    store, failures = office_render_fragments(items, arguments, pandoc_cwd, verbose, debug)
    final = list(cmd) + ["-M", "pdfmd-office-mode=render", "-M", f"pdfmd-office-fragments={store}"]
    result = run(final)
    for item in items:
        if item["id"] in failures:
            excerpt = " ".join(item["tex"].split())[:90]
            print(f"WARN  {context['md_path']}: could not draw a LaTeX {item['kind']} ({failures[item['id']]}): {excerpt}",
                  file=sys.stderr)
    if result.returncode == 0 and target == "docx" and output.is_file():
        try:
            done = module.finish_docx(output)
        except (OSError, zipfile.BadZipFile, KeyError) as error:
            print(f"WARN  {context['md_path']}: could not finish the pictures in {output.name} ({error})", file=sys.stderr)
            done = 0
        if done:
            core.vprint(verbose, f"OFFICE  {context['md_path']}: {done} LaTeX picture(s) drawn by LaTeX and embedded (SVG with PNG fallback)")
    return result


def describe_fragment(item: dict) -> str:
    """What a fragment is, in a few words: the environment or macro that made it a picture."""
    tex = item["tex"].strip()
    kind = item["kind"]
    if kind in ("math-inline", "math-display"):
        return "math Word cannot convert"
    if kind == "asset":
        return "a PDF/SVG image converted to PNG"
    found = re.match(r"\\begin\{(\w+)\*?\}", tex)
    if found:
        return f"the {found.group(1)} environment"
    found = re.match(r"\\(\w+)", tex)
    if found:
        return f"the macro \\{found.group(1)}"
    return "LaTeX only LaTeX draws" if kind == "block" else "an inline LaTeX piece"


def print_office_check(md_path: Path, items: list[dict], report: Path | None) -> None:
    """`--check-docx`: what the Word build of `md_path` makes native, what it draws as a picture and what it cannot."""
    data: dict = {}
    if report is not None and report.is_file():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    pictures = [item for item in items if item["kind"] != "asset"]
    assets = [item for item in items if item["kind"] == "asset"]
    print(f"CHECK  {core.display_path(md_path)} as a Word file:")
    print(f"  native and editable: {data.get('math', 0)} formula(s), {data.get('native', 0)} other LaTeX piece(s)"
          " (units, chemistry, references, tables, lists...)")
    if not pictures:
        print("  pictures drawn by LaTeX: none")
    else:
        print(f"  pictures drawn by LaTeX: {len(pictures)} (vector with a PNG fallback; not editable in Word)")
        for item in pictures:
            print(f"    {item['kind']:<12} {describe_fragment(item):<34} {' '.join(item['tex'].split())[:70]}")
    if assets:
        print(f"  images converted for Word (PDF/SVG to PNG): {len(assets)}")
    if pictures:
        print("  To make a macro native, the package's office profile (`<package>-office.lua`) can give it a recipe; "
              "see the README, `LaTeX in the document`.")


def check_docx_command(args, pandoc_options: list[str]) -> int:
    """`pdfmd --check-docx FILE...`: the Word build's first pass only, reported (nothing is drawn or written)."""
    status = 0
    for target in (args.path or [Path.cwd()]):
        try:
            document = core.find_markdown(target)
        except FileNotFoundError as error:
            print(str(error), file=sys.stderr)
            status = 1
            continue
        with tempfile.TemporaryDirectory(prefix="pdfmd-check-") as scratch:
            command = [sys.executable, str(Path(core.__file__).resolve()), str(document), "--to", "docx",
                       "-o", str(Path(scratch) / f"{document.stem}.docx"), "--no-stamp", "--no-backup", "--rewrite"]
            for variable in args.variable or []:
                command += ["-V", variable]
            if args.metadata_file is not None:
                command += ["-y", *map(str, args.metadata_file)]
            if args.no_auto is not None:
                command += ["--no-auto", *args.no_auto]
            command += pandoc_options
            done = subprocess.run(command, env={**os.environ, "PDFMD_OFFICE_CHECK": "1"}, capture_output=True, encoding="utf-8", errors="replace")
            print(done.stdout.rstrip())
            sys.stderr.write(done.stderr)
            status = max(status, done.returncode)
    return status


def asset_store_key(assets: list[dict], folders: list[Path]) -> str:
    """Separate stores by resolved sources and their contents, including missing assets."""
    digest = hashlib.sha256()
    for item in sorted(assets, key=lambda asset: asset["id"]):
        name = item["tex"]
        path = next((folder / name for folder in folders if (folder / name).is_file()), None)
        for value in (item["id"], name, str(path.resolve()) if path else ""):
            digest.update(value.encode("utf-8", "surrogateescape"))
            digest.update(b"\0")
        if path is not None:
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def office_render_fragments(items: list[dict], arguments, pandoc_cwd: Path, verbose: bool,
                            debug: bool) -> tuple[Path, dict[str, str]]:
    """Draw the fragments in `items` that are not cached yet; returns the folder holding their pictures
    and {id: reason} for those that would not compile."""
    module = core.office_module()
    context = arguments.context
    md_path, metadata_files = context["md_path"], context["metadata_files"]
    scratch = arguments.scratch
    note = context["note"]
    failures: dict[str, str] = {}
    root = core.cache_root() / "office"
    if not module.fragments.tools_available():
        print("WARN  LaTeX the Word output cannot express is left out: drawing it needs pdftocairo "
              "(Poppler: `pdfmd --install batchocr` explains how to get it)", file=sys.stderr)
        return root / "none", {item["id"]: "pdftocairo is missing" for item in items}
    engines = [engine for engine in core.installed_engines() if engine in core.LATEX_ENGINES
               and engine not in ("context", "latexmk", "tectonic")]
    latex_items = [item for item in items if item["kind"] != "asset"]
    assets = [item for item in items if item["kind"] == "asset"]
    preamble = ""
    store = root / "assets"
    if latex_items:
        if not engines:
            print("WARN  LaTeX the Word output cannot express is left out: there is no LaTeX engine "
                  "(lualatex, xelatex or pdflatex)", file=sys.stderr)
            failures.update({item["id"]: "no LaTeX engine" for item in latex_items})
            latex_items = []
        else:
            tex_file = scratch / "fragments-preamble.tex"
            command = core.office_pdfmd_command(md_path, metadata_files, context["variables"], context["no_auto"],
                                           "--to", "latex", "-o", str(tex_file))
            done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            text = tex_file.read_text(encoding="utf-8") if tex_file.is_file() else ""
            preamble = module.fragments.preamble_of(text) or ""
            if done.returncode != 0 or not preamble:
                print("WARN  LaTeX the Word output cannot express is left out: the document's LaTeX preamble "
                      "could not be made", file=sys.stderr)
                failures.update({item["id"]: "no preamble" for item in latex_items})
                latex_items = []
    labels_aux = scratch / "labels.aux"
    labels_text = labels_aux.read_text(encoding="utf-8") if labels_aux.is_file() else ""
    key = module.fragments.store_key(preamble, engines[0] if engines else "", labels_text)
    store = root / key
    if assets:
        store /= asset_store_key(assets, [pandoc_cwd, md_path.parent, md_path.parent / "metadata"])
    store.mkdir(parents=True, exist_ok=True)
    os.utime(store)
    todo = [item for item in latex_items if not (store / f"{item['id']}.json").is_file()]
    if todo:
        note("OFFICE", f"{md_path}: drawing {len(todo)} LaTeX fragment(s) with {engines[0]}"
                       f" ({len(latex_items) - len(todo)} cached)")
        pandoc_work = pandoc_cwd
        tex_env = core.tex_search_env(md_path.parent, pandoc_work, md_path)
        work = scratch / "fragments"
        work.mkdir(exist_ok=True)

        def compile_tex(tex_path: Path, pdf: Path) -> tuple[bool, str]:
            # one engine, no retries: fragments are drawn in the font the PDF uses or not at all
            ok, reason = core.run_tex_engine(engines[0], tex_path, tex_path.parent, verbose, cwd=pandoc_work, env=tex_env)
            if ok and not (tex_path.parent / f"{tex_path.stem}.pdf").is_file():
                ok, reason = False, "no PDF"
            if not ok:
                log = tex_path.parent / f"{tex_path.stem}.log"
                reason = module.fragments.first_error(log.read_text(encoding="utf-8", errors="replace")) if log.is_file() else reason
            return ok, reason
        failures.update(module.fragments.render(todo, preamble, labels_aux if labels_text else None, work, store,
                                                compile_tex))
    for item in assets:
        ok, reason = office_convert_asset(item, [pandoc_cwd, md_path.parent, md_path.parent / "metadata"], store, scratch)
        if not ok:
            failures[item["id"]] = reason
    return store, failures


def office_convert_asset(item: dict, folders: list[Path], store: Path, scratch: Path) -> tuple[bool, str]:
    """A PDF/EPS picture as SVG and PNG, converted again when the file is newer than its cached copy."""
    name = item["tex"]
    path = next((folder / name for folder in folders if (folder / name).is_file()), None)
    if path is None:
        return False, "file not found"
    meta = store / f"{item['id']}.json"
    if meta.is_file() and meta.stat().st_mtime >= path.stat().st_mtime:
        return True, ""
    source = path
    if path.suffix.lower() in (".eps", ".ps"):
        source = scratch / f"{item['id']}.pdf"
        converter = core.which("epstopdf")
        command = [converter, f"--outfile={source}", str(path)] if converter else (
            [core.which("gs"), "-q", "-dNOPAUSE", "-dBATCH", "-dEPSCrop", "-sDEVICE=pdfwrite", f"-sOutputFile={source}", str(path)]
            if core.which("gs") else None)
        if command is None or subprocess.run(command, capture_output=True).returncode != 0 or not source.is_file():
            return False, "EPS needs epstopdf or Ghostscript"
    module = core.office_module()
    pictures = module.fragments.convert_pages(source, 1, scratch, jobs=1)
    picture = pictures[0]
    if not Path(picture["svg"]).is_file() or not Path(picture["png"]).is_file():
        return False, "pdftocairo failed"
    svg, png = store / f"{item['id']}.svg", store / f"{item['id']}.png"
    shutil.copyfile(picture["svg"], svg)
    shutil.copyfile(picture["png"], png)
    meta.write_text(json.dumps({"svg": str(svg), "png": str(png), "width": picture["width"],
                                "height": picture["height"], "depth": 0.0, "kind": "asset"}), encoding="utf-8")
    return True, ""


def init_reference(kind: str) -> bool:
    """`pdfmd --init-reference [docx|odt|pptx]`: write reference.<kind> (Pandoc's own, with pdfmd's
    look) into the current folder, ready to be restyled in Word/LibreOffice."""
    module = core.office_module()
    kind = (kind or "docx").lower().lstrip(".")
    if kind not in core.OFFICE_REFERENCE_EXTENSIONS:
        print(f"--init-reference takes docx, odt or pptx, not {kind!r}", file=sys.stderr)
        return False
    target = Path.cwd() / f"reference.{kind}"
    if target.exists():
        print(f"{target.name} exists already; left alone.")
        return True
    try:
        data = module.default_reference(kind)
        if kind != "pptx":
            data = module.patch_reference(kind, data, module.OfficeSpec(), True)
    except (OSError, AttributeError) as error:
        print(f"Could not write {target.name}: {error}", file=sys.stderr)
        return False
    target.write_bytes(data)
    print(f"Wrote {target.name}: Pandoc's styles with pdfmd's look. Edit the styles in Word or LibreOffice "
          f"(Heading 1, Body Text, Title, Table...); pdfmd uses it for every .{kind} it writes beside or below it.")
    return True


def build_reference_numbers(md_path, metadata_files, variables, no_auto, note, scratch):
    """Collect LaTeX counters without inheriting a non-LaTeX route or entering Office conversion again."""
    engines = [engine for engine in core.installed_engines()
               if engine in core.LATEX_ENGINES and engine != "context"]
    if not engines:
        return
    disabled = [] if no_auto == [] else [*(no_auto or ["officeref"]), "officelatex"]
    command = core.office_pdfmd_command(md_path, metadata_files, variables, disabled,
                                       "-e", ",".join(engines), "-o", str(scratch / f"{md_path.stem}.pdf"), "--cache")
    note("OFFICE", f"{md_path}: building the PDF once for its equation, figure and table numbers")
    done = core.timed("PDF for reference numbers")(subprocess.run)(
        command, capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        print(f"WARN  {md_path}: the PDF build for reference numbers failed; numbers are counted "
              "instead (build the PDF to see why)", file=sys.stderr)

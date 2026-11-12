"""DECISION 50: choose the OpenDocument writer before the ordinary build.

Auto uses the complete Word build and the existing LibreOffice converter; an
OpenDocument reference selects Pandoc's styling instead. Only ODT runs load this
module. The caller supplies its build function so the Pandoc fallback cannot
select the route again, and all parts, sections and filters keep their context.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pdfmd_base import core


def engine(md_path: Path, metadata_files: list[Path]) -> str:
    requested = (core.ENGINE_CLI or "").split(",")[0].strip().casefold()
    if requested == "pandoc":
        return "pandoc"
    if core.soffice_asked_first(requested):
        return "soffice"
    settings = core.cascaded_option(md_path, metadata_files, "odt")
    value = settings.get("engine", "auto") if isinstance(settings, dict) else "auto"
    value = str(value).strip().casefold()
    if value not in ("auto", "soffice", "pandoc"):
        raise SystemExit(f"{core.display_path(md_path)}: odt.engine must be auto, soffice or pandoc, not {value!r}")
    return value


def reference(md_path, metadata_files, output, pandoc_options, no_auto):
    """Use the ordinary Office discovery, including named and command-line references."""
    for index, option in enumerate(pandoc_options):
        if option.startswith("--reference-doc="):
            return Path(option.split("=", 1)[1])
        if option == "--reference-doc" and index + 1 < len(pandoc_options):
            return Path(pandoc_options[index + 1])
    if core.auto_disabled(no_auto, "officeref"):
        return None
    return core.find_reference_doc(md_path, metadata_files, "odt", output,
                                   core.office_options(md_path, metadata_files, no_auto),
                                   core.office_package_folders(md_path, metadata_files, no_auto))[0]


def convert(build, md_path: Path, *args, **kwargs):
    values = core.inspect.signature(build).bind(md_path, *args, **kwargs)
    values.apply_defaults()
    given = values.arguments
    metadata = given["metadata_file"]
    metadata = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
    route = engine(md_path, metadata)
    output = given["output_file"] or core.load_package("pdfmd_routing.output").planned(md_path, given["out_dir"], "odt")
    if output.exists() and any(source.exists() and output.samefile(source)
                               for source in [md_path, *(given["extra_inputs"] or [])]):
        raise SystemExit(f"{core.display_path(output)} is the source itself; the odt output would replace it. "
                         "Give another name with -o, or another folder.")
    no_auto = core.effective_no_auto(md_path, given["no_auto"])
    if route == "auto":
        chosen = reference(md_path, metadata, output, given["pandoc_options"], no_auto)
        if chosen and chosen.suffix.lower() in (".odt", ".ott"):
            print(f"NOTE  odt: reference document {core.display_path(chosen)} selects Pandoc's OpenDocument writer",
                  file=sys.stderr)
            route = "pandoc"
    if route == "pandoc":
        return build(**given)
    reason = "LibreOffice was not found"
    if core.resolve_soffice() is not None:
        with tempfile.TemporaryDirectory(prefix="pdfmd-odt-word-") as scratch:
            word = Path(scratch) / "document.docx"
            word_values = {**given, "output_file": word, "target_format": "docx"}
            result = build(**word_values)
            if result[1]:
                ok, reason = core.run_soffice_convert(word, output, given["verbose"], "odt")
                core.BUILD["output"] = output
                if ok:
                    core.record_engine("soffice")
                    return result
            else:
                reason = result[2]
    core.BUILD["output"] = output
    if route == "soffice":
        raise SystemExit(f"odt: {reason}; install LibreOffice to use odt.engine: soffice")
    print(f"WARN  odt: {reason}; using Pandoc's OpenDocument writer, which loses raw Word blocks such as a cover or form "
          "and the Word route's extras; install LibreOffice to keep them", file=sys.stderr)
    return build(**given)

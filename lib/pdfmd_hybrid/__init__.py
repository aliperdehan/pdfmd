"""The hybrid PDF (`--hybrid`): a PDF that carries the document it was made from as an OpenDocument attachment.

`resolve_hybrid`, `odf_source_for`, `attach_hybrid` and `hybrid_after_success` are moved out of `pdfmd.py` unchanged
(v3.33.4, SPLIT.md), with `HYBRID_FAMILY` and `HYBRID_DESCRIPTION`. `core` is the `pdfmd` module, bound by `pdfmd.py` when it
loads (the first binding wins); the package reads `core.HYBRID_CLI` (rebound by `main()`), `core.HYBRID_MIME` (also read by
the attachment readers in `pdfmd.py`), `core.pypdf` (a lazy loader there, so it is never imported at the top here) and the
other helpers named `core.X` when it runs.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import warnings
import zlib
from pathlib import Path

core = None

# --- The hybrid PDF (v3.25.10) -----------------------------------------------------------------------------
# LibreOffice's "hybrid PDF" (Export as PDF > Embed OpenDocument file): the PDF carries the document it was made from
# as an attachment named Original.odt (.odp, .ods), described as "Embedded original document of this PDF file" with the
# ODF mime type as its subtype; opening such a PDF in LibreOffice opens the attachment as a document you can edit, not the
# pages in Draw. Checked: LibreOffice goes by that attachment, not by what the pages show, so any PDF can carry one.
HYBRID_FAMILY = {".docx": "odt", ".doc": "odt", ".odt": "odt", ".ott": "odt", ".rtf": "odt",
                 ".pptx": "odp", ".ppt": "odp", ".odp": "odp", ".xlsx": "ods", ".xls": "ods", ".ods": "ods"}
HYBRID_DESCRIPTION = "Embedded original document of this PDF file"


def resolve_hybrid(path: Path, metadata_files: list[Path]) -> bool:
    """Whether the PDF built from ``path`` carries an editable ODF copy: --hybrid / --no-hybrid, else the document's
    `pdfmd-options.hybrid` (then its metadata files', then the config's). An office file has no front matter to ask."""
    if core.HYBRID_CLI is not None:
        return core.HYBRID_CLI
    if path.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
        return bool(core.option_flag(core.config_options(path).get("hybrid")))
    return bool(core.option_flag(core.first_pdfmd_option(path, metadata_files, "hybrid")))


def odf_source_for(path: Path, metadata_files: list[Path], variables: list[str], no_auto: list[str] | None,
                   verbose: bool) -> tuple[bytes, str] | None:
    """(the bytes of an ODF file for ``path``, its extension), or None. An office document is converted by LibreOffice
    (an .odt/.odp/.ods is taken as it is); anything else is built to .odt by pdfmd itself, with the same metadata."""
    family = HYBRID_FAMILY.get(path.suffix.lower())
    with tempfile.TemporaryDirectory(prefix="pdfmd-hybrid-") as scratch:
        scratch_dir = Path(scratch)
        if family is not None:
            if path.suffix.lower() == f".{family}":
                return path.read_bytes(), family
            binary = core.resolve_soffice()
            if binary is None:
                return None
            command = [binary, "--headless", "--norestore", f"-env:UserInstallation={(scratch_dir / 'profile').as_uri()}",
                       "--convert-to", family, "--outdir", str(scratch_dir), str(path)]
            core.log_cmd(command, path.parent, verbose)
            core.run_soffice(command, cwd=path.parent)
            made = scratch_dir / f"{path.stem}.{family}"
            return (made.read_bytes(), family) if made.is_file() else None
        target = scratch_dir / f"{path.stem}.odt"
        command = core.office_pdfmd_command(path, metadata_files, variables, no_auto, "-o", str(target), "--no-hybrid",
                                       "--no-attach-source")
        core.log_cmd(command, path.parent, verbose)
        done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=path.parent,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        return (target.read_bytes(), "odt") if done.returncode == 0 and target.is_file() else None


def attach_hybrid(pdf_path: Path, data: bytes, extension: str) -> bool:
    """Put ``data`` (an ODF file) into the PDF as LibreOffice's hybrid PDF has it. False when the PDF already has one."""
    from pypdf.generic import NameObject, NumberObject, DictionaryObject, TextStringObject
    name = f"Original.{extension}"
    pypdf_logger = logging.getLogger("pypdf")
    previous_level = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            writer = core.pypdf.PdfWriter(clone_from=pdf_path)
            if any(existing.startswith("Original.") and existing[9:] in core.HYBRID_MIME for existing in writer.attachments):
                return False
            attachment = writer.add_attachment(name, data)
            embedded = attachment._embedded_file
            embedded[NameObject("/Subtype")] = NameObject("/" + core.HYBRID_MIME[extension])
            embedded.set_data(zlib.compress(data, 9))
            embedded[NameObject("/Filter")] = NameObject("/FlateDecode")
            embedded[NameObject("/Params")] = DictionaryObject({NameObject("/Size"): NumberObject(len(data))})
            filespec = attachment.pdf_object
            filespec[NameObject("/UF")] = TextStringObject(name)
            filespec[NameObject("/Desc")] = TextStringObject(HYBRID_DESCRIPTION)
            core.atomic_write_pdf(writer, pdf_path)
    finally:
        pypdf_logger.setLevel(previous_level)
    return True


def hybrid_after_success(path: Path, pdf_path: Path, metadata_files: list[Path], variables: list[str],
                         no_auto: list[str] | None, verbose: bool) -> None:
    """--hybrid: make the PDF just built open as an editable document in LibreOffice."""
    if pdf_path.suffix.lower() != ".pdf" or not pdf_path.is_file():
        return
    if core.pypdf is None:
        print("WARN  hybrid: pypdf is not installed (pip install pypdf); nothing was attached", file=sys.stderr)
        return
    try:
        found = odf_source_for(path, metadata_files, variables, no_auto, verbose)
        if found is None:
            print(f"WARN  hybrid: could not make an OpenDocument copy of {core.display_path(path)}"
                  + ("" if path.suffix.lower() not in core.OFFICE_INPUT_EXTENSIONS else " (LibreOffice was not found)")
                  + "; the PDF itself was built", file=sys.stderr)
            return
        data, extension = found
        if attach_hybrid(pdf_path, data, extension):
            print(f"HYBRID    {core.display_path(pdf_path)}: carries {core.display_path(path)} as Original.{extension} "
                  f"({len(data) // 1024 or 1} KB); LibreOffice opens the PDF as an editable document")
        else:
            core.vprint(verbose, f"HYBRID    {core.display_path(pdf_path)}: already carries its OpenDocument source")
    except Exception as error:  # noqa: BLE001 -- the PDF itself is fine; say so and carry on
        print(f"WARN  hybrid: could not attach the OpenDocument copy to {core.display_path(pdf_path)} ({error}); "
              "the PDF itself was built", file=sys.stderr)

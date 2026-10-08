"""Word and OpenDocument output for pdfmd: page setup, fonts and house styles written into the
reference document Pandoc builds `.docx`/`.odt` files from, and (in later versions) LaTeX the
document cannot express natively. No dependencies beyond the standard library; pdfmd.py decides
*what* the document asks for (its metadata, `pdfmd-options: {office: ...}`) and hands plain data here.
"""

from __future__ import annotations

from .docx import default_reference, patch_docx
from .fonts import office_font
from .labels import cref_names, caption_separator, parse_aux
from .spec import OfficeSpec, spec_from_metadata
from .units import PAPER_TWIPS, length_to_twips, parse_geometry, parse_paper

def patch_reference(kind: str, data: bytes, spec: OfficeSpec, house: bool = True) -> bytes:
    """A reference document of `kind` ('docx', 'odt') with `spec` written into it."""
    if kind == "docx":
        return patch_docx(data, spec, house)
    if kind == "odt":
        from .odt import patch_odt
        return patch_odt(data, spec, house)
    raise ValueError(f"no reference-document patching for {kind}")


__all__ = ["caption_separator", "cref_names", "parse_aux", "default_reference", "patch_docx", "patch_reference", "OfficeSpec", "PAPER_TWIPS", "length_to_twips", "office_font", "parse_geometry", "parse_paper",
           "spec_from_metadata"]

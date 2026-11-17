"""Printed page maps: anchors, roman numerals, supplements and explicit PDF labels."""
from __future__ import annotations

import re
from pdfmd_base import core
from .record import RecordError

ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def roman(number):
    result = ""
    for value, word in ROMAN:
        count, number = divmod(number, value)
        result += word * count
    return result


def advance(printed, delta):
    if re.fullmatch("[ivxlcdmIVXLCDM]+", printed):
        number, rest = 0, printed.upper()
        for value, word in ROMAN:
            while rest.startswith(word):
                number += value
                rest = rest[len(word):]
        if roman(number).casefold() == printed.casefold():
            result = roman(number + delta)
            return result.lower() if printed.islower() else result
    found = re.fullmatch(r"(.*?)([0-9]+)", printed)
    if found:
        return found[1] + str(int(found[2]) + delta)
    if delta == 0:
        return printed
    raise RecordError("page anchor must be arabic, roman or end in a number")


def reader(path):
    if core.pypdf is None:
        raise RecordError("reading PDF pages needs the optional pypdf dependency")
    try:
        if not path.read_bytes().startswith(b"%PDF-"):
            raise RecordError("source is not a PDF")
        return core.pypdf.PdfReader(path)
    except RecordError:
        raise
    except Exception:
        raise RecordError("cannot read source PDF") from None


def labels(path):
    if path is None:
        raise RecordError("PDF labels need a source file")
    pdf = reader(path)
    values = pdf.page_labels
    if values == [str(number) for number in range(1, len(pdf.pages) + 1)]:
        raise RecordError("PDF labels are trivial; supply page anchors instead")
    return values


def printed_page(mapping, number, path=None):
    if mapping == "labels":
        values = labels(path)
        if number > len(values):
            raise RecordError("pdf-page is outside the source PDF")
        return values[number - 1]
    eligible = [anchor for anchor in (mapping or []) if anchor[0] <= number]
    if not eligible:
        return ""
    start, printed = eligible[-1]
    return advance(printed, number - start)

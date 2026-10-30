"""A spreadsheet as the data of a `.csv` block (v3.29.23): `::: {.csv file="results.xlsx" sheet="Run 2"}`.

`to_csv(path, sheet)` writes the sheet as CSV text (UTF-8, RFC 4180) with the first of these that can read the file:
openpyxl (xlsx, xlsm: the values the file stores, not their display formats), pandas (xls, ods too, with its own readers), LibreOffice
(any of them: the sheet by number). `sheet` is a name or a number counted from 1; none means the first. None of them: the reason."""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

SUFFIXES = (".xlsx", ".xlsm", ".xls", ".ods")


class SheetError(Exception):
    pass


def is_spreadsheet(name: str) -> bool:
    return name.lower().endswith(SUFFIXES)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) and abs(value) < 1e15 else repr(value)
    if isinstance(value, datetime.datetime):
        return value.date().isoformat() if value.time() == datetime.time(0) else value.isoformat(sep=" ")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


def _csv(rows) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    kept = [[_text(cell) for cell in row] for row in rows]
    while kept and not any(kept[-1]):                       # the empty rows a sheet's used range ends with
        kept.pop()
    width = max((len(row) for row in kept), default=0)
    for row in kept:
        while row and not row[-1] and len(row) > width:
            row.pop()
        writer.writerow(row)
    return out.getvalue()


def _with_openpyxl(path: Path, sheet: str | None) -> str:
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        names = book.sheetnames
        if sheet is None or sheet == "":
            chosen = names[0]
        elif sheet in names:
            chosen = sheet
        elif sheet.isdigit() and 1 <= int(sheet) <= len(names):
            chosen = names[int(sheet) - 1]
        else:
            raise SheetError(f"{path.name} has no sheet {sheet!r} (it has: {', '.join(names)})")
        return _csv(book[chosen].iter_rows(values_only=True))
    finally:
        book.close()


def _with_pandas(path: Path, sheet: str | None) -> str:
    import pandas
    name: int | str = 0 if not sheet else (int(sheet) - 1 if sheet.isdigit() else sheet)
    frame = pandas.read_excel(path, sheet_name=name, header=None, dtype=object)
    return _csv(frame.itertuples(index=False, name=None) if len(frame) else [])


def _with_soffice(path: Path, sheet: str | None, soffice: str | None, run=None) -> str:
    if not soffice:
        raise ImportError("LibreOffice is not installed")
    if sheet and not sheet.isdigit():
        raise SheetError("LibreOffice picks a sheet by number (sheet=\"2\"), not by name")
    number = int(sheet) if sheet else 1
    with tempfile.TemporaryDirectory(prefix="pdfmd-sheet-") as scratch:
        # UTF-8, comma, quote; sheet number last
        filter_text = f"csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,{number}"
        command = [soffice, "--headless", "--convert-to", filter_text, "--outdir", scratch, str(path)]
        done = run(command) if run else subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
        made = sorted(Path(scratch).glob("*.csv"))
        if done.returncode != 0 or not made:
            raise SheetError("LibreOffice could not convert it: " + ((done.stderr or done.stdout).strip().splitlines() or ["?"])[-1])
        return made[0].read_text(encoding="utf-8-sig")


def to_csv(path: Path, sheet: str | None = None, soffice: str | None = None, run=None) -> str:
    """The sheet as CSV text. Raises SheetError with what to install when no reader can."""
    problems: list[str] = []
    readers = []
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        readers.append(("openpyxl", lambda: _with_openpyxl(path, sheet)))
    readers.append(("pandas", lambda: _with_pandas(path, sheet)))
    readers.append(("LibreOffice", lambda: _with_soffice(path, sheet, soffice or shutil.which("soffice"), run)))
    for label, read in readers:
        try:
            return read()
        except SheetError:
            raise
        except ImportError:
            problems.append(f"{label} is not installed")
        except Exception as error:  # noqa: BLE001 -- a broken or protected file: the next reader may cope
            problems.append(f"{label}: {error}")
    raise SheetError(f"cannot read {path.name} as a spreadsheet ({'; '.join(problems)}). "
                     "Install openpyxl (pip install openpyxl) or LibreOffice, or save it as CSV")


def cached_csv(path: Path, sheet: str | None, cache: Path, soffice: str | None = None, run=None) -> Path:
    """The sheet as a CSV file in `cache` (named by the file's content and the sheet), made once."""
    key = hashlib.sha1(path.read_bytes() + b"\0" + (sheet or "").encode("utf-8")).hexdigest()[:20]
    target = cache / f"{key}.csv"
    if not target.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        text = to_csv(path, sheet, soffice, run)
        temporary = target.with_suffix(".part")
        temporary.write_text(text, encoding="utf-8", newline="")
        temporary.replace(target)
    return target

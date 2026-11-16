"""Tables <-> `.csv` blocks: `pdfmd --extract-tables` and `--expand-tables` (pdfmd.py has only the command line).
Document table settings and filter arguments live in `pdfmd_tables.settings` (v3.33.256)."""

from .convert import Extracted, TablesError, block_table, choose_names, expand, extract, pipe_table, slug
from .scan import CsvBlock, FoundTable, caption_parts, find_csv_blocks, find_tables
from .verify import pandoc_tables, same_tables

__all__ = ["CsvBlock", "Extracted", "FoundTable", "TablesError", "block_table", "caption_parts", "choose_names",
           "expand", "extract", "find_csv_blocks", "find_tables", "pandoc_tables", "pipe_table", "same_tables", "slug"]

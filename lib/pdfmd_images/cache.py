"""Atomic writes to the image cache, shared by concurrent builds: `pdfmd_cache.write_cached()`, which every cache of
pdfmd uses (it also survives Windows refusing the rename while another writer holds the same entry)."""

from pdfmd_cache import write_cached

__all__ = ["write_cached"]

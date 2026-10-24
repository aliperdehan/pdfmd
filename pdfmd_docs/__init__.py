"""The documents that come with this version of pdfmd: README.md, recipes.md, agents.md and CHANGELOG.md.

The build (setup.py) copies them here from the repository, so an installed pdfmd has the documents of its own version,
offline; in a checkout this folder holds none and `pdfmd --doc` reads the originals. `pdfmd --doc` is the way to read them.
The version they belong to is version(); no number is written down in this file."""


def version() -> str:
    """The pdfmd version these documents are the documents of: the one pdfmd itself reports (PDFMD_VERSION)."""
    import pdfmd
    return pdfmd.PDFMD_VERSION

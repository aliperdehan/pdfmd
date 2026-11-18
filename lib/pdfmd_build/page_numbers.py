"""Keep or suppress a writer's running page numbers."""

from collections.abc import Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from pdfmd_base import atomic_write_text
from pdfmd_base import core


_CROP_DEFAULT: ContextVar[bool] = ContextVar("crop_page_numbers_default", default=True)


@contextmanager
def cropped(source: Path, variables: Sequence[str], *, report: bool):
    """Set the numbering default for this cropped PDF and its intermediate writers."""
    markdown = report or source.suffix.lower() in core.MARKDOWN_LIKE_SUFFIXES
    explicit_style = any(value.split(":", 1)[0].split("=", 1)[0] in ("pagestyle", "page-numbering")
                         for value in variables)
    token = _CROP_DEFAULT.set(not markdown or explicit_style)
    try:
        yield
    finally:
        _CROP_DEFAULT.reset(token)


def enabled(source: Path, metadata: list[Path]) -> bool:
    if core.PAGE_NUMBERS_CLI is not None:
        return core.PAGE_NUMBERS_CLI
    setting = core.option_flag(core.first_pdfmd_option(source, metadata, "page-numbers"))
    return _CROP_DEFAULT.get() if setting is None else setting


def arguments(writer: str, source: Path, metadata: list[Path]) -> list[str]:
    if writer not in {"typst", "latex", "beamer", *core.LATEX_ENGINES} or enabled(source, metadata):
        return []
    if writer == "typst":
        return ["-M", "pdfmd-page-numbers=off"]
    if writer == "context":
        return []
    header = core.cache_root() / "tex" / "packages-page-numbers-off.tex"
    if not header.is_file():
        # The title page can select the plain style even when the running style is empty.
        header.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(header, r"""\makeatletter
\AtBeginDocument{\pagestyle{empty}\let\ps@plain\ps@empty}
\makeatother
""")
    return ["--include-in-header", str(header)]

"""Keep or suppress a writer's running page numbers."""

from pathlib import Path

from pdfmd_base import atomic_write_text
from pdfmd_base import core


def enabled(source: Path, metadata: list[Path]) -> bool:
    if core.PAGE_NUMBERS_CLI is not None:
        return core.PAGE_NUMBERS_CLI
    return core.option_flag(core.first_pdfmd_option(source, metadata, "page-numbers")) is not False


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

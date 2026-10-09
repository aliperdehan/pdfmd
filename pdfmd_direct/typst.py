"""`.typ` straight to Typst: `typst compile`, with the fonts pdfmd manages on the font path."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def accepts_request(request: str | None) -> bool:
    """False when the user asked for an engine that is not Typst (`-e lualatex`): they want the Pandoc route."""
    return request is None or request.casefold() in ("", "typst", "6")


def compile_typst(typst: str, source: Path, output: Path, font_path: str | None = None,
                  log=lambda command, cwd: None) -> tuple[bool, str]:
    """Compile `source` to `output`; (True, "") or (False, Typst's message)."""
    scratch = Path(tempfile.mkdtemp(prefix="pdfmd-typst-"))
    try:
        produced = scratch / "out.pdf"
        command = [typst, "compile", str(source), str(produced)]
        if font_path:
            command += ["--font-path", font_path]
        log(command, source.parent)
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              cwd=source.parent)
        if done.returncode != 0 or not produced.is_file():
            return False, (done.stderr.strip() or done.stdout.strip() or "typst produced no PDF")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output)
        return True, ""
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

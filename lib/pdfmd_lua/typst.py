"""Apply the body pitch inside Pandoc's default Typst title/abstract and around its outline.

The Lua filter computes the lengths from the resolved metadata and variables. A copy of Pandoc's
own template consumes them inside conf, where a header rule would lose to its leading rule.
Custom templates and fragments keep their existing route.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

core = None


def template_args(writer: str, command: list[str]) -> list[str]:
    """A cached default template with the same line rules as typst.lua's body, when standalone."""
    if writer != "typst" or not command:
        return []
    if any(word in ("--template", "-d", "--defaults") or word.startswith(("--template=", "--defaults=", "-d"))
           for word in command):
        return []
    pdf = any(word.lower().endswith(".pdf") for i, word in enumerate(command) if i and command[i - 1] in ("-o", "--output"))
    if not pdf and not any(word in ("-s", "--standalone") for word in command):
        return []
    try:
        template = subprocess.run(["pandoc", "-D", "typst"], capture_output=True, text=True, check=True).stdout
        if "$template.typst()$" in template:
            partial = subprocess.run(["pandoc", "--print-default-data-file", "templates/template.typst"],
                                     capture_output=True, text=True, check=True).stdout
            template = template.replace("$template.typst()$", partial)
        original = "leading: linestretch * 0.65em"
        if original not in template:
            return []
        template = template.replace(original, "leading: $pdfmd-typst-leading$, spacing: $pdfmd-typst-spacing$")
        template = '#set text(top-edge: $pdfmd-typst-top-edge$, bottom-edge: "baseline")\n' + template
        target = core.cache_root() / "typst" / (hashlib.sha256(template.encode()).hexdigest() + ".typ")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            target.write_text(template, encoding="utf-8")
        return ["--template", str(target)]
    except (OSError, subprocess.SubprocessError):
        return []

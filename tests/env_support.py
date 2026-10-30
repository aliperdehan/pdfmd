"""Environment variables a test sets so that pdfmd finds nothing of the machine it runs on.

pdfmd looks for a tool beyond PATH on Windows (an install folder, the registry), keeps its settings in %APPDATA% and its cache in
%LOCALAPPDATA%. A test that empties PATH, or points XDG_CONFIG_HOME at a scratch folder, still sees those unless it also names them.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def can_symlink() -> bool:
    """Whether this account may create a symbolic link: on Windows only with Developer Mode or an elevated shell."""
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "target"
        target.write_text("x", encoding="utf-8")
        try:
            os.symlink(target, Path(folder) / "link")
        except (OSError, NotImplementedError):
            return False
    return True


def hidden_tools(folder: str | Path) -> dict[str, str]:
    """No tool turns up in a Windows install folder or the registry: they all point at ``folder``, which must hold none."""
    return {"PDFMD_NO_APP_PATHS": "1", "LOCALAPPDATA": str(folder), "APPDATA": str(folder), "ProgramFiles": str(folder),
            "ProgramW6432": str(folder), "ProgramFiles(x86)": str(folder)}


def config_env(folder: str | Path) -> dict[str, str]:
    """Where pdfmd keeps its settings, on every system: XDG_CONFIG_HOME, and on Windows APPDATA."""
    return {"XDG_CONFIG_HOME": str(folder), "APPDATA": str(folder)}

"""`pdfmd --setup`: change the global defaults without editing the config file by hand.

Two screens, one registry: a numbered list that needs nothing, and a full-screen one (prompt_toolkit,
installed on request with `pdfmd --install tui`). Which one opens is the config's `setup-ui:`
(`plain` or `fancy`; a missing prompt_toolkit falls back to plain with a note).
"""

from __future__ import annotations

from . import fancy, inventory, plain, registry
from .registry import Setting, settings_for

__all__ = ["fancy", "inventory", "plain", "registry", "Setting", "settings_for", "run"]


def run(stores: dict, no_auto_kinds, path: str, ui: str | None = None, read_line=input, say=print,
        flag_names: dict[str, str] | None = None) -> bool:
    """Open the setup screen for `stores` ({"config": {...}, "metadata": {...}}, edited in place); True when the
    user saved. `ui` is `plain` or `fancy` (default: the config's `setup-ui`, else plain). `flag_names` maps a flag's
    argparse dest to how it is written, for the list of what is not settable here."""
    choice = ui or registry.get(stores.setdefault("config", {}), "setup-ui") or "plain"
    settings = settings_for(no_auto_kinds, ("plain", "fancy") if fancy.available() else ("plain",))
    left_out = inventory.omitted_lines(flag_names)
    if choice == "fancy":
        if fancy.available():
            return fancy.run(stores, settings, path, left_out=left_out)
        say("NOTE  the full-screen setup needs prompt_toolkit: pdfmd --install tui (using the numbered list)")
    nudge = "" if fancy.available() else "A full-screen version is optional: pdfmd --install tui, then set \"This setup screen\" to fancy."
    return plain.run(stores, settings, path, read_line, say, nudge, left_out)

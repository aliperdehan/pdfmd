"""`pdfmd --setup`: change the global defaults without editing the config file by hand.

Two screens, one registry: a numbered list that needs nothing, and a full-screen one (prompt_toolkit,
installed on request with `pdfmd --install tui`). Which one opens is the config's `setup-ui:`
(`plain` or `fancy`; a missing prompt_toolkit falls back to plain with a note).
"""

from __future__ import annotations

from dataclasses import replace

from . import fancy, inventory, plain, registry
from .registry import Setting, settings_for

__all__ = ["fancy", "inventory", "plain", "registry", "Setting", "settings_for", "run"]


def folder_settings(settings: list[Setting]) -> tuple[list[Setting], list[str]]:
    """The rows of a folder's setup (see registry.FOLDER_OPTIONS) with the folder's own `inherit` row, and the lines that say
    what the screen leaves out: those rows are every document's, set by `pdfmd --setup`."""
    kept, left = registry.folder_split(settings)
    kept = [replace(setting, section="Every document in this folder (metadata)") if setting.section == "Every document (global metadata)"
            and setting.store == "metadata" else
            replace(setting, section="Global metadata") if setting.section == "Every document (global metadata)" else setting
            for setting in kept]
    kept.append(Setting("inherit", "Also use the settings of the folders above", "choice", registry.ON_OFF, "on",
                        "Off: this folder is the top, what lies above it (and, for its options, the global setup's own "
                        "folder layers) is not read from here down.", "This folder", "config"))
    lines = ["", "Left out of a folder's setup, because a build reads them from the global setup alone (pdfmd --setup):"]
    line = " "
    for setting in left:
        word = setting.key + ","
        if len(line) + len(word) + 1 > 100 and line.strip():
            lines.append(line)
            line = " "
        line += " " + word
    lines.append(line.rstrip(","))
    lines.append("  (a path row, bibliography and csl, is left out too: Pandoc takes a path in a metadata file from that file's own folder)")
    return kept, lines


def run(stores: dict, no_auto_kinds, path: str, ui: str | None = None, read_line=input, say=print,
        flag_names: dict[str, str] | None = None, flag_topics: dict[str, set[str]] | None = None,
        folder: bool = False, inherited=None) -> bool:
    """Open the setup screen for `stores` ({"config": {...}, "metadata": {...}}, edited in place); True when the
    user saved. `ui` is `plain` or `fancy` (default: the config's `setup-ui`, else plain). `flag_names` maps a flag's
    argparse dest to how it is written, for the list of what is not settable here; `flag_topics` maps it to its
    features (pdfmd_help topics), so the rows of a switched-off feature leave the screen. `inherited(setting)` gives, for a row a
    folder has no value for, (the value, where it comes from) in the setups above it: the numbered screen shows it."""
    choice = ui or ("plain" if folder else registry.get(stores.setdefault("config", {}), "setup-ui")) or "plain"
    settings = settings_for(no_auto_kinds, ("plain", "fancy") if fancy.available() else ("plain",))
    left_out = inventory.omitted_lines(flag_names)
    if not folder:                                    # "switch back on" is for a folder: nothing above the global setup to switch back
        settings = [setting for setting in settings if setting.key != "options.auto.on"]
    if folder:
        settings, not_here = folder_settings(settings)
        left_out = not_here + left_out
    topics = inventory.row_topics(flag_topics or {}, [setting.key for setting in settings])

    def hidden(setting: Setting) -> bool:
        """A row of a feature the screen's own "Features switched off" row has off."""
        off = registry.get(stores.setdefault("config", {}), "disabled") or []
        return setting.key != "disabled" and bool(topics.get(setting.key)) and topics[setting.key] <= set(off)

    if choice == "fancy":
        if fancy.available():
            return fancy.run(stores, settings, path, left_out=left_out, hidden=hidden)
        say("NOTE  the full-screen setup needs prompt_toolkit: pdfmd --install tui (using the numbered list)")
    nudge = "" if folder or fancy.available() else "A full-screen version is optional: pdfmd --install tui, then set \"This setup screen\" to fancy."
    return plain.run(stores, settings, path, read_line, say, nudge, left_out, hidden, inherited)

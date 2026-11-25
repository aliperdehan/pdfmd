"""The versioned report of configured values and their origins."""

from __future__ import annotations

import json
import math
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from pdfmd_base import core
from pdfmd_config import folder_layer_files, folder_options_safe, global_config_layers, install_config_path

# Public environment settings and the keys they correspond to. These are the
# configured strings, before their individual readers parse them for a build.
ENVIRONMENT_SETTINGS = {
    "PDFMD_TRANSLIT": "translit",
    "PDFMD_BATCHOCR": "batchocr",
    "PDFMD_BROWSER": "browser",
    "PDFMD_CALIBRE": "calibre",
    "PDFMD_TEX_BIN": "tex-bin",
    "PDFMD_PAGER": "options.pager_command",
    "PDFMD_BUILD_TIME": "options.build-time",
    "PDFMD_BUILD_LOG": "options.build-log",
    "PDFMD_TIME_FORMAT": "options.time-format",
    "PDFMD_STRICT": "options.strict",
    "PDFMD_SHRINK": "options.shrink",
    "PDFMD_CSV": "options.csv.enabled",
    "PDFMD_MAX_ASSET_MB": "options.max-asset-mb",
    "PDFMD_MAX_OUTPUT_MB": "options.max-output-mb",
}


def json_value(value):
    """Keep JSON-native values and represent other YAML scalars as text."""
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_value(item) for item in sorted(value, key=str)]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def configured_report(document: Path | None = None) -> bool:
    from pdfmd_setup.registry import settings_for, to_stored

    with redirect_stdout(sys.stderr):
        try:
            folder = (Path.cwd() if document is None else document if document.is_dir()
                      else core.find_markdown(document).parent)
            folder = str(folder.resolve())
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return False

    layers = []
    settings = {}

    def add_layer(name, path, values, reason=None):
        origin = {"layer": name, "path": str(path) if path is not None else None}
        layers.append({"name": name, "path": origin["path"], "active": reason is None, "reason": reason})

        def add_values(mapping, prefix=""):
            for key, value in mapping.items():
                key = prefix + str(key)
                parents = (key[:index] for index, char in enumerate(key) if char == ".")
                for parent in parents:
                    settings.pop(parent, None)
                if isinstance(value, dict) and value:
                    settings.pop(key, None)
                    add_values(value, key + ".")
                    continue
                children = [child for child in settings if child.startswith(key + ".")]
                if value == {} and children:
                    continue  # an empty mapping adds nothing to an inherited mapping
                for child in children:
                    del settings[child]
                settings[key] = {"value": json_value(value), **origin}

        add_values(values)

    add_layer("built-in default", None, {
        row.key: to_stored(row, row.default) if row.default else None
        for row in settings_for(core.NO_AUTO_KINDS) if row.kind != "action"
    })
    globals_by_name = {name: (path, values) for name, path, values in global_config_layers()}
    user_path = core.config_path()
    for name, path in (("user", user_path), ("per-install", install_config_path())):
        if path is None:
            add_layer(name, None, {}, "switched off by PDFMD_CONFIG")
        elif not path.is_file():
            add_layer(name, path, {}, "file not found")
        elif name not in globals_by_name:
            add_layer(name, path, {}, "also the per-install file")
        else:
            add_layer(name, *globals_by_name[name])

    folders = folder_layer_files(folder)
    if not folders:
        add_layer("folder", None, {}, "no folder config file")
    for path, options in reversed(folders):
        add_layer("folder", path, {"options": folder_options_safe(path, options)})

    environment = {key: os.environ[var] for var, key in ENVIRONMENT_SETTINGS.items() if var in os.environ and (os.environ[var] or var in {"PDFMD_TRANSLIT", "PDFMD_CALIBRE"})}
    if "options.pager_command" not in environment and os.environ.get("PAGER"):
        environment["options.pager_command"] = os.environ["PAGER"]
    add_layer("environment", None, environment, None if environment else "no environment overrides")

    print(json.dumps({"format": "pdfmd-config", "version": 1, "pdfmd": core.PDFMD_VERSION,
                      "layers": layers, "settings": settings}, default=str))
    return True

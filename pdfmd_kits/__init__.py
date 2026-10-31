"""Kits: a named, versioned unit for a whole document pipeline (entry 3du of the maintainer's notes).

A kit is a folder that holds a `.kit` file. `kitfile` reads and checks that file (the format, version 1);
`discovery` finds a kit by name (a path, a few folders, the TeX tree) and remembers where it was. Both are
pure: they import nothing from pdfmd, so a test or a future tool can use them alone. pdfmd.py wires them to
the config, the layers and the build.
"""

from .discovery import Found, Location, find, list_kits, normalise, Cache
from .kitfile import FORMAT, Kit, KitError, Mode, load_kit, resolve_mode

__all__ = ["Cache", "FORMAT", "Found", "Kit", "KitError", "Location", "Mode", "find", "list_kits", "load_kit", "normalise",
           "resolve_mode"]

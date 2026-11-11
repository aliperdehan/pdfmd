"""The live view's filters stay inside the project folder (review finding G4.4 of entry 3do).

`/api/render` checks the path of the document, but the filters it runs read what the TEXT names: `::: {.csv file="../private.txt"}` had
`csv_table.lua` open a file beside the project and put it into the page. Pandoc runs the file `init.lua` of its data folder before every
Lua filter, each in a Lua state of its own, so the render is given a data folder of its own whose `init.lua` (GUARD) wraps the Lua
functions that open a file by name (`io.open`, `io.lines`, `io.input`, `io.output`, `dofile`, `loadfile`, `os.remove`, `os.rename`,
`pandoc.mediabag.fetch`): a path is let through when it is in the folder of one of the render's filters, in pdfmd's cache (the
pictures it draws) or in the render's own temporary folder (TMPDIR), and otherwise only when its real path (symlinks and `..` resolved by
the operating system, CHECK) is inside the project and not in its `.git`. A refused path fails as a missing file would, with one `WARN`
line that the page shows.

What this does not cover: a program a filter starts reads what it is told (a LaTeX picture's `\\input`, a diagram tool's include). And
what it costs: a file outside the project that a setting names (a LaTeX preamble shared by every document) is not read by the live view's
filters either, and the live view no longer sees Pandoc's user data folder (its templates are not used there; an `init.lua` of the
user's own is not run).
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

# The Lua that pandoc runs before each filter of a live render. The places come from the environment (no path is written into code).
GUARD = r"""-- pdfmd --serve: the live view's filters open files only inside the project folder (written by pdfmd_serve/contain.py)
local ROOT = os.getenv("PDFMD_LIVE_ROOT")
if not ROOT then return end
local PYTHON, CHECK = os.getenv("PDFMD_LIVE_PYTHON"), os.getenv("PDFMD_LIVE_CHECK")
local fold = package.config:sub(1, 1) == "\\" or pandoc.system.os == "darwin"

local function absolute(path)
  path = path:gsub("\\", "/")
  if path:match("^/") or path:match("^%a:/") then return path end
  return (pandoc.system.get_working_directory():gsub("\\", "/")) .. "/" .. path
end

-- a lexical key for the places pdfmd named: `.` and `..` collapsed, the case folded where the file system ignores it
local function key(path)
  local head, rest = path:match("^(%a:)(/.*)$")
  if not head then head, rest = "", path end
  local parts = {}
  for part in rest:gmatch("[^/]+") do
    if part == ".." then parts[#parts] = nil elseif part ~= "." then parts[#parts + 1] = part end
  end
  local out = head .. "/" .. table.concat(parts, "/")
  return fold and out:lower() or out
end

local TRUSTED = {}
for line in (os.getenv("PDFMD_LIVE_TRUSTED") or ""):gmatch("[^\n]+") do TRUSTED[#TRUSTED + 1] = key(absolute(line)) end

local function under(path, place) return path == place or path:sub(1, #place + 1) == place .. "/" end

local verdicts = {}
local function permitted(path)
  local full = absolute(path)
  if verdicts[full] ~= nil then return verdicts[full] end
  local ok = false
  if not full:find("/%.%./") and not full:find("/%.%.$") then
    local k = key(full)
    for _, place in ipairs(TRUSTED) do if under(k, place) then ok = true break end end
  end
  if not ok and PYTHON and CHECK then        -- the project's own files: the operating system resolves the path (symlinks, `..`)
    local done, answer = pcall(pandoc.pipe, PYTHON, {"-I", "-S", CHECK}, full)
    ok = done and answer == "yes"
  end
  verdicts[full] = ok
  return ok
end

local told = {}
local function refused(path)
  local k = key(absolute(path))      -- one warning for a file, however the filter spells the places it tries
  if not told[k] then
    told[k] = true
    io.stderr:write("WARN  live view: " .. path .. " is outside the project folder; the live view's filters do not open it\n")
  end
  return path .. ": outside the project folder (pdfmd --serve)"
end

local open, lines, input, output = io.open, io.lines, io.input, io.output
local run_file, load_file, remove, rename = dofile, loadfile, os.remove, os.rename
io.open = function(path, ...)
  if type(path) == "string" and not permitted(path) then return nil, refused(path) end
  return open(path, ...)
end
io.lines = function(path, ...)
  if type(path) == "string" and not permitted(path) then error(refused(path), 2) end
  return lines(path, ...)
end
io.input = function(file, ...)
  if type(file) == "string" and not permitted(file) then error(refused(file), 2) end
  return input(file, ...)
end
io.output = function(file, ...)
  if type(file) == "string" and not permitted(file) then error(refused(file), 2) end
  return output(file, ...)
end
dofile = function(path, ...)
  if type(path) == "string" and not permitted(path) then error(refused(path), 2) end
  return run_file(path, ...)
end
loadfile = function(path, ...)
  if type(path) == "string" and not permitted(path) then return nil, refused(path) end
  return load_file(path, ...)
end
os.remove = function(path, ...)
  if type(path) == "string" and not permitted(path) then return nil, refused(path) end
  return remove(path, ...)
end
os.rename = function(from, to, ...)
  for _, path in ipairs({from, to}) do
    if type(path) == "string" and not permitted(path) then return nil, refused(path) end
  end
  return rename(from, to, ...)
end
if pandoc.mediabag and pandoc.mediabag.fetch then
  local fetch = pandoc.mediabag.fetch
  pandoc.mediabag.fetch = function(source, ...)
    if type(source) == "string" and not source:match("^%a[%w+.-]*://") and not permitted(source) then error(refused(source), 2) end
    return fetch(source, ...)
  end
end
"""

# Run by the guard for a path that is not in a place pdfmd named: "yes" when its real path is inside the project (outside `.git`) or in
# one of those places. `-I -S`: nothing of the user's site or environment is imported.
CHECK = r"""import os, sys
def under(path, place):
    path, place = os.path.normcase(path), os.path.normcase(place)
    return path == place or path.startswith(place.rstrip(os.sep) + os.sep)
real = os.path.realpath(sys.stdin.read())
root = os.path.realpath(os.environ["PDFMD_LIVE_ROOT"])
places = [os.path.realpath(p) for p in os.environ.get("PDFMD_LIVE_TRUSTED", "").split("\n") if p]
inside = under(real, root) and not under(real, os.path.join(root, ".git"))
sys.stdout.write("yes" if inside or any(under(real, p) for p in places) else "no")
"""


def trusted_places(root: Path, command: list[str], places: list) -> list[str]:
    """The places outside the project that the filters of a live render may open: the folder of each `--lua-filter` (pdfmd's own
    filters `dofile` their helpers there) and ``places``, which the caller names (pdfmd's cache: the pictures of LaTeX pieces, diagrams
    and structures). Nothing the document says is among them; a place inside the project is left out, as the real path decides there."""
    named = [str(Path(value).parent) for flag, value in zip(command, command[1:]) if flag == "--lua-filter"] + [str(item) for item in places]
    found = []
    for item in named:
        if not item or not os.path.isabs(item):
            continue
        try:
            Path(item).resolve().relative_to(root)
            continue
        except ValueError:
            pass
        except OSError:
            continue
        found += [item, str(Path(item).resolve())]
    return list(dict.fromkeys(found))


@contextlib.contextmanager
def contained(root: Path, command: list[str], places: list) -> Iterator[tuple[list[str], dict]]:
    """The extra Pandoc arguments (`--data-dir` with the guard) and the environment of one live render of the project ``root``;
    ``places`` are the caller's own places outside it (see trusted_places)."""
    with tempfile.TemporaryDirectory(prefix="pdfmd-live-guard-") as scratch:
        base = Path(scratch)
        data, temporary = base / "data", base / "tmp"
        data.mkdir()
        temporary.mkdir()
        (data / "init.lua").write_text(GUARD, encoding="utf-8")
        (base / "check.py").write_text(CHECK, encoding="utf-8")
        trusted = [str(temporary), str(temporary.resolve())] + trusted_places(root, command, places)
        environment = {**os.environ, "PDFMD_LIVE_ROOT": str(root), "PDFMD_LIVE_TRUSTED": "\n".join(dict.fromkeys(trusted)),
                       "PDFMD_LIVE_PYTHON": sys.executable, "PDFMD_LIVE_CHECK": str(base / "check.py"),
                       "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary)}
        yield ["--data-dir", str(data)], environment

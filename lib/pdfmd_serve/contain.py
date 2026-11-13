"""The live view contains document-supplied references (DECISION 66).

A document's own references (images, includes, CSV, raw-LaTeX inputs, fetches and cache folders) stay inside the project,
excluding its private `.git` folder. Paths are checked after resolving symlinks and `..`. pdfmd's generated assets and filter
helpers may also use the cache, filter and temporary folders named by the caller; a document cannot add trusted roots.

Project filters are trusted code: they can run programs and reach any file, as can the Pandoc functions they call. The guard
checks document-supplied references handled by the shipped filters; it does not sandbox arbitrary project code or its native
filesystem and loader APIs.

`/api/render` checks the document path. Each filter then starts in a Lua state of its own, with this render's data-folder
`init.lua` (GUARD) wrapping file operations. CHECK resolves paths using the operating system. A refusal produces the existing
missing-file-style error and a WARN line for the page. The live view does not load Pandoc's user data folder or its init.lua.
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
-- Pandoc's LaTeX reader performs native includes, bypassing io.open. Inspect their files before handing it any text.
local read = pandoc.read
local function latex_inputs(text, seen, directory)
  local i = 1
  while i <= #text do
    local char = text:sub(i, i)
    if char == "%" then
      i = text:find("\n", i, true) or (#text + 1)
    elseif char == "\\" then
      local command, after = text:match("^\\(%a+)()", i)
      if command == "input" or command == "include" then
        local argument = text:sub(after):match("^%s*(%b{})")
        local name = argument and argument:sub(2, -2):match("^%s*(.-)%s*$") or text:sub(i, after - 1)
        -- A macro-dependent name cannot be checked before the native reader expands it. Fail closed.
        if not argument or name:find("[\\{}#%%\"]") then error(refused(name), 2) end
        local folders = {directory or pandoc.system.get_working_directory()}
        for _, folder in ipairs(PANDOC_STATE.resource_path or {}) do folders[#folders + 1] = folder end
        for _, folder in ipairs(folders) do
          local path = (name:match("^/") or name:match("^%a:[/\\]")) and name or (folder .. "/" .. name)
          for _, candidate in ipairs({path, path .. ".tex"}) do
            if not permitted(candidate) then error(refused(candidate), 2) end
            local identity = key(absolute(candidate))
            if not seen[identity] then
              seen[identity] = true
              local handle = open(candidate, "rb")
              if handle then
                local contents = handle:read("a"); handle:close()
                latex_inputs(contents, seen, candidate:match("^(.*)[/\\]") or folder)
              end
            end
          end
        end
        i = after
      else
        i = after or (i + 2)       -- also skip escaped percent signs and backslashes
      end
    else
      i = i + 1
    end
  end
end
pandoc.read = function(text, format, ...)
  if type(text) == "string" and type(format) == "string" and (format == "latex" or format:match("^latex[+-]")) then
    latex_inputs(text, {})
  end
  return read(text, format, ...)
end

if pandoc.mediabag and pandoc.mediabag.fetch then
  local fetch = pandoc.mediabag.fetch
  pandoc.mediabag.fetch = function(source, ...)
    if type(source) == "string" then
      local scheme = source:match("^(%a[%w+.-]*):")
      scheme = scheme and scheme:lower()
      local path = source
      if scheme == "file" then
        path = source:sub(#scheme + 2):match("^[^?#]*")
        local host, rest = path:match("^//([^/]*)(.*)$")
        local function decode(value)
          return (value:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))
        end
        if host then
          host = decode(host)
          path = (host == "" or host:lower() == "localhost") and rest or ("//" .. host .. rest)
        end
        path = decode(path)
        if package.config:sub(1, 1) == "\\" and path:match("^/%a:/") then path = path:sub(2) end
      end
      local network = source:match("^%a[%w+.-]*://") and (scheme == "http" or scheme == "https" or scheme == "ftp" or scheme == "ftps")
      if not network and not permitted(path) then error(refused(path), 2) end
    end
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

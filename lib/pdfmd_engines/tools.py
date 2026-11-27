"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_engines.tools`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import importlib.util
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from pdfmd_base import core
from pdfmd_base import spelling

from pdfmd_base import pandoc_run
from pdfmd_log import emit


# The tools pdfmd runs that Windows installers leave off PATH: tool -> (the `options:` key of the config that names it,
# its programs, its folders below an install root, other roots as (variable, folder below it), whether its folder goes on
# PATH for pdfmd's own runs). The folders are a file-system fact about those installers, not a behaviour threshold; a `*`
# matches a version in a folder name (poppler's builds). soffice stays off PATH: its folder holds a python.exe and DLLs of its own.
FOUND_TOOLS = {
    "tesseract": ("tesseract-path", ("tesseract",), ("Tesseract-OCR",), (), True),
    "soffice": ("soffice-path", ("soffice", "libreoffice"), ("LibreOffice/program",), (), False),
    "dot": ("dot-path", ("dot",), ("Graphviz/bin", "Graphviz*/bin"), (), True),
    "mmdc": ("mmdc-path", ("mmdc",), (), (("APPDATA", "npm"),), True),
    "poppler": ("poppler-path", ("pdftotext", "pdftoppm"), ("poppler*/Library/bin", "poppler*/bin"), (), True),
    "calibre": (None, ("ebook-convert",), ("Calibre2",), (), False),
    "pandoc": ("pandoc-path", ("pandoc",), ("Pandoc",), (("LOCALAPPDATA", "Pandoc"),), True),
    "typst": ("typst-path", ("typst",), (), (("LOCALAPPDATA", "Microsoft/WinGet/Links"),
                                              ("LOCALAPPDATA", "Microsoft/WinGet/Packages/Typst.Typst_*/typst-*")), True),
    "chrome": ("chrome-path", ("chrome",), ("Google/Chrome/Application",), (), False),      # by PDFMD_BROWSER, see use_found_tools()
}


WINDOWS_INSTALL_ROOTS = (("ProgramFiles", ""), ("ProgramW6432", ""), ("ProgramFiles(x86)", ""), ("LOCALAPPDATA", "Programs"))


TOOLS_FOUND: dict[str, tuple[str, str]] = {}      # tool -> (file, "key" | "probe") for what use_found_tools() found off PATH


TOOL_WARNED: set[str] = set()


TOOL_KEYS = tuple(item[0] for item in FOUND_TOOLS.values() if item[0])
TOOL_PINS = ContextVar("tool_pins", default={})


def pinned_program(program: str) -> str | None:
    found = TOOL_PINS.get().get(program)
    return found[0] if found else None


def which(program: str) -> str | None:
    return pinned_program(program) or shutil.which(program)


def tool_setting(name: str) -> str | None:
    for program in FOUND_TOOLS[name][1]:
        if found := TOOL_PINS.get().get(program):
            return found[1]
    return None


def named_program(place: Path, programs: tuple[str, ...], name: str) -> Path | None:
    if place.is_dir():
        return next((found for program in programs if (found := tool_program(place, program))), None)
    return place if name != "poppler" and place.is_file() else None


@contextmanager
def tool_paths(document: Path | None = None, metadata_files=(), *, directory: Path | None = None):
    """Scope executable pins like soffice-timeout, with the command line above the option layers."""
    cli = getattr(core, "TOOL_PATHS_CLI", {})
    layers = None
    if document is not None:
        try:
            layers = core.option_sources(document, metadata_files)
        except (OSError, UnicodeError):
            directory = document.parent
    if layers is None:
        layers = [*(core.folder_layers(directory / ".pdfmd") if directory else []), ("config", core.config_options())]
    pins: dict[str, tuple[str, str]] = {}
    directories = []
    updates = {}
    for name, (key, programs, _, _, on_path) in FOUND_TOOLS.items():
        if key is None:
            continue
        if key in cli:
            named, source = cli[key], "--" + key
        else:
            named, source = next(((values[alias], f"options.{key}" if label == "config" else f"{label} ({key})")
                                  for label, values in layers for alias in spelling.spellings(key) if alias in values),
                                 (None, ""))
        if not isinstance(named, str) or not named.strip():
            continue
        place = Path(os.path.expandvars(named.strip())).expanduser().absolute()
        file = named_program(place, programs, name)
        if file is None:
            if (warning := f"{key}:{named}") not in core.TOOL_WARNED:
                core.TOOL_WARNED.add(warning)
                emit("warning", None, f"WARN  {source} ({named}) holds no {programs[0]}; looking on PATH and in the usual folders",
                     file=sys.stderr)
            continue
        if name == "poppler":
            for program in programs:
                if found := tool_program(place, program):
                    pins[program] = str(found), source
        else:
            pins[programs[0]] = str(file), source
        if on_path:
            directories.append(str(file.parent))
        if name == "chrome":
            updates["PDFMD_BROWSER"] = str(file)
        if name in ("pandoc", "typst"):
            updates["QUARTO_" + name.upper()] = str(file)
        if name in ("dot", "mmdc"):
            updates["PDFMD_TOOL_" + name.upper()] = str(file)
    if directories:
        updates["PATH"] = os.pathsep.join(dict.fromkeys([*directories, *os.environ.get("PATH", "").split(os.pathsep)]))
    previous = {key: os.environ.get(key) for key in updates}
    pandoc_changed = pinned_program("pandoc") != pins.get("pandoc", (None, ""))[0]
    cache = {}
    if pandoc_changed:
        for key, default in (("_PANDOC_VERSION", None), ("_PANDOC_DATA_DIR", False), ("_PANDOC_HELP", None)):
            cache[key] = getattr(core, key)
            setattr(core, key, default)
        extensions = core._PANDOC_EXTENSIONS.copy()
        core._PANDOC_EXTENSIONS.clear()
    token = TOOL_PINS.set(pins)
    try:
        os.environ.update(updates)
        yield
    finally:
        TOOL_PINS.reset(token)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key, value in cache.items():
            setattr(core, key, value)
        if pandoc_changed:
            core._PANDOC_EXTENSIONS.clear()
            core._PANDOC_EXTENSIONS.update(extensions)


def pinned_command(arguments):
    """Use exact filenames, including for a Typst subprocess started by Pandoc."""
    if not arguments or not TOOL_PINS.get():
        return arguments
    program, *rest = arguments
    fixed = pinned_program(str(program))
    if str(program) in ("pandoc", "pandoc.exe", pinned_program("pandoc")):
        if typst := pinned_program("typst"):
            rest = [f"--pdf-engine={typst}" if arg == "--pdf-engine=typst" else
                    typst if arg == "typst" and index and rest[index - 1] == "--pdf-engine" else arg
                    for index, arg in enumerate(rest)]
    return [fixed or program, *rest]


def pinned_flags() -> list[str]:
    """Pass the tools selected for this document to a diagnostic child."""
    options = []
    for key, programs, *_ in FOUND_TOOLS.values():
        if key and (program := next((pinned_program(name) for name in programs if pinned_program(name)), None)):
            options.extend(("--" + key, str(Path(program).parent) if key == "poppler-path" else program))
    return options


def tool_program(folder: Path, program: str) -> Path | None:
    """The file of ``program`` in ``folder`` (with the extensions Windows runs a program by there)."""
    for suffix in ((".exe", ".cmd", ".bat", ".com") if sys.platform == "win32" else ("",)):
        if (folder / (program + suffix)).is_file():
            return folder / (program + suffix)
    return None


def app_path_file(program: str) -> Path | None:
    """The file the Windows registry (``App Paths``) gives for ``program.exe``, or None. PDFMD_NO_APP_PATHS=1 skips it; that
    switch is for the tests (a test that hides a tool must not find it through the registry), not a setting."""
    if sys.platform != "win32" or os.environ.get("PDFMD_NO_APP_PATHS"):
        return None
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{program}.exe") as key:
                value = winreg.QueryValueEx(key, "")[0]
        except OSError:
            continue
        file = Path(os.path.expandvars(str(value).strip().strip('"')))
        if file.is_file():
            return file
    return None


def locate_tool(name: str) -> tuple[str | None, str]:
    """(the tool's file, how it was found) for a tool of FOUND_TOOLS: ``"key"`` (the config's ``options.<tool>-path``, a file or a
    folder; a folder only for poppler), ``"path"`` (PATH), ``"probe"`` (the usual Windows install folders, then the registry's
    App Paths), or (None, ""). A key that names nothing is said once and passed over."""
    key, programs, folders, roots, _ = FOUND_TOOLS[name]
    if found := next((pinned_program(program) for program in programs if pinned_program(program)), None):
        return found, "key"
    named = core.config_options().get(key) if key else None
    if isinstance(named, str) and named.strip():
        place = Path(os.path.expandvars(named.strip())).expanduser()
        found = named_program(place, programs, name)
        if found:
            return str(found), "key"
        if f"{key}:{named}" not in core.TOOL_WARNED:
            core.TOOL_WARNED.add(f"{key}:{named}")
            emit("warning", None, f"WARN  config: options.{key} ({named}) holds no {programs[0]}; looking on PATH and in the usual folders",
                  file=sys.stderr)
    for program in programs:
        found = core.which(program)
        if found:
            return found, "path"
    if sys.platform == "win32":
        places = [Path(os.environ[variable]) / below for variable, below in WINDOWS_INSTALL_ROOTS if os.environ.get(variable)]
        for root in places:
            for pattern in folders:
                for folder in sorted(root.glob(pattern), reverse=True):
                    for program in programs:
                        if tool_program(folder, program):
                            return str(tool_program(folder, program)), "probe"
        for variable, below in roots:
            for folder in sorted(Path(os.environ[variable]).glob(below), reverse=True) if os.environ.get(variable) else []:
                for program in programs:
                    if tool_program(folder, program):
                        return str(tool_program(folder, program)), "probe"
        for program in programs:
            if app_path_file(program):
                return str(app_path_file(program)), "probe"
    return None, ""


def use_found_tools() -> None:
    """A tool that is installed but not on PATH (a Windows installer often leaves it off) is used all the same: its folder goes
    on PATH for pdfmd's own runs and the programs and filters it starts, in front when the config names it, behind otherwise.
    ``--doctor`` says where it was found."""
    for name, (_, _, _, _, on_path) in FOUND_TOOLS.items():
        file, how = locate_tool(name)
        if how not in ("key", "probe"):
            continue
        TOOLS_FOUND[name] = (file, how)
        if name == "chrome" and how == "key":
            os.environ.setdefault("PDFMD_BROWSER", file)       # the browser engines already read this for Chrome
        entries = os.environ.get("PATH", "").split(os.pathsep)
        folder = str(Path(file).parent)
        if on_path and folder not in entries:
            order = [folder, *entries] if how == "key" else [*entries, folder]
            os.environ["PATH"] = os.pathsep.join(entry for entry in order if entry)


SOFFICE_TIMEOUT = 300.0          # seconds a LibreOffice run may take when nothing says otherwise: the `soffice-timeout` setting's default


def soffice_timeout_from(value) -> float:
    """The `soffice-timeout` setting as seconds: 0 = LibreOffice is never run, a negative number = no limit, not set or
    not a number = SOFFICE_TIMEOUT."""
    number = core.option_flag_number(value)
    return SOFFICE_TIMEOUT if number is None else number


def soffice_limit() -> float:
    """Seconds one LibreOffice run may take (0: never run it; negative: no limit). The environment variable `PDFMD_NO_SOFFICE`
    (any non-empty value) means 0 whatever the settings say: an agent's sandbox crashes LibreOffice and leaves a crash dialog."""
    if os.environ.get("PDFMD_NO_SOFFICE"):
        return 0
    return core.SOFFICE_TIMEOUT_NOW if core.SOFFICE_TIMEOUT_NOW is not None else soffice_timeout_from(core.config_options().get("soffice-timeout"))


def run_soffice(command: list[str], **options) -> subprocess.CompletedProcess:
    """subprocess.run for a LibreOffice command under the `soffice-timeout` limit: output captured as text, and when the
    time is up the whole process tree is stopped (the launcher starts the real program as a child) and the result is a
    failed run whose stderr names the setting. `cwd` is the only option passed on."""
    limit = soffice_limit()
    if limit == 0:
        return subprocess.CompletedProcess(command, 1, "", "LibreOffice is turned off by the setting `soffice-timeout: 0`")
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                               cwd=options.get("cwd"), **flags)
    try:
        out, err = process.communicate(timeout=None if limit < 0 else limit)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
        process.communicate()
        return subprocess.CompletedProcess(command, 124, "", f"LibreOffice did not finish in {limit:g} s and was stopped "
                                           "(the setting `soffice-timeout`: seconds, 0 = never run it, -1 = no limit)")
    return subprocess.CompletedProcess(command, process.returncode, out, err)


def tool_folders_off_path() -> list[tuple[str, str]]:
    """(folder, why) for each folder of a tool pdfmd found off PATH that `pdfmd --user-path add` may put on the user PATH: the
    tools whose folder holds only their own programs (not LibreOffice or Chrome, whose folders hold others) and a TeX install."""
    found: dict[str, str] = {}
    for name, (file, _) in TOOLS_FOUND.items():
        if FOUND_TOOLS[name][4]:
            found.setdefault(str(Path(file).parent), f"{name} found there")
    if core.TEX_FOUND_AT is not None:
        found.setdefault(str(core.TEX_FOUND_AT), "TeX found there")
    return list(found.items())


def resolve_soffice() -> str | None:
    """Locate the LibreOffice/soffice binary, beyond a bare PATH lookup.

    A common real-world setup (confirmed on this machine) has `soffice`
    reachable only through an interactive shell alias pointing straight at
    the macOS .app bundle's own binary -- invisible to both which() and
    subprocess (neither one consults shell aliases, only PATH), so a plain
    which("soffice") silently reports it missing even though it works
    fine for the user every day at a terminal prompt. Checked, in order:
    `options.soffice-path` of the config, `soffice` on PATH, `libreoffice` on
    PATH (the usual Linux package name -- often a symlink to the same binary),
    then the standard macOS app-bundle path directly, or on Windows the usual
    install folders and the registry's App Paths (see locate_tool()).
    """
    if soffice_limit() == 0:                 # `soffice-timeout: 0`: LibreOffice is turned off, whatever is installed
        return None
    found = locate_tool("soffice")[0]
    if found:
        return found
    if sys.platform == "darwin":
        mac_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if mac_path.exists():
            return str(mac_path)
    return None


def calibre_own_folders() -> list[Path]:
    """The Calibre folders `pdfmd --install calibre` unpacked (data_root()/calibre/<version>), newest first."""
    try:
        found = [folder for folder in (core.data_root() / "calibre").iterdir() if folder.is_dir()]
    except OSError:
        return []
    return sorted(found, key=lambda folder: tuple(int(part) for part in re.findall(r"\d+", folder.name)), reverse=True)


def resolve_calibre() -> str | None:
    """Calibre's `ebook-convert`: on PATH (Linux packages, Homebrew's cask), else where the installers put it
    without touching PATH (the macOS app bundle, `%ProgramFiles%\\Calibre2` on Windows). `PDFMD_CALIBRE` names the file
    instead, or an empty value says there is none (the tests of the no-Pandoc tier use it)."""
    if "PDFMD_CALIBRE" in os.environ:
        named = os.environ["PDFMD_CALIBRE"]
        return named if named and Path(named).is_file() else None
    found = core.which("ebook-convert")
    if found:
        return found
    places: list[Path] = [folder / "ebook-convert" for folder in calibre_own_folders()]      # `pdfmd --install calibre` (Linux)
    if sys.platform == "darwin":
        places += [Path(folder) / "calibre.app" / "Contents" / "MacOS" / "ebook-convert"
                   for folder in ("/Applications", Path.home() / "Applications")]
    found = next((str(place) for place in places if place.is_file()), None)
    if found is None and sys.platform == "win32":
        found = locate_tool("calibre")[0]
    return found


def engine_executable(engine: str) -> str | None:
    """which(), except for "soffice" -- see resolve_soffice()'s docstring -- and "calibre" (its `ebook-convert`).

    Every PDF_ENGINES membership check (installed_engines, select_engines,
    dependency_report) goes through this instead of a bare which() so
    "soffice" is recognized as available under the same real-world
    condition the pipeline will actually invoke it under.
    """
    if engine == "calibre":
        return core.resolve_calibre()
    if engine in core.BROWSER_ENGINES:
        try:
            import pdfmd_direct as direct
        except ImportError:
            return None
        return direct.find_browser(engine, core.which)
    return core.resolve_soffice() if engine == "soffice" else core.which(engine)


def tools_directory() -> Path:
    return core.data_root() / "bin"


def bundled_pandoc_directory() -> Path | None:
    """The folder of the Pandoc that `pip install pypandoc_binary` brings, if any."""
    try:
        spec = importlib.util.find_spec("pypandoc")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    folder = Path(spec.origin).parent / "files"
    return folder if any((folder / name).is_file() for name in ("pandoc", "pandoc.exe")) else None


def managed_tool_directories() -> list[Path]:
    return [folder for folder in (tools_directory(), bundled_pandoc_directory())
            if folder is not None and folder.is_dir()]


def use_managed_tools() -> None:
    """Make the tools `pdfmd --install` put in place findable, behind whatever the
    user has on PATH (a system Pandoc or Typst always wins over ours)."""
    entries = os.environ.get("PATH", "").split(os.pathsep)
    extra = [str(folder) for folder in managed_tool_directories() if str(folder) not in entries]
    if extra:
        os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), *extra]).strip(os.pathsep)
    use_tex_install()
    use_found_tools()


TEX_ENGINE_NAMES = ("lualatex", "xelatex", "pdflatex", "latexmk")


def tex_install_patterns(system: str | None = None, environ: dict | None = None) -> list[str]:
    """Where TeX Live and MiKTeX put their programs when the installer did not (or could not) add them to PATH:
    glob patterns, the year of a TeX Live (`bin/windows`, `bin/x86_64-linux`) matched by `*`, newest first once sorted."""
    system = (system or platform.system()).lower()
    environ = os.environ if environ is None else environ
    patterns: list[str] = []
    if system == "windows":
        drive = environ.get("SystemDrive", "C:")
        program_files = [environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        for root in dict.fromkeys([f"{drive}\\texlive", *(f"{base}\\texlive" for base in program_files if base),
                                   str(Path(environ.get("USERPROFILE", "~")).expanduser() / "texlive")]):
            patterns.append(str(Path(root) / "*" / "bin" / "*"))
        miktex = [str(Path(environ["LOCALAPPDATA"]) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64")] \
            if environ.get("LOCALAPPDATA") else []
        patterns += miktex + [str(Path(base) / "MiKTeX*" / "miktex" / "bin" / "x64") for base in program_files if base]
    else:
        patterns += ["/usr/local/texlive/*/bin/*", str(Path("~/texlive").expanduser() / "*" / "bin" / "*"),
                     "/Library/TeX/texbin", "/usr/texbin"]
    return patterns


def find_tex_directory(patterns: list[str]) -> Path | None:
    """The first (newest year first) folder among the glob patterns that holds a TeX engine program."""
    import glob
    found: list[Path] = []
    for pattern in patterns:
        found += [Path(match) for match in glob.glob(pattern) if Path(match).is_dir()]
    for folder in sorted(found, key=lambda path: str(path), reverse=True):
        if any((folder / (name + suffix)).is_file() for name in TEX_ENGINE_NAMES for suffix in ("", ".exe")):
            return folder
    return None


def use_tex_install() -> None:
    """A TeX that is installed but not on PATH (TeX Live's installer on Windows can leave it off, a shell started before
    the install does not have it yet) is used all the same: its folder goes behind PATH, for pdfmd's own runs.
    `PDFMD_TEX_BIN` names a folder for an install in an unusual place. Nothing is done when a TeX engine is on PATH."""
    if any(shutil.which(name) for name in TEX_ENGINE_NAMES):
        return
    chosen = os.environ.get("PDFMD_TEX_BIN", "").strip()
    folder = find_tex_directory([chosen]) if chosen else None
    folder = folder or find_tex_directory(tex_install_patterns())
    if folder is None:
        return
    core.TEX_FOUND_AT = folder
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), str(folder)]).strip(os.pathsep)


def pandoc_user_data_dir() -> Path | None:
    """Pandoc's user data directory (where it also looks for a `csl:` style, in
    its `csl/` subfolder), from the "User data directory:" line of
    `pandoc --version`; None if there is none."""
    if core._PANDOC_DATA_DIR is False:
        core._PANDOC_DATA_DIR = None
        done = core.run_probe(["pandoc", "--version"])
        for line in (done.stdout if done else "").splitlines():
            if line.lower().startswith("user data directory:"):
                core._PANDOC_DATA_DIR = Path(line.split(":", 1)[1].strip())
    return core._PANDOC_DATA_DIR or None


def pandoc_version() -> tuple[int, ...]:
    if core._PANDOC_VERSION is None:
        try:
            done = core.run_probe(["pandoc", "--version"])
            first = done.stdout.splitlines()[0]                                  # (no answer: an AttributeError, below)
            core._PANDOC_VERSION = tuple(int(part) for part in re.search(r"(\d+(?:\.\d+)+)", first).group(1).split("."))
        except (OSError, IndexError, AttributeError, ValueError):
            core._PANDOC_VERSION = (0,)
    return core._PANDOC_VERSION


# `pandoc --version`, `kpsewhich`, `typst --version` ... answer at once; a hung one (a broken install, a network drive, a tool
# waiting on a prompt) must not hang pdfmd. A probe gets PROBE_TIMEOUT seconds, and one that does not answer counts as "not
# available" (a verbose line says so). Never used for a command that builds something (Pandoc, a LaTeX engine, a converter):
# those take as long as the document needs.
PROBE_TIMEOUT = 10


def run_probe(command: list, **options) -> "subprocess.CompletedProcess | None":
    """``subprocess.run`` of a probe: output captured as text, PROBE_TIMEOUT s. None when the program cannot be started or does
    not answer in time. The text is read as UTF-8 (what kpsewhich, Pandoc and fc-list write), a byte that is not UTF-8
    replaced: left to `text=True` alone, Windows would decode with the console's code page (issue 13)."""
    options.setdefault("capture_output", True)
    options.setdefault("text", True)
    options.setdefault("encoding", "utf-8")
    options.setdefault("errors", "replace")
    try:
        return pandoc_run(command, timeout=core.PROBE_TIMEOUT, **options)
    except subprocess.TimeoutExpired:
        if core.VERBOSE_OUTPUT:
            asked = " ".join(Path(str(command[0])).name if index == 0 else str(word) for index, word in enumerate(command[:3]))
            emit("normal", "PROBE", f"AUTO PROBE  {asked}: no answer in {core.PROBE_TIMEOUT} s; counted as not available")
        return None
    except OSError:
        return None


def kpsewhich_path(name: str) -> Path | None:
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich:
        return None
    done = core.run_probe([kpsewhich, name])
    found = done.stdout.strip().splitlines() if done else []
    return Path(found[0]) if found else None


@lru_cache(maxsize=None)
def _engine_version_line(program: str) -> str:
    done = core.run_probe([program, "--version"])
    out = done.stdout if done else ""
    return out.splitlines()[0] if out else ""


def engine_version_line(engine: str) -> str:
    program = pinned_program(engine) or engine
    if engine == "soffice":                    # found beyond PATH too; on Windows soffice.exe is the window launcher, which does not
        program = core.engine_executable("soffice") or engine      # answer --version and leaves soffice.bin running: soffice.com does
        if os.name == "nt" and Path(program).suffix.lower() == ".exe" and Path(program).with_suffix(".com").is_file():
            program = str(Path(program).with_suffix(".com"))
    return _engine_version_line(program)


engine_version_line.cache_clear = _engine_version_line.cache_clear


def typst_version() -> tuple[int, ...]:
    """The version of the `typst` on PATH, (0,) when there is none or it says something else."""
    found = re.search(r"(\d+(?:\.\d+)+)", engine_version_line("typst"))
    return tuple(int(part) for part in found.group(1).split(".")) if found else (0,)

# pdfmd on Windows: environment problems and how to fix them

Each entry says what you see, why it happens, and what to do. "Observed" means it happened
while testing pdfmd 3.31.6 to 3.31.15 on Windows 11 (Python 3.14, Pandoc 3.12, a Russian-language system with the cp1251 locale).
"Standard Windows behaviour" means the cause is how Windows works and was not measured here.

---

## 1. A tool is installed, but pdfmd (or `pdfmd --doctor`) says it is missing

**Observed.** Tesseract, Graphviz (`dot`), Mermaid (`mmdc`), poppler, LibreOffice and Calibre can all be installed and
still not be found: their installers put them in `C:\Program Files\...`, `%LOCALAPPDATA%\Programs\...` or a folder of the
user's choosing (for example on a second drive), and many do not add that folder to PATH.

**Why.** Before pdfmd 3.31.10 it looked for most tools with a plain PATH search; only Pandoc, LibreOffice and Calibre also
had a list of usual Windows folders.

**Fix.**
- Add the tool's folder to the user PATH (Settings → System → About → Advanced system settings → Environment Variables →
  `Path` under *User variables*), then open a **new** terminal.
- Check with `pdfmd --doctor`, which names what it found and where.
- Since pdfmd 3.31.10 (Tesseract, LibreOffice, Graphviz, Mermaid, Poppler) and 3.31.11 (Pandoc, Typst, Chrome) pdfmd looks for these tools itself (Program Files, `%LOCALAPPDATA%\Programs`, the registry
  "App Paths" entry that an installer writes, and `%APPDATA%\npm` for Mermaid) and uses what it finds, and `--doctor` says
  "found at X, not on PATH (pdfmd uses it anyway)". To name a folder yourself, use `options.tesseract-path`,
  `soffice-path`, `dot-path`, `mmdc-path`, `poppler-path`, `pandoc-path`, `typst-path` or `chrome-path` in `pdfmd --setup`
  (the "Tool locations" section). A key that names a missing folder gives one warning and the search goes on.
- A tool that is not run by pdfmd itself (for example your own script calling `tesseract`) still needs PATH.
- In tests, `PDFMD_NO_APP_PATHS=1` switches the registry lookup off; it is not meant for users.

## 2. A terminal started before the install does not see the new tool

**Observed.** A program (an editor, an IDE terminal, a long-running shell) keeps the environment it was started with.
After installing TeX Live or any other tool, `where xelatex` still finds nothing in that window, while a brand-new
terminal finds it. Test runs in the old window then skip or fail the tests that need the tool.

**Why.** Standard Windows behaviour: a process gets a copy of the environment when it starts; later PATH changes reach
only processes started afterwards.

**Fix.** Close and reopen the terminal, or in PowerShell rebuild PATH for the current window:

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
```

## 3. "UnicodeDecodeError", garbled letters, or `None` instead of output (cp1251, cp1252, cp866 ...)

**Observed.** With a non-UTF-8 system locale (here cp1251), a Python script that runs `pdfmd` and reads its output with
`subprocess.run(..., text=True)` decodes the UTF-8 text with the locale's code page: letters come out as `В°` or `в€’`,
or the call fails and the output is `None`. pdfmd itself writes valid UTF-8.

**Why.** Python on Windows decodes text with the ANSI code page unless told otherwise.

**Fix.** For your own scripts pass `encoding="utf-8"` to `subprocess.run` and `open`. To make Python use UTF-8 everywhere:

```powershell
setx PYTHONUTF8 1          # new terminals only
```

(or Settings → Time & language → Language & region → Administrative language settings → *Beta: Use Unicode UTF-8 for
worldwide language support*, which affects the whole system and needs a restart).

## 4. "A required privilege is not held by the client" (WinError 1314) when pdfmd makes a link

**Observed.** Creating a symbolic link fails for an ordinary user. `pdfmd --split` used to stop with a traceback; it now
copies the files beside the document instead (fixed in pdfmd 3.31.7).

**Why.** Standard Windows behaviour: only an elevated process, or any process when Developer Mode is on, may create
symbolic links.

**Fix.** Turn on Developer Mode (Settings → System → For developers → Developer Mode), or run the shell as
administrator. A copy works for pdfmd, but a link keeps one file in one place.

## 5. `python3` does nothing, or opens the Microsoft Store

**Observed.** `python3` resolves to `...\WindowsApps\python3.exe`, a Store stub, not a Python. Anything that starts
`python3` by name (older scripts, some filters) fails. pdfmd's own routes pass the interpreter they run in
(`sys.executable`), so pdfmd itself is not affected; tests and your own scripts may be.

**Why.** Standard Windows behaviour: the installer of Python from python.org provides `python` and `py`, not `python3`.

**Fix.** Use `python` or `py -3`. To get rid of the stub: Settings → Apps → Advanced app settings → App execution
aliases → turn off *python.exe* and *python3.exe*.

## 6. A leftover copy of pdfmd hides the one you are testing

**Observed.** With a global `pip install pdfmd-cli` and a virtual environment created with `--system-site-packages`,
the environment loaded the global package, not the checked-out code, so test results described the wrong version.

**Fix.** Test in a clean virtual environment (`python -m venv venv`, no `--system-site-packages`), install the checkout
with `pip install -e ".[math]"`, and confirm with `python -c "import pdfmd; print(pdfmd.__file__)"`.

## 7. LibreOffice: a conversion never finishes, a console window asks to press Enter

**Observed.** pdfmd started `soffice` with a profile folder given as `file://C:\Users\...\profile`, which is not a file
URL. Headless LibreOffice then waited for ever (more than 25 minutes, almost no CPU) and wrote nothing. A console
window from `soffice.com` can sit open showing "Failed to read file ..." / "Could not find platform independent
libraries" until a key is pressed. Fixed in pdfmd 3.31.9 (pdfmd now passes `file:///C:/...`) in all three places that start soffice (the Office converter,
the ODF reader and the SVG converter).

A message box "Cannot start the application. The configuration file ... `program\bootstrap.ini` is corrupt" can appear
for the same reason: it is the wording LibreOffice uses when it cannot make sense of its start-up arguments, not a damaged
file (the file stays intact; check its size and date). Reproduced with the malformed profile URL: soffice exits with code 1
and makes no PDF; with a proper `file:///` URL the same file converts. If it appears with a current pdfmd, look for a
program or script of your own that starts `soffice` with `-env:UserInstallation=file://C:\...`.

**If it still hangs.**
- Look for stray LibreOffice processes (`Get-Process soffice*`) and end them; a process left from an earlier run keeps
  its profile locked.
- The first start with a new profile takes about 20 to 30 seconds; later ones are quicker.
- `soffice.com` is the console launcher and `soffice.exe` the window one; a script should wait for the process, not for a key.

## 8. "The process cannot access the file because it is being used by another process" (WinError 32)

**Observed.** Deleting or replacing a file fails while something still has it open: an unclosed archive in a script, a
PDF viewer, an editor, a virus scanner. On Linux and macOS the same delete works.

**Fix.** Close the file (`with zipfile.ZipFile(...) as z:` in Python), close the viewer, retry. For temporary folders,
close every handle before the folder is removed.

## 9. A Git Bash command is given a Windows path

**Observed.** `bash -n C:\Users\me\x.bash` (from a script) fails with "No such file or directory": the backslashes were
taken as escapes and the path became `C:Usersmex.bash`.

**Fix.** Give POSIX shells forward-slash paths (`C:/Users/me/x.bash`) or run them in the file's folder with a bare name.
`bash` may also be WSL's launcher (`C:\Windows\System32\bash.exe`) in place of Git Bash; the two see paths differently.

## 10. Native-command quirks in Windows PowerShell 5.1 (not 7)

**Observed.** `&&` and `||` are a syntax error; piping JSON into a program with `|` can change its bytes (encoding
and line endings); `2>&1` on a native program turns its stderr lines into error records.

**Fix.** Use PowerShell 7 (`winget install Microsoft.PowerShell`), or write the data to a file and pass the file.

## 11. Not enough memory for long test runs

**Observed.** On a machine with 8 GB of RAM, hours-long background runs (the whole test suite, LaTeX builds) were
ended by the tool that started them when physical memory ran low; the page file (swap) did not count.

**Fix.** Run the suite in pieces (one test module at a time, resuming from the ones that finished), close other
programs, or give the machine more RAM.

## 12. Non-English Windows

**Observed.** Error messages from Windows arrive in the system language (for example the Russian text of WinError 32).
Anything that matches them against English words will not match.

**Fix.** Match on the error code (`WinError 32`, `errno`) and not on the message text.

## 13. A Windows path inside a value that another program re-reads (backslashes disappear)

**Observed.** A diagram, a spreadsheet block (`.csv` of an `.xlsx`), a converted SVG or a raw filter failed on Windows with
"could not open ...", "File `C:-1234.pdf' not found" or an empty result. pdfmd had passed a path such as
`C:\Users\ann\AppData\Local\pdfmd\sheets\ab12.csv` to Pandoc as metadata, or to LaTeX as text.

**Why.** Pandoc reads metadata strings as Markdown, which removes backslashes; LaTeX reads a backslash as the start of a
command. Forward slashes are accepted by Windows, Pandoc, Lua and LaTeX alike.

**Fix (for pdfmd code and for your own filters).** Write such a path with `Path(...).as_posix()`. Fixed so far: the raw
filters and diagrams (3.31.8), the image map of converted SVG pictures (3.31.13) and the spreadsheet map (3.31.15). Mermaid's
`mmdc` is a `.cmd` file on Windows and Pandoc's `pipe` cannot start a `.cmd` directly, so since 3.31.12 pdfmd starts it
through `cmd /c`.

## 14. Where pdfmd keeps its files on Windows (matters for scripts and tests)

- Settings and the "shown once" notices: `%APPDATA%\pdfmd` (macOS and Linux: `$XDG_CONFIG_HOME/pdfmd`).
- Cache, build records, converted pictures: `%LOCALAPPDATA%\pdfmd` (macOS and Linux: `$XDG_CACHE_HOME/pdfmd`).
- A script or test that sets only the `XDG_*` variable still reads and writes the real folder on Windows. Set both:
  `XDG_CONFIG_HOME` and `APPDATA`, `XDG_CACHE_HOME` and `LOCALAPPDATA`. Setting `HOME` alone is not enough either: the home
  folder is `USERPROFILE`.
- A test that empties PATH to run "without Pandoc" must also stop the install-folder search (see section 1).

## 15. Shell scripts that pdfmd prints get CRLF line ends

**Observed.** `source <(pdfmd --completion bash)` in Git Bash or WSL fails with "syntax error near unexpected token
`$'{\r''`".

**Why.** Python's text-mode standard output turns each newline into CRLF on Windows, and bash does not accept a carriage
return in a script.

**Fix.** Fixed in pdfmd 3.31.14 (the command now keeps plain newlines). For any other script written from Python for a POSIX
shell, write bytes or open the file with `newline="\n"`; `Path.write_text` also translates newlines on Windows.

## 16. Tests that need a symbolic link or a POSIX shell

Without Developer Mode (or an elevated shell) a Windows account may not create symbolic links (WinError 1314): such tests
skip with that reason, or copy the file instead of linking it. Tests that use `sh` scripts as stand-ins for a tool are
skipped on Windows; a stand-in there is a `.cmd` file (arguments arrive quoted, so use `%~4` and not `%4`).

---

## Quick check before reporting a Windows problem

1. `pdfmd --version` and `pdfmd --doctor` from a **new** terminal.
2. `python -c "import pdfmd; print(pdfmd.__file__)"`: which copy is it?
3. `where pandoc xelatex lualatex tesseract dot mmdc pdftocairo soffice` in the same terminal.
4. `python -c "import locale,sys; print(locale.getpreferredencoding(), sys.flags.utf8_mode)"`.
5. For a failing build: `pdfmd FILE --verbose` and `pdfmd --last-build FILE`.

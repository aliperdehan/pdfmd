# Colophon for Windows (trial)

A thin native Windows shell for the web UI in `../lib/pdfmd_web/`, served by `pdfmd --serve`: .NET 8, WPF and
WebView2. It is not a port of the Mac app in `../gui/`; pdfmd's logic stays in pdfmd.

WPF is the frame because it needs no Windows App SDK and no extra installer: a `dotnet publish` folder plus the
WebView2 runtime that Windows 11 already has is enough. WinUI 3 would add the Windows App SDK runtime and a
packaging step for no gain in a window that is mostly a WebView2.

## Build and run

    dotnet build gui-win/ColophonWin.csproj
    gui-win/bin/Debug/net8.0-windows/colophon-win.exe [FILE|FOLDER]

Needs the .NET 8 SDK and the WebView2 runtime. `pdfmd` must be on `PATH` (`pip install -e .` in the pdfmd clone);
`COLOPHON_PDFMD` may name its executable instead. Startup data (WebView2 profile, window rectangle, settings) lives
in `%LOCALAPPDATA%\Colophon`; `COLOPHON_DATA_DIR` moves it.

`Open Folder` (Ctrl+O) shows the folder's project in the web studio. The shell starts `pdfmd --serve FOLDER` and
loads the URL the server prints; the server chooses a free localhost port and its own token. A file argument opens
that folder on that file. The child runs in a job object that kills it when the shell closes, including when the
shell is killed or crashes; the status bar says when a server has stopped. Ctrl+O is also taken from the page and
sent back to the native folder dialogue.

`Build` (Ctrl+B) saves the file the studio is on, runs `pdfmd FILE.md` in its folder and shows the PDF in a pane below
the page, beside a log of what pdfmd printed. A failed build, a timeout or a PDF pdfmd did not name is reported in the
status bar and in the log. The PDF is the one named in pdfmd's `OK source > output in ... (engine)` line; a part of a
project therefore shows its parent's PDF. Ctrl+B is the shell's: the page's own Ctrl+B (bold) does not reach the
editor while the shell is in front.

Light and dark follow Windows and update live; the window's size and position are remembered between runs; the page's
own shortcuts keep working inside WebView2. Closing with unsaved changes asks first, using the page's own answer when it
can answer, otherwise the last state it reported.

Settings are read from `%LOCALAPPDATA%\Colophon\settings.json` (all seconds; defaults in brackets):
`BuildTimeoutSeconds` [600], `ServerStartTimeoutSeconds` [20], `SaveTimeoutSeconds` [15], `BuildPaneHeight` [260].

## Package

    powershell -ExecutionPolicy Bypass -File gui-win\publish.ps1

runs `dotnet publish` for win-x64, self-contained, into `gui-win\publish\` (about 146 MB). That folder runs on a
clean Windows 11 with only the WebView2 runtime, which Windows 11 carries by default; there is no installer. The
executable is `colophon-win.exe`.

## Tests

    colophon-win.exe --selftest

runs the checks that need no window: the command line, pdfmd's location and child environment, the build-line parser,
window placement, settings and the child job.

`--smoke` runs a real page through `pdfmd --serve`, saves an edit, builds a PDF through pdfmd and checks the PDF pane;
it uses a scratch project and never a real document. `--smoke-crash` simulates a crash for the job-object check
(`COLOPHON_CRASH_PIDFILE` names the file that receives the server's process id). The close prompt and the visual
result on screen are not verified by hand.

## What this commit has

The shell, its `pdfmd --serve` page and the build pane. The native window behaviour follows in the next commit of the
trial.

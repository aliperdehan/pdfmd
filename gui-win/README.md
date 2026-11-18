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

Settings are read from `%LOCALAPPDATA%\Colophon\settings.json` (all seconds; defaults in brackets):
`BuildTimeoutSeconds` [600], `ServerStartTimeoutSeconds` [20], `SaveTimeoutSeconds` [15], `BuildPaneHeight` [260].

## Tests

    colophon-win.exe --selftest

runs the checks that need no window: the command line, pdfmd's location and child environment, window placement,
settings, theme and the child job.

## What this commit has

The shell and its `pdfmd --serve` page. Building a PDF from the page follows in the next commit of the trial.

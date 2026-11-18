# Colophon for Windows (trial)

A thin native Windows shell for the web UI in `../lib/pdfmd_web/`, served by `pdfmd --serve`: .NET 8, WPF and
WebView2. It is not a port of the Mac app in `../gui/`; pdfmd's logic stays in pdfmd.

WPF is the frame because it needs no Windows App SDK and no extra installer: a `dotnet publish` folder plus the
WebView2 runtime that Windows 11 already has is enough. WinUI 3 would add the Windows App SDK runtime and a
packaging step for no gain in a window that is mostly a WebView2.

## Build and run

    dotnet build gui-win/ColophonWin.csproj
    gui-win/bin/Debug/net8.0-windows/colophon-win.exe

Needs the .NET 8 SDK and the WebView2 runtime. `pdfmd` must be on `PATH` (`pip install -e .` in the pdfmd clone);
`COLOPHON_PDFMD` may name its executable instead. Startup data (WebView2 profile, window rectangle, settings) lives
in `%LOCALAPPDATA%\Colophon`; `COLOPHON_DATA_DIR` moves it.

Settings are read from `%LOCALAPPDATA%\Colophon\settings.json` (all seconds; defaults in brackets):
`BuildTimeoutSeconds` [600], `ServerStartTimeoutSeconds` [20], `SaveTimeoutSeconds` [15], `BuildPaneHeight` [260].

## Tests

    colophon-win.exe --selftest

runs the checks that need no window. `--smoke` runs a real page through `pdfmd --serve`, saves an edit, builds a PDF
through pdfmd and checks the PDF pane; it uses a scratch project and never a real document. `--smoke-crash` simulates
a crash for the job-object check (`COLOPHON_CRASH_PIDFILE` names the file that receives the server's process id).

## What this commit has

The shell window and its WebView2 page. The studio, its server and the build follow in the next commits of the trial.

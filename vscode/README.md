# pdfmd for VS Code

A thin layer over the [`pdfmd`](https://github.com/aliperdehan/pdfmd) command (`pipx install pdfmd-cli`): every
command here is a pdfmd command line that is also written to the **pdfmd** output panel, so what it ran is always
visible and the same line works in a terminal.

| Command (palette: *pdfmd: ...*) | Keys | What it runs |
|---|---|---|
| Build | `Cmd/Ctrl+Alt+B`, the play button, the status bar | `pdfmd FILE` (the file is saved first) |
| Build and open the result | `Cmd/Ctrl+Alt+O` | the same, then opens the PDF |
| Build as Word, OpenDocument, HTML, Typst... | | `pdfmd FILE -o FILE.docx` and so on; slides with `-p` |
| Rebuild on every change | | `pdfmd -w FILE` in a terminal |
| Extract tables to CSV files | | `pdfmd --extract-tables [--table-numbers 2] [--dry-run] FILE` |
| Expand CSV blocks back to tables | | `pdfmd --expand-tables FILE` |
| Insert `<!-- pdfmd: ignore -->` above this line | | keeps one table or block out of extraction |
| Show the history / Compare / Restore a version | | `pdfmd --history`, `--history-diff REF`, `--history-restore REF` |
| Restore the source a PDF carries | right-click a PDF | `pdfmd --restore FILE.pdf` |
| Check what pdfmd can use | | `pdfmd --doctor` |

Settings: `pdfmd.command` (default `pdfmd`; `python3 /path/to/pdfmd.py` works), `pdfmd.extraArguments` (added to every
build, e.g. `["-e", "lualatex", "--attach-source"]`), `pdfmd.buildOnSave`, `pdfmd.openAfterBuild`.

## Install

From a clone of the repository:

```sh
cd vscode && npx @vscode/vsce package     # writes pdfmd-vscode-0.1.0.vsix
code --install-extension pdfmd-vscode-0.1.0.vsix
```

or copy this folder to `~/.vscode/extensions/pdfmd-vscode` and restart VS Code. `npm test` runs the extension against a
stand-in for the VS Code API and the real pdfmd.

No extension at all: `pdfmd --init-vscode` writes a `.vscode/tasks.json` with build, build-and-open and watch tasks
(Terminal > Run Build Task, `Cmd/Ctrl+Shift+B`).

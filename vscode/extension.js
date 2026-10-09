// pdfmd for VS Code: a thin layer over the `pdfmd` command. Everything it does is a pdfmd command line shown in the
// "pdfmd" output channel, so what it ran is always visible and the same line works in a terminal.
"use strict";

const vscode = require("vscode");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let output;
let statusItem;

// `pdfmd`, `"/path with spaces/pdfmd"` or `python3 /path/pdfmd.py` -> an argv prefix
function splitCommand(text) {
  const parts = [];
  const pattern = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let match;
  while ((match = pattern.exec(text || "pdfmd")) !== null) {
    parts.push(match[1] !== undefined ? match[1] : match[2] !== undefined ? match[2] : match[3]);
  }
  return parts.length ? parts : ["pdfmd"];
}

function settings() {
  const config = vscode.workspace.getConfiguration("pdfmd");
  return {
    command: splitCommand(config.get("command", "pdfmd")),
    extra: config.get("extraArguments", []),
    openAfter: config.get("openAfterBuild", false),
    onSave: config.get("buildOnSave", false),
  };
}

function say(text) {
  output.appendLine(text);
}

// Run pdfmd with `args` in `cwd`; resolves {code, text}. The line that was run is written first.
function run(args, cwd, { withExtra = false } = {}) {
  const { command, extra } = settings();
  const argv = [...command.slice(1), ...(withExtra ? extra : []), ...args];
  say(`$ ${[command[0], ...argv].map((item) => (/\s/.test(item) ? JSON.stringify(item) : item)).join(" ")}`);
  return new Promise((resolve) => {
    let text = "";
    let child;
    try {
      child = spawn(command[0], argv, { cwd, env: process.env });
    } catch (error) {
      say(`Could not start ${command[0]}: ${error.message}`);
      resolve({ code: 127, text: "" });
      return;
    }
    const take = (chunk) => {
      const piece = chunk.toString();
      text += piece;
      output.append(piece);
    };
    child.stdout.on("data", take);
    child.stderr.on("data", take);
    child.on("error", (error) => {
      say(`Could not start ${command[0]}: ${error.message}. Set pdfmd.command (pip install pdfmd-cli).`);
      resolve({ code: 127, text });
    });
    child.on("close", (code) => {
      say("");
      resolve({ code: code === null ? 1 : code, text });
    });
  });
}

// The file a command is about: the one clicked in the Explorer, else the active editor's.
function targetFile(uri, extensions) {
  let file = uri && uri.fsPath;
  if (!file && vscode.window.activeTextEditor) {
    file = vscode.window.activeTextEditor.document.uri.fsPath;
  }
  if (!file) {
    vscode.window.showWarningMessage("pdfmd: open a file first.");
    return null;
  }
  if (extensions && !extensions.includes(path.extname(file).toLowerCase())) {
    vscode.window.showWarningMessage(`pdfmd: ${path.basename(file)} is not one of ${extensions.join(", ")}.`);
    return null;
  }
  return file;
}

async function saveIfOpen(file) {
  const document = vscode.workspace.textDocuments.find((item) => item.uri.fsPath === file);
  if (document && document.isDirty) {
    await document.save();
  }
}

function openResult(file) {
  return vscode.env.openExternal(vscode.Uri.file(file));
}

async function build(uri, { open = false, args = [], result = null } = {}) {
  const file = targetFile(uri, [".md", ".markdown", ".tex", ".typ", ".html", ".qmd", ".rst", ".txt"]);
  if (!file) return null;
  await saveIfOpen(file);
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: `pdfmd: building ${path.basename(file)}` },
    async () => {
      output.show(true);
      const done = await run([...args, file], path.dirname(file), { withExtra: true });
      if (done.code !== 0) {
        output.show(false);
        vscode.window.showErrorMessage(`pdfmd: the build of ${path.basename(file)} failed (see the pdfmd output).`);
        return null;
      }
      const made = result || path.join(path.dirname(file), path.basename(file, path.extname(file)) + ".pdf");
      const exists = fs.existsSync(made);
      if (open || settings().openAfter) {
        if (exists) await openResult(made);
      } else if (exists) {
        const choice = await vscode.window.showInformationMessage(`pdfmd: built ${path.basename(made)}`, "Open");
        if (choice === "Open") await openResult(made);
      } else {
        vscode.window.showInformationMessage(`pdfmd: built ${path.basename(file)}`);
      }
      return made;
    }
  );
}

const FORMATS = [
  ["Word (.docx)", "docx"],
  ["OpenDocument text (.odt)", "odt"],
  ["HTML, one self-contained file (.html)", "html"],
  ["Typst (.typ)", "typ"],
  ["LaTeX (.tex)", "tex"],
  ["EPUB (.epub)", "epub"],
  ["Beamer slides (PDF)", "slides"],
];

async function buildAs(uri) {
  const file = targetFile(uri, [".md", ".markdown"]);
  if (!file) return;
  const pick = await vscode.window.showQuickPick(FORMATS.map(([label, ext]) => ({ label, ext })), {
    placeHolder: "Build as...",
  });
  if (!pick) return;
  const stem = path.join(path.dirname(file), path.basename(file, path.extname(file)));
  if (pick.ext === "slides") {
    await build(uri, { args: ["-p"], result: stem + ".pdf" });
  } else {
    const out = `${stem}.${pick.ext}`;
    await build(uri, { args: pick.ext === "html" ? ["--self-contained", "-o", out] : ["-o", out], result: out });
  }
}

function watch(uri) {
  const file = targetFile(uri, [".md", ".markdown"]);
  if (!file) return;
  const { command } = settings();
  const terminal = vscode.window.createTerminal({ name: `pdfmd -w ${path.basename(file)}`, cwd: path.dirname(file) });
  terminal.show();
  const quote = (item) => (/[\s"'$`\\]/.test(item) ? JSON.stringify(item) : item);
  terminal.sendText([...command.map(quote), "-w", quote(file)].join(" "));
}

async function tables(uri, expand) {
  const file = targetFile(uri, [".md", ".markdown"]);
  if (!file) return;
  await saveIfOpen(file);
  const cwd = path.dirname(file);
  if (expand) {
    const done = await run(["--expand-tables", file], cwd);
    output.show(true);
    if (done.code === 0) vscode.window.showInformationMessage("pdfmd: tables expanded (the old file is in the backup folder).");
    return;
  }
  const choice = await vscode.window.showQuickPick(
    [
      { label: "All tables", detail: "Every table that can be written as CSV", numbers: null },
      { label: "Only some...", detail: "Give the table numbers, for example 2 or 1,3-4", numbers: "ask" },
      { label: "Preview only (dry run)", detail: "Show what would change; write nothing", numbers: null, dry: true },
    ],
    { placeHolder: "Extract tables to tables/*.csv" }
  );
  if (!choice) return;
  const args = ["--extract-tables"];
  if (choice.numbers === "ask") {
    const answer = await vscode.window.showInputBox({ prompt: "Table numbers (1 is the first)", placeHolder: "1,3-4" });
    if (!answer) return;
    args.push("--table-numbers", answer);
  }
  if (choice.dry) args.push("--dry-run");
  const done = await run([...args, file], cwd);
  output.show(true);
  if (done.code === 0 && !choice.dry) {
    vscode.window.showInformationMessage("pdfmd: tables extracted (the old file is in the backup folder).");
  }
}

async function ignoreHere() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const line = editor.selection.active.line;
  await editor.edit((edit) => edit.insert(new vscode.Position(line, 0), "<!-- pdfmd: ignore -->\n"));
}

async function history(uri, mode) {
  const file = targetFile(uri, [".md", ".markdown"]);
  if (!file) return;
  await saveIfOpen(file);
  const cwd = path.dirname(file);
  if (mode === "list") {
    await run(["--history", file], cwd);
    output.show(true);
    return;
  }
  const answer = await vscode.window.showInputBox({
    prompt: mode === "diff" ? "Compare with which version?" : "Restore which version?",
    placeHolder: "a number from the history, previous, latest, a time such as 2026-10-06, or a commit",
    value: "previous",
  });
  if (!answer) return;
  if (mode === "diff") {
    await run(["--history-diff", answer, file], cwd);
    output.show(true);
    return;
  }
  const sure = await vscode.window.showWarningMessage(
    `Restore ${path.basename(file)} to version "${answer}"? The current file is backed up first.`,
    { modal: true },
    "Restore"
  );
  if (sure === "Restore") {
    const done = await run(["--history-restore", answer, file], cwd);
    output.show(true);
    if (done.code === 0) vscode.window.showInformationMessage(`pdfmd: restored ${path.basename(file)}.`);
  }
}

async function restoreSource(uri) {
  const file = targetFile(uri, [".pdf"]);
  if (!file) return;
  const done = await run(["--restore", file], path.dirname(file));
  output.show(true);
  if (done.code === 0) {
    const folder = path.join(path.dirname(file), path.basename(file, ".pdf") + ".restored");
    if (fs.existsSync(folder)) {
      const choice = await vscode.window.showInformationMessage(`pdfmd: restored into ${path.basename(folder)}`, "Open folder");
      if (choice === "Open folder") await vscode.commands.executeCommand("vscode.openFolder", vscode.Uri.file(folder), true);
    }
  }
}

async function doctor() {
  await run(["--doctor"], (vscode.workspace.workspaceFolders || [{ uri: { fsPath: process.cwd() } }])[0].uri.fsPath);
  output.show(true);
}

function activate(context) {
  output = vscode.window.createOutputChannel("pdfmd");
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  statusItem.text = "$(play) pdfmd";
  statusItem.tooltip = "Build this document with pdfmd";
  statusItem.command = "pdfmd.build";
  const refresh = (editor) => {
    if (editor && ["markdown"].includes(editor.document.languageId)) statusItem.show();
    else statusItem.hide();
  };
  refresh(vscode.window.activeTextEditor);

  const add = (name, handler) => context.subscriptions.push(vscode.commands.registerCommand(name, handler));
  add("pdfmd.build", (uri) => build(uri));
  add("pdfmd.buildOpen", (uri) => build(uri, { open: true }));
  add("pdfmd.buildAs", buildAs);
  add("pdfmd.watch", watch);
  add("pdfmd.extractTables", (uri) => tables(uri, false));
  add("pdfmd.expandTables", (uri) => tables(uri, true));
  add("pdfmd.ignoreHere", ignoreHere);
  add("pdfmd.history", (uri) => history(uri, "list"));
  add("pdfmd.historyDiff", (uri) => history(uri, "diff"));
  add("pdfmd.historyRestore", (uri) => history(uri, "restore"));
  add("pdfmd.restoreSource", restoreSource);
  add("pdfmd.doctor", doctor);
  context.subscriptions.push(
    output,
    statusItem,
    vscode.window.onDidChangeActiveTextEditor(refresh),
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (settings().onSave && document.languageId === "markdown") build(document.uri);
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate, splitCommand };

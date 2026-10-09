// Runs the extension against a stand-in for the `vscode` module and the real pdfmd: a build, a table extraction and a
// history listing. `node test/smoke.js` (needs pdfmd's own dependencies; the repo's pdfmd.py is used, not an installed one).
"use strict";
const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const Module = require("module");

const repo = path.resolve(__dirname, "..", "..");
const handlers = {};
const opened = [];
const messages = [];
let quickPick = (items) => items[0];
let inputBox = () => undefined;
const channel = { appendLine() {}, append() {}, show() {}, dispose() {} };

const vscode = {
  window: {
    createOutputChannel: () => channel,
    createStatusBarItem: () => ({ show() {}, hide() {}, dispose() {} }),
    createTerminal: () => ({ show() {}, sendText: (text) => messages.push("terminal: " + text) }),
    activeTextEditor: null,
    showInformationMessage: async (text) => { messages.push(text); },
    showWarningMessage: async (text) => { messages.push(text); },
    showErrorMessage: async (text) => { messages.push("ERROR " + text); },
    showQuickPick: async (items) => quickPick(items),
    showInputBox: async () => inputBox(),
    withProgress: async (_options, task) => task(),
    onDidChangeActiveTextEditor: () => ({ dispose() {} }),
  },
  workspace: {
    getConfiguration: () => ({
      get: (key, fallback) => (key === "command" ? `"${process.env.PYTHON || "python3"}" "${path.join(repo, "pdfmd.py")}"` : fallback),
    }),
    textDocuments: [],
    onDidSaveTextDocument: () => ({ dispose() {} }),
    workspaceFolders: undefined,
  },
  commands: { registerCommand: (name, fn) => { handlers[name] = fn; return { dispose() {} }; }, executeCommand: async () => {} },
  env: { openExternal: async (uri) => { opened.push(uri.fsPath); return true; } },
  Uri: { file: (fsPath) => ({ fsPath }) },
  ProgressLocation: { Window: 10 },
  StatusBarAlignment: { Left: 1 },
  Position: class { constructor(line, character) { this.line = line; this.character = character; } },
};

const load = Module._load;
Module._load = function (request, ...rest) { return request === "vscode" ? vscode : load.call(this, request, ...rest); };
const extension = require("../extension.js");
Module._load = load;

(async () => {
  assert.deepStrictEqual(extension.splitCommand('pdfmd'), ["pdfmd"]);
  assert.deepStrictEqual(extension.splitCommand('"/a b/pdfmd" -v'), ["/a b/pdfmd", "-v"]);
  assert.deepStrictEqual(extension.splitCommand("python3 /x/pdfmd.py"), ["python3", "/x/pdfmd.py"]);

  const subscriptions = [];
  extension.activate({ subscriptions });
  for (const name of ["build", "buildOpen", "buildAs", "watch", "extractTables", "expandTables", "ignoreHere", "history",
                      "historyDiff", "historyRestore", "restoreSource", "doctor"]) {
    assert.ok(handlers["pdfmd." + name], "pdfmd." + name + " is registered");
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
  for (const command of manifest.contributes.commands) assert.ok(handlers[command.command], command.command + " has a handler");

  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "pdfmd-vscode-"));
  const doc = path.join(folder, "note.md");
  fs.writeFileSync(doc, "---\ntitle: Note\n---\n\nHello.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n: Numbers\n");

  await handlers["pdfmd.buildOpen"]({ fsPath: doc });
  assert.ok(fs.existsSync(path.join(folder, "note.pdf")), "the PDF was built");
  assert.deepStrictEqual(opened, [path.join(folder, "note.pdf")]);

  quickPick = (items) => items[0];
  await handlers["pdfmd.extractTables"]({ fsPath: doc });
  assert.ok(fs.existsSync(path.join(folder, "tables")) && fs.readdirSync(path.join(folder, "tables")).some((n) => n.endsWith(".csv")), "the table became a CSV file");
  assert.ok(fs.readFileSync(doc, "utf8").includes(".csv"));
  await handlers["pdfmd.expandTables"]({ fsPath: doc });
  assert.ok(fs.readFileSync(doc, "utf8").includes("| a | b |"), "and back");

  await handlers["pdfmd.history"]({ fsPath: doc });
  await handlers["pdfmd.build"]({ fsPath: path.join(folder, "missing.md") });
  assert.ok(messages.some((text) => text.startsWith("ERROR")), "a failed build is reported");
  console.log("vscode smoke test: ok");
})().catch((error) => { console.error(error); process.exit(1); });

"""Web editor regressions, executed under node without opening a browser."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "lib" / "pdfmd_web"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "needs node")
class EditorHistory(unittest.TestCase):
    def test_each_document_keeps_its_own_codemirror_history(self):
        modules = WEB / "vendor" / "cm" / "node_modules"
        if not (modules / "@codemirror" / "state").is_dir():
            self.skipTest("needs the installed CodeMirror build dependencies")
        script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const path = require("path"), {createRequire} = require("module");
const web = process.argv[1], load = createRequire(path.join(web, "vendor/cm/package.json"));
const {EditorState} = load("@codemirror/state");
const {history, undo, redo} = load("@codemirror/commands");
// Real CodeMirror state/history; the DOM view is replaced with its state/dispatch contract.
class EditorView {
  constructor({state}) { this.state = state; this.dispatch = spec => {
    this.state = spec.state || this.state.update(spec).state;
  }; }
  setState(state) { this.state = state; }
  focus() {}
}
EditorView.lineWrapping = [];
EditorView.updateListener = {of: () => []};
const empty = () => [], context = {
  window: {}, EditorState, EditorView, history, undo, redo,
  lineNumbers: empty, foldGutter: empty, drawSelection: empty, highlightActiveLine: empty,
  markdown: empty, syntaxState: [], regions: [], colours: [], look: [], marks: [],
  keymap: {of: empty}, defaultKeymap: [], historyKeymap: [], searchKeymap: [], foldKeymap: [],
};
const source = fs.readFileSync(path.join(web, "vendor/cm/entry.js"), "utf8");
vm.runInNewContext(source.slice(source.indexOf("window.AppEditorCM =")), context);
const ed = context.window.AppEditorCM({}, "");
ed.setText("A", "a.md");
ed.replaceRange(1, 1, " edit");
ed.setText("B", "b.md");
ed.undo();
assert.equal(ed.getText(), "B", "Undo in B must never retrieve A");
ed.replaceRange(1, 1, " edit");
ed.setText("A edit", "a.md");
assert.equal(ed.getText(), "A edit");
ed.undo(); assert.equal(ed.getText(), "A");
ed.redo(); assert.equal(ed.getText(), "A edit");
ed.setText("B edit", "b.md");
ed.undo(); assert.equal(ed.getText(), "B");
ed.forgetDocument("b.md");
ed.setText("A edit", "a.md");
ed.setText("disk B", "b.md");
ed.undo(); assert.equal(ed.getText(), "disk B", "closed documents discard their history");
'''
        done = subprocess.run([NODE, "-e", script, str(WEB)], env={**os.environ},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


@unittest.skipUnless(NODE, "needs node")
class WebApp(unittest.TestCase):
    def run_js(self, script):
        harness = (ROOT / "tests" / "web_app_harness.js").read_text()
        done = subprocess.run([NODE, "-e", harness + "\n" + script, str(WEB)], env={**os.environ},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_tabs_select_and_discard_their_own_editor_state(self):
        self.run_js(r'''
(async () => {
  const switches = [], forgotten = [];
  let text = "";
  S.editor = {getText: () => text, selection: () => ({from: 0}),
    setText(t, key) { text = t; switches.push(key); }, setSelection() {}, focus() {},
    forgetDocument(key) { forgotten.push(key); }};
  S.project = {tree: [{name: "a.md"}, {name: "b.md"}]};
  context.api.readFile = async p => ({text: p});
  await openFile("a.md"); await openFile("b.md"); await openFile("a.md");
  assert.deepEqual(switches, ["a.md", "b.md", "a.md"]);
  closeTab("b.md"); assert.deepEqual(forgotten, ["b.md"]);
  closeTab("a.md"); assert.deepEqual(forgotten, ["b.md", "a.md"]);
  assert.equal(switches.at(-1), null, "the empty editor has fresh history");
})().catch(e => {console.error(e); process.exitCode = 1;});
''')

    def test_typing_during_save_keeps_the_unwritten_text_dirty(self):
        self.run_js(r'''
(async () => {
  let text = "submitted", finish;
  const writes = [];
  S.cur = "a.md"; S.tabs = [S.cur];
  const f = S.files[S.cur] = {text, saved: "old", original: "old"};
  S.editor = {getText: () => text};
  context.api.writeFile = (p, t) => { writes.push([p, t]); return new Promise(resolve => {finish = resolve;}); };
  const saving = save();
  text = f.text = "typed during save";
  finish({}); await saving;
  assert.equal(f.saved, "submitted");
  assert.equal(f.text, "typed during save");
  assert.equal(anyDirty(), true);
  assert.deepEqual(writes, [["a.md", "submitted"]]);
  const again = save(); finish({}); await again;
  assert.equal(f.saved, "typed during save");
  assert.equal(anyDirty(), false);
})().catch(e => {console.error(e); process.exitCode = 1;});
''')

    def test_the_native_quit_saves_every_changed_tab_and_says_what_stays_unsaved(self):
        # Colophon asks the page before the app quits (appDirty) and saves it all (appSaveAll): a refused save keeps the app open
        self.run_js(r'''
(async () => {
  let text = "a edited";
  const writes = [];
  S.tabs = ["a.md", "b.md", "c.md", "pic.png", "d.md"]; S.cur = "a.md";
  S.files["a.md"] = {text: "a", saved: "a"};
  S.files["b.md"] = {text: "b edited", saved: "b"};
  S.files["c.md"] = {text: "c edited", saved: "c"};
  S.files["pic.png"] = {view: "image", text: "", saved: ""};
  S.files["d.md"] = {text: "d", saved: "d"};
  S.editor = {getText: () => text};
  context.api.writeFile = async (p, t) => {
    writes.push([p, t]);
    if (p === "c.md") { const e = new Error("changed on disk"); e.status = 409; throw e; }
    return {};
  };
  assert.equal(typeof window.appDirty, "function");
  assert.equal(window.appDirty(), true, "the current tab counts by the editor's text");
  const first = await window.appSaveAll();
  assert.deepEqual(writes, [["a.md", "a edited"], ["b.md", "b edited"], ["c.md", "c edited"]], "only the tabs with changes are written");
  assert.equal(S.files["a.md"].saved, "a edited");
  assert.equal(S.files["b.md"].saved, "b edited");
  assert.equal(S.files["c.md"].stale, true);
  assert.equal(first.dirty, true, "a refused save leaves something unsaved");
  context.api.writeFile = async () => ({});
  assert.equal((await window.appSaveAll()).dirty, false);
  assert.equal(window.appDirty(), false);
})().catch(e => {console.error(e); process.exitCode = 1;});
''')


@unittest.skipUnless(NODE and shutil.which("pandoc"), "needs node and Pandoc")
class LivePreview(unittest.TestCase):
    def test_reverting_to_original_renders_that_exact_source(self):
        script = r'''
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const {execFileSync} = require("child_process");
const [web, python, launcher, folder] = process.argv.slice(1);
let renders = 0;
const context = {
  FIXTURES: {settingsSchema: []}, location: {protocol: "http:", hash: ""},
  fetch: async (url, opts = {}) => {
    const args = [launcher, "--api", opts.method || "GET", url];
    if (opts.body) args.push(opts.body);
    if (url === "/api/render") renders++;
    const data = JSON.parse(execFileSync(python, args, {cwd: folder, env: process.env,
      stdio: ["ignore", "pipe", "pipe"], encoding: "utf8"}));
    return {ok: true, json: async () => data};
  },
};
context.window = context;
vm.runInNewContext(fs.readFileSync(path.join(web, "js/api.js"), "utf8"), context);
(async () => {
  const api = context.api;
  const original = await api.renderLive("doc.md", "Original", true);
  const edited = await api.renderLive("doc.md", "Edited", false);
  assert.notEqual(original, edited);
  const reverted = await api.renderLive("doc.md", "Original", true);
  assert.equal(reverted, original, "Undo must show the original preview");
  assert.equal(renders, 3);
  assert.equal(await api.renderLive("doc.md", "Original", false), original);
  assert.equal(renders, 3, "the exact source can be reused even when unchanged is false");
  await api.renderLive("doc.md", "Original\n", false);
  assert.equal(renders, 4, "cache keys include trailing whitespace");
})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        with tempfile.TemporaryDirectory(prefix="pdfmd-web-preview-") as directory:
            root = Path(directory)
            (root / "doc.md").write_text("Original")
            env = {**os.environ, "XDG_CONFIG_HOME": str(root / "config"),
                   "XDG_CACHE_HOME": str(root / "cache"), "XDG_DATA_HOME": str(root / "data"),
                   "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([NODE, "-e", script, str(WEB), sys.executable,
                                   str(ROOT / "scripts" / "pdfmd"), str(root)], env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

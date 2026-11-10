"""Web editor regressions, executed under node without opening a browser."""
from __future__ import annotations

import os
import shutil
import subprocess
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

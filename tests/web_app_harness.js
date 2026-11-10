const fs = require("fs"), vm = require("vm"), assert = require("assert"), path = require("path");
const nodes = new Map();
const element = () => ({textContent: "", hidden: false, append() {}, addEventListener() {}, classList: {add() {}, remove() {}}, style: {}});
const document = {addEventListener() {}, querySelector(s) { if (!nodes.has(s)) nodes.set(s, element()); return nodes.get(s); }, querySelectorAll: () => [], createElement: element};
const window = {addEventListener() {}};
const context = {window, document, location: {hash: "", search: ""}, navigator: {platform: "test"}, api: {}, console, clearTimeout() {}, setTimeout() {}, confirm: () => true};
let source = fs.readFileSync(path.join(process.argv[1], "js/app.js"), "utf8");
source = source.replace("  start();", `
  renderTabs = renderSide = refreshAll = onSelection = () => {};
  showViewer = async () => {};
  window.test = {S, openFile, closeTab, save, mountEditor, anyDirty};
`);
vm.runInNewContext(source, context);
const {S, openFile, closeTab, save, mountEditor, anyDirty} = window.test;

// The page. It holds no logic of pdfmd's: it asks api.js, draws, and inserts text. Everything a person can do here is also a pdfmd command
// (the Export dialog shows the command), so a script or an agent can do the same without this page.
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); kids.flat().forEach(k => e.append(k)); return e; };
  const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";
  const PLATFORM = "browser";    // the platform this page runs as: rows whose `platforms` lack it are hidden (the Mac app would say "macos")

  const S = { project: null, files: {}, tabs: [], cur: null, panel: "files", layout: "split", view: "html", settings: {}, schema: [], exports: [],
              engine: "", editor: null, renderTimer: 0, renderedFor: "", building: false, historyLane: "edits", sideTab: "General", searchQ: "" };

  // ---------- small helpers ----------------------------------------------------------------------------------------------------
  function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), ms); }
  const setting = k => S.settings[k];
  const flag = k => setting(k) === "1";
  const num = k => +setting(k);
  const file = () => S.files[S.cur];
  const isDirty = f => f.text !== f.saved;
  const lineStarts = text => { const a = [0]; for (let i = 0; i < text.length; i++) if (text[i] === "\n") a.push(i + 1); return a; };

  // ---------- menus: one component for every dropdown, nested ones included ("a dropdown in a dropdown") -------------------------
  let pops = [];
  function closePops(from = 0) { pops.splice(from).forEach(p => p.remove()); }
  function showMenu(items, x, y, level = 0) {
    closePops(level);
    const box = el("div", { className: "popover" });
    for (const it of items) {
      if (it === "-") { box.append(el("hr")); continue; }
      if (it.head) { box.append(el("div", { className: "head" }, it.head)); continue; }
      const row = el("div", { className: "mi" + (it.sub ? " sub" : "") + (it.off ? " off" : "") }, el("span", {}, (it.check ? "✓ " : "") + it.label), it.keys ? el("span", { className: "keys" }, it.keys) : "");
      row.addEventListener("mouseenter", () => { closePops(level + 1); if (it.sub) { const r = row.getBoundingClientRect(); showMenu(it.sub, r.right - 2, r.top - 4, level + 1); } });
      if (!it.sub) row.addEventListener("click", e => { e.stopPropagation(); closePops(); it.run && it.run(); });
      box.append(row);
    }
    document.body.append(box); pops[level] = box;
    const r = box.getBoundingClientRect();
    box.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 6)) + "px";
    box.style.top = Math.max(4, Math.min(y, innerHeight - r.height - 6)) + "px";
    return box;
  }
  function showAt(anchor, items) { const r = anchor.getBoundingClientRect(); return showMenu(items, r.left, r.bottom + 2); }
  document.addEventListener("mousedown", e => { if (pops.length && !e.target.closest(".popover")) closePops(); });

  // ---------- the editor, switchable ------------------------------------------------------------------------------------------
  function mountEditor(initial) {
    const kind = setting("editorKind");
    S.editor = createEditor(kind, $("#editor"), initial || "");
    S.editor.onChange(onEdit);
    S.editor.onSelection(onSelection);
    if (S.syntaxes) S.editor.setSyntax(S.syntaxes, "markdown");
    $("#stEditor").textContent = S.editor.kind === "codemirror" ? "editor: CodeMirror 6" : "editor: plain text box";
  }
  function switchEditorKind(kind) {
    S.settings.editorKind = kind; api.setSetting("editorKind", kind);
    const f = file(); mountEditor(f ? f.text : ""); onSelection(S.editor.selection()); toast("Editor: " + (kind === "codemirror" ? "CodeMirror 6" : "plain text box") + " (same contract)");
  }

  // The colours of the roles in the syntax table (syntax/syntaxes.json): one CSS custom property per role, a light and a dark value, and the class
  // the editor puts on the text that has the role. The Mac app colours the same roles from its theme.
  function roleColours(table) {
    if (!table) return;
    const roles = table.roles, one = which => roles.map(r => `--syn-${r.key}: ${r[which]};`).join(" ");
    const css = `:root { ${one("light")} } @media (prefers-color-scheme: dark) { :root { ${one("dark")} } } ` + roles.map(r => `.syn-${r.key} { color: var(--syn-${r.key}); }`).join(" ") + " .syn-heading { font-weight: 600; } .syn-emphasis { font-weight: 700; }";
    document.head.append(el("style", { id: "syntaxColours" }, css));
  }

  // ---------- tabs and files --------------------------------------------------------------------------------------------------
  // What a file is, by the project's own listing (the core says it by extension), else by its name.
  const kindOf = path => (S.project.tree.find(n => n.name === path) || {}).kind || (/\.(png|jpe?g|gif|svg|webp)$/i.test(path) ? "image" : /\.pdf$/i.test(path) ? "pdf" : "text");
  // A picture or a PDF is shown, not edited: the viewer takes the editor's place (the editor keeps the text of the tab it was on).
  async function showViewer(path, kind) {
    const v = $("#viewer"), editor = $("#editor"), bar = $("#toolbar");
    v.hidden = !path; editor.hidden = !!path; bar.hidden = !!path;
    if (!path) return;
    v.textContent = "";
    const url = await api.rawUrl(path);
    if (!url) v.append(el("div", { className: "dim" }, "This file is shown only in the app with a project folder (the demo has no " + (kind === "pdf" ? "PDF" : "picture") + ")."));
    else v.append(kind === "image" ? el("img", { src: url, alt: path }) : el("iframe", { src: url, title: path }));
  }
  async function openFile(path, line) {
    const kind = kindOf(path);
    if (kind === "image" || kind === "pdf") {
      if (S.cur && S.files[S.cur] && !S.files[S.cur].view) { S.files[S.cur].text = S.editor.getText(); S.files[S.cur].sel = S.editor.selection().from; }
      S.files[path] = S.files[path] || { view: kind, text: "", saved: "", sel: 0, original: "" };
      if (!S.tabs.includes(path)) S.tabs.push(path);
      S.cur = path; await showViewer(path, kind); renderTabs(); renderSide(); refreshAll();
      return;
    }
    await showViewer(null);
    if (!S.files[path]) { const r = await api.readFile(path); S.files[path] = { text: r.text, saved: r.text, sel: 0, original: r.text }; }
    if (S.cur && S.files[S.cur] && !S.files[S.cur].view) { S.files[S.cur].text = S.editor.getText(); S.files[S.cur].sel = S.editor.selection().from; }
    if (!S.tabs.includes(path)) S.tabs.push(path);
    S.cur = path;
    S.editor.setText(S.files[path].text);
    S.editor.setSelection(S.files[path].sel || 0);
    if (line) S.editor.scrollTo(line);
    renderTabs(); renderSide(); refreshAll(); S.editor.focus();
  }
  async function newFile() {      // a new empty file as a new tab of the project (the native command T)
    let n = 1, name = "untitled.md"; while (S.files[name] || S.project.tree.some(t => t.name === name)) name = "untitled-" + (++n) + ".md";
    await api.createFile(name); await openFile(name);
  }
  function closeTab(path) {
    const f = S.files[path];
    if (f && isDirty(f) && !confirm(path + " has changes that are not saved. Close it anyway?")) return;
    if (f) f.text = f.saved;
    if (f && f.stale) delete S.files[path];       // a save was refused because the file changed on disk: the next open reads it again
    S.tabs = S.tabs.filter(p => p !== path);
    if (S.cur === path) { S.cur = null; if (S.tabs.length) openFile(S.tabs[S.tabs.length - 1]); else { S.editor.setText(""); renderTabs(); } }
    else renderTabs();
  }
  function renderTabs() {
    const box = $("#tabs"); box.textContent = "";
    for (const p of S.tabs) {
      const f = S.files[p], on = p === S.cur;
      const tab = el("div", { className: "tab" + (on ? " on" : ""), title: p }, p, !f.view && (on ? S.editor.getText() !== f.saved : isDirty(f)) ? el("span", { className: "dot" }, "●") : "", el("span", { className: "x", textContent: "✕", title: "Close" }));
      tab.addEventListener("click", e => { if (e.target.classList.contains("x")) closeTab(p); else if (!on) openFile(p); });
      box.append(tab);
    }
    reportState();
  }
  async function save() {
    const f = file(); if (!f || f.view) return;
    f.text = S.editor.getText();
    try { await api.writeFile(S.cur, f.text); } catch (e) { if (e.status === 409) f.stale = true; toast(e.status === 409 ? S.cur + " changed on disk since it was opened: nothing was saved. Copy your text, close this tab, and open the file again to load the disk version" : "Not saved: " + e.message); return; }
    f.saved = f.text; renderTabs(); toast("Saved " + S.cur);
    if (setting("renderMode") === "watch") renderLive(true);
  }

  // ---------- the live view: render modes, stale banner, the source <-> preview mirror ------------------------------------------
  function effectiveMode() {
    const m = $("#renderMode").value;
    if (m !== "auto") return m;
    return S.editor.lineCount() <= num("renderAutoMaxLines") ? "instant" : "watch";
  }
  function onEdit(text) {
    const f = file(); if (!f) return; f.text = text; renderTabs();
    $("#stWords").textContent = words(text) + " words";
    const mode = effectiveMode();
    if (mode === "instant") { clearTimeout(S.renderTimer); S.renderTimer = setTimeout(() => renderLive(), num("renderDelayMs")); }
    else banner(mode === "watch" ? "Live view follows the saved text (render: watch). Save to update it." : "Live view is older than the text (render: manual). " + MOD + "R renders it.");
  }
  const words = t => (t.trim().match(/\S+/g) || []).length;
  function banner(msg) { const b = $("#liveBanner"); b.hidden = !msg; b.textContent = msg || ""; }
  // A CSV file's preview is its table (the same cells a document's `.csv` block would show); another file that is not Markdown has none.
  function csvRows(text) {
    const delim = [",", ";", "\t", "|"].map(d => [d, (text.split("\n")[0] || "").split(d).length]).sort((a, b) => b[1] - a[1])[0][0];
    const rows = []; let row = [], cell = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
      else if (c === '"') q = true;
      else if (c === delim) { row.push(cell); cell = ""; }
      else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cell); cell = ""; if (!(row.length === 1 && row[0] === "")) rows.push(row); row = []; }
      else cell += c;
    }
    row.push(cell); if (!(row.length === 1 && row[0] === "")) rows.push(row);
    return rows;
  }
  function renderOther(text) {
    const live = $("#live"); banner("");
    if (/\.csv$/i.test(S.cur)) {
      const rows = csvRows(text), table = el("table", { className: "csvview" });
      rows.forEach((r, i) => table.append(el("tr", {}, ...r.map(c => el(i === 0 ? "th" : "td", {}, c)))));
      live.textContent = ""; live.append(el("p", { className: "dim small" }, rows.length + " rows"), table);
    } else { live.textContent = ""; live.append(el("p", { className: "dim" }, "No preview for this kind of file.")); }
    S.renderedFor = S.cur; S.lastHtml = live.innerHTML;
  }
  async function renderLive(fromSave) {
    const f = file(); if (!f || f.view) return;
    const text = S.editor.getText();
    if (kindOf(S.cur) !== "markdown") { renderOther(text); return; }
    const unchanged = text === f.original;
    let html;
    try { html = await api.renderLive(S.cur, text, unchanged); } catch (e) { banner("The live view could not render: " + e.message + " (it shows the last render)"); return; }
    const live = $("#live"), top = $("#liveView").scrollTop;
    live.innerHTML = html; $("#liveView").scrollTop = top;
    const st = api.lastRender; banner(unchanged || st.live ? "" : `${st.kept} blocks are pandoc's own, ${st.rendered} edited block${st.rendered === 1 ? "" : "s"} from the stand-in renderer (the core renders those through pandoc too; math and citations show as typed here)`);
    S.renderedFor = S.cur; S.lastHtml = html;
    if (S.channel) S.channel.postMessage({ html });
    onSelection(S.editor.selection());
  }
  // The lines a block covers. Pandoc's end position of a list runs on to the start of the next block (past the blank line, a heading's line
  // included), and `li` has no position at all: so the end is cut at the next sibling's first line and the blank lines at its end are dropped.
  function blockLines(node) {
    const m = /@(\d+):\d+-(\d+):(\d+)$/.exec(node.getAttribute("data-pos") || ""); if (!m) return null;
    const a = +m[1], c = +m[2], d = +m[3];
    let end = d === 1 && c > a ? c - 1 : c;
    const next = node.nextElementSibling && /@(\d+):/.exec(node.nextElementSibling.getAttribute("data-pos") || "");
    if (next) end = Math.min(end, +next[1] - 1);
    const lines = S.editor.getText().split("\n");
    while (end > a && !(lines[end - 1] || "").trim()) end--;
    return [a, end];
  }
  function onSelection(sel) {
    $("#stPos").textContent = sel.line + ":" + sel.col;
    $$("#live .mirror").forEach(n => n.classList.remove("mirror"));
    if (!flag("mirrorSource") || sel.from === sel.to) return;
    const starts = lineStarts(S.editor.getText());
    const lineOf = off => { let i = 0; while (i + 1 < starts.length && starts[i + 1] <= off) i++; return i + 1; };
    const a = lineOf(sel.from), b = lineOf(Math.max(sel.from, sel.to - 1));
    const hit = $$("#live [data-pos]").filter(n => { const r = blockLines(n); return r && r[0] <= b && r[1] >= a; });
    const leaves = hit.filter(n => !hit.some(o => o !== n && n.contains(o)));
    leaves.forEach(n => n.classList.add("mirror"));
    if (leaves[0]) { const v = $("#liveView"), r = leaves[0].getBoundingClientRect(), vr = v.getBoundingClientRect(); if (r.top < vr.top + 30 || r.bottom > vr.bottom - 30) v.scrollTop += r.top - vr.top - vr.height / 3; }
  }
  // the other way, only as a mark: the block under the pointer shows its lines in the source (decorate is part of the contract)
  document.addEventListener("mouseover", e => {
    if (!flag("mirrorSource") || !S.editor) return;
    const n = e.target.closest && e.target.closest("#live [data-pos]");
    if (!n) { S.editor.decorate([]); return; }
    const r = blockLines(n); if (!r) return;
    const starts = lineStarts(S.editor.getText()), end = i => (i < starts.length ? starts[i] - 1 : S.editor.getText().length);
    S.editor.decorate([{ from: starts[r[0] - 1], to: end(r[1]) }]);
  });

  // ---------- toolbar and insert templates --------------------------------------------------------------------------------------
  // A template is plain text; "¦" marks where the cursor goes (the same list would live in pdfmd, so a plain editor offers it too).
  const T = {
    bold: ["**¦**", "Bold", MOD + "B"], italic: ["*¦*", "Italic", MOD + "I"], code: ["`¦`", "Inline code", MOD + "E"],
    link: ["[¦](https://)", "Link", MOD + "K"], comment: ["<!-- ¦ -->", "Comment", MOD + "/"],
    fence: ["```\n¦\n```", "Code block", MOD + "⌥C"], div: ["::: ¦\n\n:::", "Div (:::)", MOD + "⌥D"],
    calc: ["::: calc\n¦V = 20.60 - 0.00 = {ans:2dp} mL.\n:::", "Calculation block", MOD + "⌥K"],
    image: ["![¦](figure.png)", "Image", MOD + "⌥I"], table: ["| ¦A | B |\n|---|---|\n| 1 | 2 |", "Table", MOD + "⌥T"],
    math: ["$¦$", "Inline math", MOD + "M"], mathblock: ["$$\n¦\n$$", "Display math", MOD + "⌥M"], footnote: ["[^¦]", "Footnote", MOD + "⌥F"],
    cite: ["[@¦]", "Citation", MOD + "⌥R"], list: ["- ¦", "Bullet list", ""], pagebreak: ["<!-- pagebreak -->\n¦", "Page break", ""],
  };
  // A template TOGGLES: pressing it again where it was just put (or around what it wrapped) takes it out again.
  //  - a WRAPPER (bold, italic, code, link, comment, math, footnote, citation, code block, display math) wraps the selection; with the
  //    selection already inside its marks, or the cursor between them, it unwraps;
  //  - any other (div, calc, image, table, list, page break) is put in once; the same key pressed with the cursor in what it inserted removes it.
  const WRAP = new Set(["bold", "italic", "code", "link", "comment", "math", "mathblock", "fence", "footnote", "cite"]);
  function insert(key) {
    const [tpl] = T[key], at = tpl.indexOf("\u00A6"), text = tpl.replace("\u00A6", "");
    const ed = S.editor, all = ed.getText(), sel = ed.selection();
    if (WRAP.has(key) && at >= 0) {
      const pre = tpl.slice(0, at), post = tpl.slice(at + 1), chosen = all.slice(sel.from, sel.to);
      let around = all.slice(sel.from - pre.length, sel.from) === pre && all.startsWith(post, sel.to);
      if (key === "bold" || key === "italic") {                          // stars: **x** is bold, *x* italic, ***x*** both: judge by the run of stars around the selection
        let l = 0, r = 0; while (all[sel.from - 1 - l] === "*") l++; while (all[sel.to + r] === "*") r++;
        const run = Math.min(l, r); around = key === "bold" ? run >= 2 : run % 2 === 1;
      }
      if (around) {                                                      // the marks around the selection: take them off
        ed.replaceRange(sel.from - pre.length, sel.to + post.length, chosen, sel.from - pre.length, sel.from - pre.length + chosen.length); S.last = null; return;
      }
      if (chosen.length >= pre.length + post.length && chosen.startsWith(pre) && chosen.endsWith(post)) {            // the selection includes the marks
        const inner = chosen.slice(pre.length, chosen.length - post.length); ed.replaceRange(sel.from, sel.to, inner, sel.from, sel.from + inner.length); S.last = null; return;
      }
      ed.replaceRange(sel.from, sel.to, pre + chosen + post, sel.from + pre.length, sel.from + pre.length + chosen.length); S.last = null; return;
    }
    const last = S.last;                                                                                                // the same template again, in what it inserted
    if (last && last.key === key && last.file === S.cur && all.slice(last.from, last.from + last.text.length) === last.text && sel.from >= last.from && sel.to <= last.from + last.text.length) {
      ed.replaceRange(last.from, last.from + last.text.length, "", last.from, last.from); S.last = null; return;
    }
    ed.replaceRange(sel.from, sel.to, text, sel.from + (at >= 0 ? at : text.length));
    S.last = { key, file: S.cur, from: sel.from, text };
  }
  function heading(level) {
    const sel = S.editor.selection(), text = S.editor.getText(), start = text.lastIndexOf("\n", sel.from - 1) + 1, end = text.indexOf("\n", sel.from) < 0 ? text.length : text.indexOf("\n", sel.from);
    const line = text.slice(start, end).replace(/^#{1,6}\s+/, "");
    S.editor.setSelection(start, end); S.editor.replaceSelection(level ? "#".repeat(level) + " " + line : line, false);
  }
  // [character, LaTeX]: the document stays ASCII-only by default (setting symbolInsert = ascii: `$\\alpha$`, or `\\alpha` when the cursor is already in math)
  const SYMBOLS = {
    Greek: [["\u03B1","\\alpha"],["\u03B2","\\beta"],["\u03B3","\\gamma"],["\u03B4","\\delta"],["\u03B5","\\varepsilon"],["\u03B6","\\zeta"],["\u03B7","\\eta"],["\u03B8","\\theta"],["\u03BB","\\lambda"],["\u03BC","\\mu"],["\u03BD","\\nu"],["\u03BE","\\xi"],["\u03C0","\\pi"],["\u03C1","\\rho"],["\u03C3","\\sigma"],["\u03C4","\\tau"],["\u03C6","\\varphi"],["\u03C7","\\chi"],["\u03C8","\\psi"],["\u03C9","\\omega"],["\u0394","\\Delta"],["\u0398","\\Theta"],["\u039B","\\Lambda"],["\u03A0","\\Pi"],["\u03A3","\\Sigma"],["\u03A6","\\Phi"],["\u03A8","\\Psi"],["\u03A9","\\Omega"]],
    Math: [["\u00B1","\\pm"],["\u00D7","\\times"],["\u00F7","\\div"],["\u2212","-"],["\u2260","\\neq"],["\u2248","\\approx"],["\u2261","\\equiv"],["\u2264","\\leq"],["\u2265","\\geq"],["\u221E","\\infty"],["\u221A","\\sqrt{}"],["\u2211","\\sum"],["\u220F","\\prod"],["\u222B","\\int"],["\u2202","\\partial"],["\u2207","\\nabla"],["\u2208","\\in"],["\u2282","\\subset"],["\u222A","\\cup"],["\u2229","\\cap"],["\u2200","\\forall"],["\u2203","\\exists"],["\u2192","\\to"],["\u21D2","\\Rightarrow"],["\u21C4","\\rightleftarrows"]],
    Chemistry: [["\u00B0","^\\circ"],["\u2022","\\cdot"],["\u2032","^\\prime"],["\u2033","^{\\prime\\prime}"],["\u212B","\\text{\\AA}"],["\u21CC","\\rightleftharpoons"],["\u2191","\\uparrow"],["\u2193","\\downarrow"],["\u207A","^+"],["\u207B","^-"],["\u2070","^0"],["\u00B9","^1"],["\u00B2","^2"],["\u00B3","^3"],["\u2074","^4"],["\u2080","_0"],["\u2081","_1"],["\u2082","_2"],["\u2083","_3"],["\u2084","_4"],["\u2085","_5"],["\u2086","_6"],["\u2087","_7"]],
  };
  // is the cursor inside $...$ or $$...$$ of its paragraph?
  function inMath(text, at) {
    const para = text.slice(text.lastIndexOf("\n\n", at - 1) + 1, at), display = (para.match(/\$\$/g) || []).length;
    return display % 2 === 1 || (para.replace(/\$\$/g, "").match(/(?<!\\)\$/g) || []).length % 2 === 1;
  }
  function putSymbol([ch, tex]) {
    if (setting("symbolInsert") === "unicode") { S.editor.replaceSelection(ch, false); return; }
    const text = S.editor.getText(), sel = S.editor.selection(), next = text[sel.to] || "";
    const body = tex + (/[A-Za-z]$/.test(tex) && /[A-Za-z0-9]/.test(next) ? " " : "");
    const put = inMath(text, sel.from) ? body : "$" + tex + "$";
    S.editor.replaceRange(sel.from, sel.to, put, sel.from + put.length - (tex.endsWith("{}") && !put.endsWith("$") ? 1 : tex.endsWith("{}") ? 2 : 0));
  }
  function symbolsPicker(anchor) {
    closePops();
    const box = el("div", { className: "popover" });
    const mode = el("div", { className: "seg", style: "margin:2px 2px 4px" });
    const paint = () => { mode.textContent = ""; for (const [v, label, tip] of [["ascii", "ASCII (LaTeX)", "inserts $\\alpha$: the document stays plain ASCII"], ["unicode", "Unicode", "inserts the character itself"]])
      mode.append(el("button", { className: setting("symbolInsert") === v ? "on" : "", textContent: label, title: tip, onclick: async () => { S.settings.symbolInsert = v; await api.setSetting("symbolInsert", v); paint(); } })); };
    paint(); box.append(mode);
    for (const [name, pairs] of Object.entries(SYMBOLS)) {
      box.append(el("div", { className: "head" }, name));
      const grid = el("div", { className: "symgrid" });
      for (const pair of pairs) grid.append(el("button", { textContent: pair[0], title: pair[1] + "   U+" + pair[0].codePointAt(0).toString(16).toUpperCase(), onclick: () => { putSymbol(pair); closePops(); } }));
      box.append(grid);
    }
    document.body.append(box); pops[0] = box;
    const r = anchor.getBoundingClientRect(); box.style.left = r.left + "px"; box.style.top = r.bottom + 2 + "px";
  }
  function insertMenu(anchor) {
    showAt(anchor, ["comment", "code", "fence", "div", "calc", "-", "image", "link", "table", "-", "math", "mathblock", "footnote", "cite", "-", "pagebreak"]
      .map(k => (k === "-" ? k : { label: T[k][1], keys: T[k][2], run: () => insert(k) })));
  }
  const keyMap = () => ({ b: "bold", i: "italic", e: "code", k: "link", "/": "comment", m: "math" });
  const altMap = { c: "fence", d: "div", k: "calc", i: "image", t: "table", m: "mathblock", f: "footnote", r: "cite" };

  // ---------- export, build -----------------------------------------------------------------------------------------------------
  function exportTree() {
    const root = []; const by = new Map([["", root]]);
    for (const f of S.exports) {
      let key = "", list = root;
      for (const part of f.menu) { key += "/" + part; if (!by.has(key)) { const sub = []; list.push({ label: part, sub }); by.set(key, sub); } list = by.get(key); }
      list.push({ label: f.title, run: () => exportDialog(f) });
    }
    // the same order as the Mac menu: Markdown, PDF, Word, HTML, Cropped, Others (the table lists them in that order already)
    return root;
  }
  function outName(f) { const base = S.cur.replace(/\.[^.]+$/, ""); return f.id === "md" ? base + ".assembled.md" : base + "." + f.extension; }
  function exportDialog(f) {
    const cmd = `pdfmd ${S.cur} ${f.pdfmd.join(" ")} -o ${outName(f)}`, d = $("#dialog"); d.textContent = "";
    d.append(el("h2", {}, "Export as " + (f.menu.length ? f.menu[0] + " › " : "") + f.title), el("div", { className: "dim" }, "The page runs this pdfmd command; you can run it yourself:"), el("pre", { className: "cmd" }, cmd),
      el("div", { className: "buttons" }, el("button", { className: "btn", textContent: "Copy command", onclick: () => navigator.clipboard && navigator.clipboard.writeText(cmd).then(() => toast("Copied")) }),
        el("button", { className: "btn", textContent: "Cancel", onclick: () => d.close() }),
        el("button", { className: "btn primary", textContent: "Export", onclick: () => { d.close(); toast("Exported " + outName(f) + " (prototype: nothing is written)"); } })));
    d.showModal();
  }
  async function runBuild() {
    if (S.building) return; S.building = true; const f = file(); if (f && f.text !== f.saved) await save();
    setView("log"); const log = $("#log"); log.textContent = ""; $("#buildBtn").textContent = "Building…"; $("#stBuild").textContent = "building…";
    const r = await api.build({ file: S.project.main, engine: S.engine }, line => { log.append(el("div", { className: /^OK/.test(line) ? "ok" : "" }, line)); log.scrollTop = log.scrollHeight; });
    S.building = false; $("#buildBtn").textContent = "Build";
    if (!r.ok) { $("#stBuild").textContent = "no build here yet"; return; }
    $("#stBuild").textContent = "built " + r.output + " in " + r.seconds.toFixed(1) + " s";
    $("#pdfFrame").src = api.pdfUrl() + "#toolbar=1&view=FitH"; setView("pdf");
  }
  function buildMenu() {
    const engines = S.exports.filter(f => /^pdf(:|$)/.test(f.id) && !/-cropped/.test(f.id));
    const quick = [["", "Auto"], ["typst", "Typst"], ["lualatex", "LuaLaTeX"], ["xelatex", "XeLaTeX"], ["weasyprint", "WeasyPrint"]];
    const known = engines.filter(f => quick.some(q => q[0] && f.id === "pdf:" + q[0])).length;
    showAt($("#buildMore"), [{ head: "Engine" }, ...quick.map(([id, label]) => ({ label, check: S.engine === id, run: () => { S.engine = id; toast("Build engine: " + label); } })),
      { label: "All engines (" + (engines.length - 1) + ")", sub: engines.filter(f => f.id !== "pdf").map(f => ({ label: f.menu.slice(1).concat(f.title).join(" › "), check: S.engine === f.id.replace("pdf:", ""), run: () => { S.engine = f.id.replace("pdf:", ""); toast("Build engine: " + f.title); } })) },
      "-", { label: "Stop on first error", check: true, run: () => toast("Stop on first error (sample)") }, { label: "Clear cache", run: () => toast("pdfmd cache cleared (prototype)") },
      "-", { head: "Main file" }, { label: S.project.main + "  (pdfmd's pick: " + S.project.mainWhy + ")", run: () => {} }]);
    void known;
  }

  // ---------- side panels -------------------------------------------------------------------------------------------------------
  function setPanel(name) { S.panel = name; $$("#rail button[data-panel]").forEach(b => b.classList.toggle("on", b.dataset.panel === name)); renderSide(); }
  const searchable = n => !["bib", "pdf", "image", "other"].includes(n.kind);      // the files whose text the search reads
  async function renderSide() {
    const side = $("#side"); side.textContent = "";
    const panel = el("div", { className: "panel" }); side.append(panel);
    if (S.panel === "files") {
      panel.append(el("h3", {}, "Files"));
      fileTree(panel);
      const outline = S.cur ? await api.outline(S.cur) : [];
      const live = S.cur ? headings(file().text) : outline;
      panel.append(el("h3", {}, "Outline"));
      if (!live.length) panel.append(el("div", { className: "row dim" }, "no headings"));
      for (const h of live) panel.append(row(h.title, "§", false, () => S.editor.scrollTo(h.line), "", (h.level - 1) * 12));
    } else if (S.panel === "search") {
      const q = el("input", { type: "search", placeholder: "Search all files", value: S.searchQ }); panel.append(q, el("div", { id: "hits" }));
      const go = async () => { S.searchQ = q.value; const texts = Object.fromEntries(S.project.tree.filter(n => searchable(n)).map(n => [n.name, (S.files[n.name] || { text: null }).text ?? null]));
        for (const n of S.project.tree) if (searchable(n) && texts[n.name] == null) texts[n.name] = (await api.readFile(n.name).catch(() => ({ text: "" }))).text;
        const hits = await api.search(q.value, texts), box = $("#hits"); box.textContent = "";
        box.append(el("div", { className: "dim small", style: "padding:0 12px 6px" }, q.value ? hits.length + " matches" : ""));
        for (const h of hits.slice(0, 200)) { const d = el("div", { className: "hit" }, el("div", { className: "where" }, h.file + ":" + h.line)); d.append(h.text.slice(0, h.at), el("mark", {}, h.text.slice(h.at, h.at + h.len)), h.text.slice(h.at + h.len)); d.onclick = () => openFile(h.file, h.line); box.append(d); } };
      q.addEventListener("input", go); q.focus(); go();
    } else if (S.panel === "checks") {
      const c = await api.checks(); panel.append(el("h3", {}, "Checks"), el("div", { className: "dim small", style: "padding:0 12px 6px" }, c.note));
      for (const it of c.items) panel.append(el("div", { className: "item", onclick: () => openFile(it.file, it.line) }, el("div", { className: "t" }, el("span", { className: "lvl " + it.level }, it.level.toUpperCase()), it.file + ":" + it.line), el("div", { className: "s" }, it.message)));
    } else if (S.panel === "history") {
      const h = await api.history(); panel.append(el("h3", {}, "History"), el("div", { className: "dim small", style: "padding:0 12px 6px" }, h.note));
      const lanes = el("div", { className: "lanes" }, el("div", { className: "seg" }, ...["edits", "builds"].map(l => el("button", { className: S.historyLane === l ? "on" : "", textContent: l === "edits" ? "Edits (git)" : "Builds (.hst)", onclick: () => { S.historyLane = l; renderSide(); } }))));
      panel.append(lanes);
      if (S.historyLane === "edits") for (const e of h.edits) panel.append(el("div", { className: "item", onclick: () => diffDialog(e, h) }, el("div", { className: "t" }, e.title), el("div", { className: "s" }, `${e.id} · ${e.when.slice(0, 16).replace("T", " ")} · ${e.files.join(", ")} · +${e.plus} −${e.minus}`)));
      else for (const b of h.builds) panel.append(el("div", { className: "item", onclick: () => { setView("log"); toast("Build record " + b.id + (b.ok ? "" : ": " + b.why)); } }, el("div", { className: "t" }, el("span", { className: b.ok ? "ok" : "bad" }, b.ok ? "✓ " : "✗ "), b.title), el("div", { className: "s" }, `${b.id} · ${b.when.slice(0, 16).replace("T", " ")} · ${b.seconds} s` + (b.why ? " · " + b.why : ""))));
    } else if (S.panel === "settings") {
      const tabs = [...new Set(S.schema.filter(s => s.platforms.includes(PLATFORM)).map(s => s.tab))];
      if (!tabs.includes(S.sideTab)) S.sideTab = tabs[0];
      panel.append(el("div", { className: "stabs" }, ...tabs.map(t => el("button", { className: t === S.sideTab ? "on" : "", textContent: t, onclick: () => { S.sideTab = t; renderSide(); } }))));
      const hidden = S.schema.filter(s => s.tab === S.sideTab && !s.platforms.includes(PLATFORM)).length;
      for (const s of S.schema.filter(s => s.tab === S.sideTab && s.platforms.includes(PLATFORM))) panel.append(settingRow(s));
      if (hidden) panel.append(el("div", { className: "dim small", style: "padding:10px 12px" }, hidden + " setting(s) of this tab only mean something in the Mac app and are not shown here (their stored values are kept)."));
    }
  }
  // The files as the folders hold them: folders first, then files (as the Finder lists them); a folder opens and closes, and the choice is
  // remembered. A folder starts closed, except the ones above the file that is open.
  const ICONS = { markdown: "¶", bib: "❝", csv: "▦", image: "▣", pdf: "⎙" };
  function fileTree(panel) {
    const root = { dirs: new Map(), files: [] };
    for (const n of S.project.tree) {
      const parts = n.name.split("/"); let d = root;
      for (const name of parts.slice(0, -1)) { if (!d.dirs.has(name)) d.dirs.set(name, { dirs: new Map(), files: [] }); d = d.dirs.get(name); }
      d.files.push(n);
    }
    const chosen = api.store.get("openDirs", {});            // folder -> true (open) or false (closed): what the author clicked
    const above = new Set(); (S.cur || "").split("/").slice(0, -1).reduce((acc, name) => { const p = acc ? acc + "/" + name : name; above.add(p); return p; }, "");
    const isOpen = p => (p in chosen ? chosen[p] : above.has(p));
    const byName = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
    const count = d => d.files.length + [...d.dirs.values()].reduce((n, s) => n + count(s), 0);
    const walk = (d, prefix, depth) => {
      for (const name of [...d.dirs.keys()].sort(byName)) {
        const path = prefix + name, sub = d.dirs.get(name), open = isOpen(path);
        const r = row(name, open ? "▾" : "▸", false, () => { chosen[path] = !open; api.store.set("openDirs", chosen); renderSide(); }, String(count(sub)), depth * 14);
        r.classList.add("dir"); panel.append(r);
        if (open) walk(sub, path + "/", depth + 1);
      }
      for (const n of d.files.sort((a, b) => byName(a.name, b.name))) panel.append(row(n.name.split("/").pop(), ICONS[n.kind] || "☰", n.name === S.cur, () => openFile(n.name), n.name === S.project.main ? "main" : "", depth * 14));
    };
    walk(root, "", 0);
  }
  function row(label, icon, on, run, meta = "", indent = 0) { const r = el("div", { className: "row" + (on ? " on" : ""), style: "padding-left:" + (12 + indent) + "px" }, el("span", { className: "ico" }, icon), label, meta ? el("span", { className: "meta" }, meta) : ""); r.onclick = run; return r; }
  const headings = text => { const out = []; let fence = false; text.split("\n").forEach((l, i) => { if (/^```/.test(l)) fence = !fence; const m = !fence && /^(#{1,6})\s+(.*)/.exec(l); if (m) out.push({ level: m[1].length, title: m[2], line: i + 1 }); }); return out; };
  function settingRow(s) {
    const cur = setting(s.key); let input;
    const err = el("div", { className: "err" });
    const commit = async () => { const r = await api.setSetting(s.key, input.type === "checkbox" ? (input.checked ? "1" : "0") : input.value);
      if (r.error) { err.textContent = r.error; } else { err.textContent = ""; S.settings[s.key] = r.value; if (input.type !== "checkbox") input.value = r.value; applySetting(s.key); } };
    if (s.kind === "flag") { input = el("input", { type: "checkbox", checked: cur === "1" }); input.onchange = commit; }
    else if (s.kind === "choice") { input = el("select", {}, ...(s.choices || []).map(c => el("option", { value: c, textContent: c, selected: c === cur }))); input.onchange = commit; }
    else { input = el("input", { type: "text", value: cur }); input.onchange = commit; }
    const label = el("label", {}, input.type === "checkbox" ? input : "", s.key, s.platforms.length < 4 ? el("span", { className: "plat" }, s.platforms.join(", ")) : "");
    return el("div", { className: "field" }, label, input.type === "checkbox" ? "" : input, el("div", { className: "help" }, s.help), err);
  }
  function applySetting(key) { if (key === "editorKind") switchEditorKind(setting("editorKind")); if (key === "renderAutoMaxLines" || key === "renderDelayMs") toast(key + " = " + setting(key)); }
  function diffDialog(e, h) {
    const d = $("#dialog"); d.textContent = ""; const diff = h.diff[e.id];
    d.append(el("h2", {}, e.title), el("div", { className: "dim small", style: "margin-bottom:8px" }, `${e.id} · ${e.files.join(", ")} · +${e.plus} −${e.minus}`));
    if (diff) { const pre = el("pre", { className: "diff" }); diff.split("\n").forEach(l => pre.append(el("div", { className: l[0] === "+" ? "a" : l[0] === "-" ? "d" : l[0] === "@" ? "h" : "" }, l || " "))); d.append(pre); }
    else d.append(el("div", { className: "dim" }, "This sample has no diff stored for this edit. The real one is `git diff` of the folder, drawn here."));
    d.append(el("div", { className: "buttons" }, el("button", { className: "btn", disabled: true, title: "needs the core (git restore)", textContent: "Restore this version" }), el("button", { className: "btn primary", textContent: "Close", onclick: () => d.close() })));
    d.showModal();
  }

  // ---------- chrome: menus, layouts, views, splitters ---------------------------------------------------------------------------
  function setLayout(l) {
    if (l === "tab" && window.NATIVE) return;
    if (l === "tab") { window.open(location.pathname + "#preview", "app-preview"); toast("Preview opened in a browser tab; it follows this page"); return; }
    S.layout = l; document.body.dataset.layout = l; $$("#layoutSeg button").forEach(b => b.classList.toggle("on", b.dataset.layout === l)); api.store.set("layout", l);
  }
  function setView(v) { S.view = v; $$("#viewSeg button").forEach(b => b.classList.toggle("on", b.dataset.view === v)); $("#liveView").hidden = v !== "html"; $("#pdfView").hidden = v !== "pdf"; $("#logView").hidden = v !== "log"; }
  function menuItems(name) {
    const mk = k => ({ label: T[k][1], keys: T[k][2], run: () => insert(k) });
    return ({
      file: [{ label: "Save", keys: MOD + "S", run: save }, { label: "Close tab", keys: MOD + "W", run: () => S.cur && closeTab(S.cur) }, "-", { label: "Export As", sub: exportTree() }, "-", { label: "Build", keys: MOD + "↩", run: runBuild }],
      edit: [{ label: "Undo", keys: MOD + "Z", run: () => S.editor.undo() }, { label: "Redo", keys: MOD + "⇧Z", run: () => S.editor.redo() }, "-", { label: "Find in all files", keys: MOD + "⇧F", run: () => setPanel("search") }],
      insert: ["comment", "code", "fence", "div", "calc", "-", "image", "link", "table", "-", "math", "mathblock", "footnote", "cite", "-", "pagebreak"].map(k => (k === "-" ? k : mk(k))),
      view: [{ head: "Layout" }, ...[["split", "Split"], ["editor", "Editor only"], ["preview", "Preview only"], ...(window.NATIVE ? [] : [["tab", "Preview in a browser tab"]]), ["focus", "Focus mode"]].map(([k, l]) => ({ label: l, check: S.layout === k, run: () => setLayout(k) })),
        "-", { head: "Editor" }, { label: "CodeMirror 6", check: S.editor.kind === "codemirror", run: () => switchEditorKind("codemirror") }, { label: "Plain text box", check: S.editor.kind === "textarea", run: () => switchEditorKind("plain") },
        "-", { head: "Panels" }, ...[["files", "Files and outline"], ["search", "Search"], ["checks", "Checks"], ["history", "History"], ["settings", "Settings"]].map(([k, l]) => ({ label: l, check: S.panel === k, run: () => setPanel(k) }))],
      format: [mk("bold"), mk("italic"), mk("code"), "-", ...[1, 2, 3].map(n => ({ label: "Heading " + n, run: () => heading(n) })), { label: "Normal text", run: () => heading(0) }, "-", mk("list")],
      help: [{ label: "About this prototype", run: about }],
    })[name];
  }
  function about() {
    const d = $("#dialog"); d.textContent = "";
    d.append(el("h2", {}, "APP: a prototype of the web UI"), el("div", {}, "Everything the page does goes through ", el("code", {}, "js/api.js"), " (today: fixtures made from a demo project and the real ", el("code", {}, "colophon export --list --json"), " and settings schema; later: ", el("code", {}, "pdfmd --serve"), ") and ", el("code", {}, "js/editor.js"), " (the editor contract)."),
      el("ul", {}, el("li", {}, "Real: the Export tree (111 pdfmd formats), the settings schema, the pandoc render of the demo, a PDF made by pdfmd."), el("li", {}, "Stand-in: the live render of edited text, the build run, history, checks (marked “sample”)."), el("li", {}, "Not here yet: click in the PDF to the source, real files, git.")),
      el("div", { className: "buttons" }, el("button", { className: "btn primary", textContent: "Close", onclick: () => d.close() })));
    d.showModal();
  }
  function drag(splitter, onMove) {
    splitter.addEventListener("pointerdown", e => { splitter.setPointerCapture(e.pointerId); splitter.classList.add("drag"); const move = ev => onMove(ev); const up = () => { splitter.classList.remove("drag"); splitter.removeEventListener("pointermove", move); splitter.removeEventListener("pointerup", up); }; splitter.addEventListener("pointermove", move); splitter.addEventListener("pointerup", up); });
  }

  function refreshAll() { const f = file(); $("#mainName").textContent = S.project.main; $("#projectName").textContent = S.project.name; $("#stKind").textContent = S.cur ? (S.cur.endsWith(".md") ? "Markdown" : S.cur.endsWith(".bib") ? "BibTeX" : "text") : ""; if (f) { $("#stWords").textContent = words(f.text) + " words"; renderLive(); } }

  // ---------- the native window (WKWebView): it owns the shortcuts and the menu bar and calls these; the page tells it what to show -----------
  const COMMANDS = {
    save, render: () => renderLive(), build: runBuild, newTab: newFile, closeTab: () => S.cur && closeTab(S.cur),
    find: () => setPanel("search"), undo: () => S.editor.undo(), redo: () => S.editor.redo(), settings: () => setPanel("settings"),
    layoutSplit: () => setLayout("split"), layoutEditor: () => setLayout("editor"), layoutPreview: () => setLayout("preview"), layoutFocus: () => setLayout("focus"),
    nextTab: () => cycleTab(1), previousTab: () => cycleTab(-1),
  };
  function cycleTab(d) { if (S.tabs.length > 1) openFile(S.tabs[(S.tabs.indexOf(S.cur) + d + S.tabs.length) % S.tabs.length]); }
  // command-1 .. command-8 of the native window: the nth tab; a number past the last tab does nothing
  for (let n = 1; n <= 8; n++) COMMANDS["tab" + n] = () => { const p = S.tabs[n - 1]; if (p) openFile(p); };
  COMMANDS.tabLast = () => { const p = S.tabs[S.tabs.length - 1]; if (p) openFile(p); };   // command-9: the last tab, whatever their number
  // The native window opens a file of the project in a tab (the file it was editing); false when there is no such file.
  window.appOpen = async path => { try { await openFile(path); return true; } catch (e) { toast("Could not open " + path + ": " + (e.message || e)); return false; } };
  // The native window hands over the text of an unsaved new file: a new tab of the project that holds it (unsaved, so the dot shows).
  window.appAdopt = async text => { try { await newFile(); S.editor.replaceSelection(text, false); return true; } catch (e) { toast("Could not take the text over: " + (e.message || e)); return false; } };
  // The native window saves the current file before it leaves for the plain editor: {saved: the file has nothing unsaved now, dirty: some tab has}.
  window.appSave = async () => { await save(); const f = file(); return { saved: !f || S.editor.getText() === f.saved, dirty: anyDirty() }; };
  // A file that another program changed while the page was out of focus: an unedited tab shows the new text (the caret stays), an edited one is
  // told, and its next save is refused by the core (the mtime it holds is the old one), so nothing is overwritten unseen.
  async function checkDisk() {
    for (const p of [...S.tabs]) {
      const f = S.files[p]; if (!f || f.view) continue;
      let disk; try { disk = await api.peekFile(p); } catch { continue; }
      if (disk.text === f.saved) continue;                                  // the disk still has what this tab loaded or saved
      const mine = p === S.cur ? S.editor.getText() : f.text;
      if (mine === f.saved) {
        await api.readFile(p);                                              // now the new mtime is the one a save sends
        f.text = f.saved = f.original = disk.text;
        if (p === S.cur) { const at = S.editor.selection().from; S.editor.setText(disk.text); S.editor.setSelection(Math.min(at, disk.text.length)); renderTabs(); renderLive(); }
        toast(p + " changed on disk: shown again");
      } else if (f.warned !== disk.text) { f.warned = disk.text; toast(p + " changed on disk, and this tab has changes that are not saved: saving it will be refused"); }
    }
  }
  window.addEventListener("focus", () => { if (S.project) checkDisk(); });
  COMMANDS.checkDisk = () => checkDisk();
  window.appCommand = name => { const c = COMMANDS[name]; if (!c) return false; c(); return true; };
  function anyDirty() { return S.tabs.some(p => { const f = S.files[p]; return f && !f.view && (p === S.cur ? S.editor.getText() !== f.saved : isDirty(f)); }); }
  function reportState() {
    if (!window.NATIVE || !S.project) return;
    const dirty = anyDirty();
    const st = JSON.stringify({ type: "state", project: S.project.name, main: S.project.main, cur: S.cur, tabs: S.tabs.length, dirty });
    if (st !== reportState.last) { reportState.last = st; window.NATIVE.post(JSON.parse(st)); }
  }

  // ---------- start ---------------------------------------------------------------------------------------------------------------
  async function start() {
    if (location.hash === "#preview") {                              // the preview in its own browser tab: it only listens
      document.body.classList.add("preview-only"); const ch = new BroadcastChannel("app-preview"); $("#live").innerHTML = "<p class='dim'>Waiting for the editor page …</p>";
      ch.onmessage = e => { $("#live").innerHTML = e.data.html; }; ch.postMessage({ hello: true }); return;
    }
    S.channel = new BroadcastChannel("app-preview"); S.channel.onmessage = e => { if (e.data.hello && S.lastHtml) S.channel.postMessage({ html: S.lastHtml }); };
    [S.project, S.schema, S.settings, S.exports, S.syntaxes] = await Promise.all([api.project(), api.settingsSchema(), api.settings(), api.exports(), api.syntaxes()]);
    roleColours(S.syntaxes);
    S.settings.renderMode = api.store.get("renderMode", "auto");
    mountEditor("");
    $("#renderMode").value = S.settings.renderMode;
    $("#renderMode").onchange = e => { api.store.set("renderMode", e.target.value); S.settings.renderMode = e.target.value; if (e.target.value === "instant") renderLive(); };
    $$("#menus .menu").forEach(b => b.onclick = () => showAt(b, menuItems(b.dataset.menu)));
    $$("#rail button[data-panel]").forEach(b => b.onclick = () => setPanel(b.dataset.panel));
    $$("#layoutSeg button").forEach(b => b.onclick = () => setLayout(b.dataset.layout));
    $$("#viewSeg button").forEach(b => b.onclick = () => setView(b.dataset.view));
    $("#exportBtn").onclick = e => showAt(e.currentTarget, exportTree());
    $("#buildBtn").onclick = runBuild; $("#buildMore").onclick = buildMenu;
    $("#headingSel").onchange = e => { heading(+e.target.value); e.target.value = ""; };
    $$("#toolbar [data-do]").forEach(b => b.onclick = e => { const d = b.dataset.do;
      if (d === "undo") S.editor.undo(); else if (d === "redo") S.editor.redo(); else if (d === "symbols") symbolsPicker(b); else if (d === "insertMenu") insertMenu(b); else insert(d); S.editor.focus(); });
    document.addEventListener("keydown", e => {
      const mod = e.metaKey || e.ctrlKey;
      if (e.key === "Escape" && S.layout === "focus") setLayout("split");
      if (!mod) return;
      if (e.metaKey && e.ctrlKey) return;        // control-command chords belong to the Mac's menu (the mode switch is control-command-S): not the page's Save
      const k = e.key.toLowerCase();
      if (k === "s") { e.preventDefault(); save(); }
      else if (k === "enter") { e.preventDefault(); runBuild(); }
      else if (k === "r") { e.preventDefault(); renderLive(); }
      else if (k === "w" && !e.shiftKey && S.cur && e.altKey) { e.preventDefault(); closeTab(S.cur); }
      else if (e.shiftKey && k === "f") { e.preventDefault(); setPanel("search"); }
      else if (e.altKey && altMap[e.code.replace("Key", "").toLowerCase()] && e.target.closest && e.target.closest("#editor")) { e.preventDefault(); e.stopPropagation(); insert(altMap[e.code.replace("Key", "").toLowerCase()]); }
      else if (!e.altKey && !e.shiftKey && keyMap()[k] && e.target.closest && e.target.closest("#editor")) { e.preventDefault(); e.stopPropagation(); insert(keyMap()[k]); }   // before the editor's own binding (Mod-i selects the parent syntax)
    }, true);
    drag($("#splitSide"), ev => { const w = Math.max(160, Math.min(520, ev.clientX - 44)); document.documentElement.style.setProperty("--side", w + "px"); });
    drag($("#splitWork"), ev => { const r = $("#work").getBoundingClientRect(); const p = Math.max(20, Math.min(80, ((ev.clientX - r.left) / r.width) * 100)); document.documentElement.style.setProperty("--split", p + "%"); });
    setLayout(api.store.get("layout", "split")); setView("html"); setPanel("files");
    const first = S.project.main || (S.project.tree.find(n => n.kind === "markdown") || S.project.tree[0] || {}).name;   // a folder with no Markdown file has no main
    const asked = new URLSearchParams(location.search).get("open");          // the Mac app opens the page on the file that was in its editor window
    if (!(asked && await window.appOpen(asked)) && first) await openFile(first);
    $("#checkBadge").textContent = (await api.checks()).items.length;
  }
  start();
  window.__app = S;    // for the self-test only
  if (location.hash.startsWith("#selftest")) document.head.append(el("script", { src: "js/selftest.js" }));
})();

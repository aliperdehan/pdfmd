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
    $("#stEditor").textContent = S.editor.kind === "codemirror" ? "editor: CodeMirror 6" : "editor: plain text box";
  }
  function switchEditorKind(kind) {
    S.settings.editorKind = kind; api.setSetting("editorKind", kind);
    const f = file(); mountEditor(f ? f.text : ""); onSelection(S.editor.selection()); toast("Editor: " + (kind === "codemirror" ? "CodeMirror 6" : "plain text box") + " (same contract)");
  }

  // ---------- tabs and files --------------------------------------------------------------------------------------------------
  async function openFile(path, line) {
    if (!S.files[path]) { const r = await api.readFile(path); S.files[path] = { text: r.text, saved: r.text, sel: 0, original: r.text }; }
    if (S.cur && S.files[S.cur]) { S.files[S.cur].text = S.editor.getText(); S.files[S.cur].sel = S.editor.selection().from; }
    if (!S.tabs.includes(path)) S.tabs.push(path);
    S.cur = path;
    S.editor.setText(S.files[path].text);
    S.editor.setSelection(S.files[path].sel || 0);
    if (line) S.editor.scrollTo(line);
    renderTabs(); renderSide(); refreshAll(); S.editor.focus();
  }
  function closeTab(path) {
    const f = S.files[path];
    if (f && isDirty(f) && !confirm(path + " has changes that are not saved. Close it anyway?")) return;
    if (f) f.text = f.saved;
    S.tabs = S.tabs.filter(p => p !== path);
    if (S.cur === path) { S.cur = null; if (S.tabs.length) openFile(S.tabs[S.tabs.length - 1]); else { S.editor.setText(""); renderTabs(); } }
    else renderTabs();
  }
  function renderTabs() {
    const box = $("#tabs"); box.textContent = "";
    for (const p of S.tabs) {
      const f = S.files[p], on = p === S.cur;
      const tab = el("div", { className: "tab" + (on ? " on" : ""), title: p }, p, (on ? S.editor.getText() !== f.saved : isDirty(f)) ? el("span", { className: "dot" }, "●") : "", el("span", { className: "x", textContent: "✕", title: "Close" }));
      tab.addEventListener("click", e => { if (e.target.classList.contains("x")) closeTab(p); else if (!on) openFile(p); });
      box.append(tab);
    }
  }
  async function save() {
    const f = file(); if (!f) return;
    f.text = S.editor.getText(); await api.writeFile(S.cur, f.text); f.saved = f.text; renderTabs(); toast("Saved " + S.cur);
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
  async function renderLive(fromSave) {
    const f = file(); if (!f) return;
    const text = S.editor.getText();
    const unchanged = text === f.original;
    const html = await api.renderLive(S.cur, text, unchanged);
    const live = $("#live"), top = $("#liveView").scrollTop;
    live.innerHTML = html; $("#liveView").scrollTop = top;
    banner(unchanged ? "" : "Showing the stand-in renderer (headings, text, lists, tables); the core's pandoc render replaces it. Math and citations appear as typed.");
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
  function insert(key) {
    const [tpl] = T[key], at = tpl.indexOf("¦"), text = tpl.replace("¦", "");
    const sel = S.editor.selection(), chosen = S.editor.getText().slice(sel.from, sel.to);
    if (chosen && at >= 0 && /^(bold|italic|code|link|math)$/.test(key)) {                // wrap the selection
      const pre = tpl.slice(0, at), post = tpl.slice(at + 1); S.editor.replaceSelection(pre + chosen + post, false); return;
    }
    S.editor.replaceSelection(text, false);
    if (at >= 0) { const here = S.editor.selection().from; S.editor.setSelection(here - (text.length - at)); }
  }
  function heading(level) {
    const sel = S.editor.selection(), text = S.editor.getText(), start = text.lastIndexOf("\n", sel.from - 1) + 1, end = text.indexOf("\n", sel.from) < 0 ? text.length : text.indexOf("\n", sel.from);
    const line = text.slice(start, end).replace(/^#{1,6}\s+/, "");
    S.editor.setSelection(start, end); S.editor.replaceSelection(level ? "#".repeat(level) + " " + line : line, false);
  }
  const SYMBOLS = {
    Greek: "αβγδεζηθλμνξπρστφχψωΔΘΛΠΣΦΨΩ",
    Math: "±×÷−≠≈≡≤≥∞√∑∏∫∂∇∈⊂∪∩∀∃→⇒⇄",
    Chemistry: "°•′″Å⇌→↑↓⁺⁻⁰¹²³⁴₀₁₂₃₄₅₆₇",
  };
  function symbolsPicker(anchor) {
    closePops();
    const box = el("div", { className: "popover" });
    for (const [name, chars] of Object.entries(SYMBOLS)) {
      box.append(el("div", { className: "head" }, name));
      const grid = el("div", { className: "symgrid" });
      for (const ch of [...chars]) grid.append(el("button", { textContent: ch, title: "U+" + ch.codePointAt(0).toString(16).toUpperCase(), onclick: () => { S.editor.replaceSelection(ch, false); closePops(); } }));
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
    S.building = false; $("#buildBtn").textContent = "Build"; $("#stBuild").textContent = "built " + r.output + " in " + r.seconds.toFixed(1) + " s";
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
  async function renderSide() {
    const side = $("#side"); side.textContent = "";
    const panel = el("div", { className: "panel" }); side.append(panel);
    if (S.panel === "files") {
      panel.append(el("h3", {}, "Files"));
      for (const n of S.project.tree) panel.append(row(n.name, n.kind === "markdown" ? "¶" : n.kind === "bib" ? "❝" : "☰", n.name === S.cur, () => openFile(n.name), n.name === S.project.main ? "main" : ""));
      const outline = S.cur ? await api.outline(S.cur) : [];
      const live = S.cur ? headings(file().text) : outline;
      panel.append(el("h3", {}, "Outline"));
      if (!live.length) panel.append(el("div", { className: "row dim" }, "no headings"));
      for (const h of live) panel.append(row(h.title, "§", false, () => S.editor.scrollTo(h.line), "", (h.level - 1) * 12));
    } else if (S.panel === "search") {
      const q = el("input", { type: "search", placeholder: "Search all files", value: S.searchQ }); panel.append(q, el("div", { id: "hits" }));
      const go = async () => { S.searchQ = q.value; const texts = Object.fromEntries(S.project.tree.filter(n => n.kind !== "bib").map(n => [n.name, (S.files[n.name] || { text: null }).text ?? null]));
        for (const n of S.project.tree) if (texts[n.name] == null) texts[n.name] = (await api.readFile(n.name)).text;
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
      view: [{ head: "Layout" }, ...[["split", "Split"], ["editor", "Editor only"], ["preview", "Preview only"], ["tab", "Preview in a browser tab"], ["focus", "Focus mode"]].map(([k, l]) => ({ label: l, check: S.layout === k, run: () => setLayout(k) })),
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

  // ---------- start ---------------------------------------------------------------------------------------------------------------
  async function start() {
    if (location.hash === "#preview") {                              // the preview in its own browser tab: it only listens
      document.body.classList.add("preview-only"); const ch = new BroadcastChannel("app-preview"); $("#live").innerHTML = "<p class='dim'>Waiting for the editor page …</p>";
      ch.onmessage = e => { $("#live").innerHTML = e.data.html; }; ch.postMessage({ hello: true }); return;
    }
    S.channel = new BroadcastChannel("app-preview"); S.channel.onmessage = e => { if (e.data.hello && S.lastHtml) S.channel.postMessage({ html: S.lastHtml }); };
    [S.project, S.schema, S.settings, S.exports] = await Promise.all([api.project(), api.settingsSchema(), api.settings(), api.exports()]);
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
    await openFile(S.project.main);
    $("#checkBadge").textContent = (await api.checks()).items.length;
  }
  start();
  window.__app = S;    // for the self-test only
  if (location.hash === "#selftest") document.head.append(el("script", { src: "js/selftest.js" }));
})();

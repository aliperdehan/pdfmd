// The only file that knows where data comes from. Today: fixtures/fixtures.js and a stand-in renderer. At S3 each function becomes one
// `fetch` of the endpoint named in its comment (pdfmd --serve), and the UI above it does not change. Every function returns a Promise.
(function () {
  "use strict";
  const F = window.FIXTURES;
  const later = (v, ms = 0) => new Promise(r => setTimeout(() => r(structuredClone(v)), ms));
  const store = {
    get: (k, d) => { try { const v = localStorage.getItem("app." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem("app." + k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  // ---- the stand-in for the core's live render --------------------------------------------------------------------------------
  // The real one is pandoc (CommonMark with source positions) behind POST /render; this one knows headings, paragraphs, lists, tables, fences and
  // the inline marks, and it CLOSES an unfinished **bold / *italic / `code` for display (shown dimmed until the author really closes it).
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  function inline(s) {
    const codes = [];
    s = esc(s).replace(/`([^`]+)`/g, (_, c) => "\u0000" + (codes.push("<code>" + c + "</code>") - 1) + "\u0000");
    s = s.replace(/`([^`]*)$/, (_, c) => "\u0000" + (codes.push('<code class="pending">' + c + "</code>") - 1) + "\u0000");   // an unfinished `code
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*\*(\S.*)$/, '<strong class="pending">$1</strong>');
    s = s.replace(/\*(\S(?:.*?\S)?)\*/g, "<em>$1</em>").replace(/\*(\S.*)$/, '<em class="pending">$1</em>');
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>').replace(/\$\$?([^$]+)\$\$?/g, '<span class="pending" title="math: the core renders it">$&</span>');
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[+i]);
  }
  function standIn(name, text) {
    const lines = text.split("\n");
    let i = 0, out = "";
    if (lines[0] === "---") { i = lines.indexOf("---", 1) + 1 || 0; }   // the YAML block is not shown
    const pos = (a, b) => ` data-pos="${name}@${a + 1}:1-${b + 1}:1"`;
    while (i < lines.length) {
      const L = lines[i];
      if (!L.trim()) { i++; continue; }
      let m, start = i;
      if ((m = /^(#{1,6})\s+(.*)/.exec(L))) { out += `<h${m[1].length}${pos(i, i + 1)}>${inline(m[2])}</h${m[1].length}>\n`; i++; continue; }
      if (/^```/.test(L)) { let j = i + 1; while (j < lines.length && !/^```/.test(lines[j])) j++; out += `<pre${pos(i, j + 1)}><code>${esc(lines.slice(i + 1, j).join("\n"))}</code></pre>\n`; i = j + 1; continue; }
      if (/^\s*([-*]|\d+\.)\s/.test(L)) { const ord = /^\s*\d+\./.test(L), tag = ord ? "ol" : "ul"; let items = ""; while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) { items += `<li${pos(i, i + 1)}>${inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+(\[[ x]\]\s+)?/, ""))}</li>`; i++; } out += `<${tag}${pos(start, i)}>${items}</${tag}>\n`; continue; }
      if (/^\|/.test(L)) { const rows = []; while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]); const cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        out += `<table${pos(start, i)}><thead><tr>${cells(rows[0]).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${rows.slice(2).map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>\n`; continue; }
      if (/^>/.test(L)) { let q = ""; while (i < lines.length && /^>/.test(lines[i])) q += lines[i++].replace(/^>\s?/, "") + " "; out += `<blockquote${pos(start, i)}>${inline(q)}</blockquote>\n`; continue; }
      let para = ""; while (i < lines.length && lines[i].trim() && !/^(#|```|\||>|\s*([-*]|\d+\.)\s)/.test(lines[i])) para += (para ? " " : "") + lines[i++];
      out += `<p${pos(start, i)}>${inline(para)}</p>\n`;
    }
    return out;
  }

  // ---- settings: a schema-driven validator (type, choices; no per-key code) ----------------------------------------------------
  // rows that only the web UI has (the real ones come from the same schema file as the others, S2): the live view's own numbers are
  // settings, not constants
  const EXTRA = [
    { key: "editorKind", kind: "choice", choices: ["codemirror", "plain"], default: "codemirror", tab: "Editor", help: "which editor the page uses: the vendored CodeMirror 6, or a plain text box (the Mac app can use its native editor)" },
    { key: "renderAutoMaxLines", kind: "number", default: "3000", tab: "Live view", help: "render mode auto: a file of up to this many lines renders after every edit (instant); a longer one renders on save (watch)" },
    { key: "renderDelayMs", kind: "number", default: "150", tab: "Live view", help: "instant mode: how long the page waits after the last keystroke before it renders" },
    { key: "mirrorSource", kind: "flag", default: "1", tab: "Live view", help: "1 = a selection in the source marks the part of the preview that it makes, and a block under the pointer marks its source lines" },
  ];
  const schema = [...EXTRA, ...F.settingsSchema];
  const MAC_ONLY = k => /^pop/.test(k) || /^studio/.test(k) || k === "textKit";    // sample: the real rows carry `platforms: [...]` (S2)
  const bySchema = Object.fromEntries(schema.map(s => [s.key, s]));
  function validate(key, raw) {
    const s = bySchema[key]; if (!s) return { error: "no such setting" };
    const t = String(raw).trim();
    if (s.kind === "flag") { const v = { "1": 1, on: 1, yes: 1, true: 1, "0": 0, off: 0, no: 0, false: 0 }[t.toLowerCase()]; return v == null ? { error: "use on or off" } : { value: String(v) }; }
    if (s.kind === "number") return t !== "" && isFinite(+t) ? { value: String(+t) } : { error: "a number, please" };
    if (s.kind === "choice") { const hit = (s.choices || []).find(c => c.toLowerCase() === t.toLowerCase()); return hit ? { value: hit } : { error: "one of: " + (s.choices || []).join(", ") }; }
    return { value: t };
  }

  // ---- the API: one function per planned endpoint -----------------------------------------------------------------------------
  window.api = {
    store,
    standIn,
    project: () => later(F.project),                                   // GET /project
    readFile: p => later(F.files[p]),                                  // GET /file?path=
    writeFile: (p, text) => { F.files[p].text = text; return later({ ok: true, mtime: new Date().toISOString() }); },   // PUT /file (409 on a newer mtime)
    outline: p => later(F.outline[p] || []),                           // GET /outline?path=
    renderLive: (p, text, unchanged) => later(unchanged && F.preview[p] ? F.preview[p] : standIn(p, text)),   // POST /render {file,text,mode:"live"}
    exports: () => later(F.exports),                                   // GET /formats  (pdfmd --list-formats --json, S1)
    settingsSchema: () => later(schema.map(s => ({ ...s, platforms: MAC_ONLY(s.key) ? ["macos"] : ["macos", "windows", "linux", "browser"] }))),   // GET /settings/schema
    settings: () => later(Object.fromEntries(schema.map(s => [s.key, store.get("set." + s.key, s.default)]))),                                  // GET /settings
    validate,                                                          // (client-side: the same schema, the same test cases as pdfmd's)
    setSetting: (key, raw) => { const r = validate(key, raw); if (r.value != null) store.set("set." + key, r.value); return later(r); },          // PUT /settings/KEY
    history: () => later(F.history),                                   // GET /history
    diff: id => later(F.history.diff[id] || null),                     // GET /history/ID/diff
    checks: () => later(F.checks),                                     // GET /checks  (pdfmd --check --json, S1)
    pdfUrl: () => "fixtures/report.pdf",
    build: (opts, onLine) => new Promise(resolve => {                  // POST /build  then  GET /job/ID/events (server-sent events)
      const lines = [...F.build.lines]; if (opts.engine) lines[0] = `$ pdfmd ${opts.file} -t pdf -e ${opts.engine}`;
      let i = 0; const t0 = performance.now();
      const tick = () => { if (i < lines.length) { onLine(lines[i++]); setTimeout(tick, 260); } else resolve({ ok: true, seconds: (performance.now() - t0) / 1000, output: opts.file.replace(/\.md$/, ".pdf") }); };
      tick();
    }),
    search: (q, texts) => { const out = []; const needle = q.toLowerCase(); if (!needle) return later([]);
      for (const [file, text] of Object.entries(texts)) text.split("\n").forEach((line, i) => { const at = line.toLowerCase().indexOf(needle); if (at >= 0) out.push({ file, line: i + 1, text: line, at, len: q.length }); });
      return later(out); },                                            // GET /search?q=
  };
})();

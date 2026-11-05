// The only file that knows where data comes from. Two sources, chosen once: the core when the page is served by `pdfmd --serve` (the
// endpoints named in the comments below, JSON, `api: 1`), else fixtures/fixtures.js and a stand-in renderer (a file opened from disk, the Mac
// app's window today, and every `#selftest`). The UI above does not change. Every function returns a Promise.
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
    s = s.replace(/&lt;!--([\s\S]*?)--&gt;/g, '<span class="cmt" title="a comment: it is not in the output">&lt;!--$1--&gt;</span>').replace(/&lt;!--([\s\S]*)$/, '<span class="cmt pending" title="an unfinished comment, closed for display">&lt;!--$1--&gt;</span>');   // an unfinished <!-- would hide the rest of the page in a real render
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>').replace(/\$\$?([^$]+)\$\$?/g, '<span class="pending" title="math: the core renders it">$&</span>').replace(/\$([^$]+)$/, '<span class="pending" title="unfinished math, closed for display">$$$1$$</span>');
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[+i]);
  }
  // `cache` maps the source text of a block to pandoc's HTML of it: a block that did not change is taken from there (its line numbers shifted),
  // one that did is made by this stand-in. The core will do the same with a hash of the block: a render costs what changed.
  function standIn(name, text, cache, stats) {
    const lines = text.split("\n");
    let i = 0, out = "";
    if (lines[0] === "---") { i = lines.indexOf("---", 1) + 1 || 0; }   // the YAML block is not shown
    const posOf = (a, b) => ` data-pos="${name}@${a + 1}:1-${b + 1}:1"`;
    const key = (a, b) => lines.slice(a, b).join("\n").replace(/\s+$/, "");
    function block(a, b, make) {                                          // lines a..b-1 (0-based) are one block
      const hit = cache && cache.get(key(a, b));
      if (hit) { if (stats) stats.kept++; const d = a + 1 - hit.a; return hit.html.replace(/@(\d+):(\d+)-(\d+):(\d+)/g, (_, p, q, r, t) => `@${+p + d}:${q}-${+r + d}:${t}`); }
      if (stats) stats.rendered++;
      return make(posOf(a, b));
    }
    while (i < lines.length) {
      const L = lines[i];
      if (!L.trim()) { i++; continue; }
      let m; const start = i;
      if ((m = /^(#{1,6})\s+(.*)/.exec(L))) { i++; out += block(start, i, p => `<h${m[1].length}${p}>${inline(m[2])}</h${m[1].length}>\n`); continue; }
      if (/^```/.test(L)) { let j = i + 1; while (j < lines.length && !/^```/.test(lines[j])) j++; i = j + 1; out += block(start, i, p => `<pre${p}><code>${esc(lines.slice(start + 1, j).join("\n"))}</code></pre>\n`); continue; }
      if (/^\s*([-*]|\d+\.)\s/.test(L)) { const tag = /^\s*\d+\./.test(L) ? "ol" : "ul"; while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) i++;
        out += block(start, i, p => `<${tag}${p}>${lines.slice(start, i).map(l => `<li>${inline(l.replace(/^\s*([-*]|\d+\.)\s+(\[[ x]\]\s+)?/, ""))}</li>`).join("")}</${tag}>\n`); continue; }
      if (/^\|/.test(L)) { while (i < lines.length && /^\|/.test(lines[i])) i++; const rows = lines.slice(start, i), cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        out += block(start, i, p => `<table${p}><thead><tr>${cells(rows[0]).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${rows.slice(2).map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>\n`); continue; }
      if (/^>/.test(L)) { while (i < lines.length && /^>/.test(lines[i])) i++; out += block(start, i, p => `<blockquote${p}>${inline(lines.slice(start, i).map(l => l.replace(/^>\s?/, "")).join(" "))}</blockquote>\n`); continue; }
      while (i < lines.length && lines[i].trim() && !/^(#|```|\||>|\s*([-*]|\d+\.)\s)/.test(lines[i])) i++;
      if (i === start) i++;
      out += block(start, i, p => `<p${p}>${inline(lines.slice(start, i).join(" "))}</p>\n`);
    }
    return out;
  }

  // the cache of a file: the source text of each block of its first text -> pandoc's HTML of that block
  const CACHE = {};
  function partial(p, text, unchanged) {
    if (!CACHE[p] && F.preview[p]) {
      const lines = F.files[p].text.split("\n"), tpl = document.createElement("template"); tpl.innerHTML = F.preview[p];
      const nodes = [...tpl.content.children].map(n => { const m = /@(\d+):\d+-(\d+):(\d+)/.exec(n.getAttribute("data-pos") || ""); return { n, a: m ? +m[1] : 0, c: m ? (+m[3] === 1 && +m[2] > +m[1] ? +m[2] - 1 : +m[2]) : 0 }; });
      nodes.forEach((x, i) => { const nx = nodes[i + 1]; if (nx && nx.a) x.c = Math.min(x.c, nx.a - 1); });
      CACHE[p] = new Map();
      for (const x of nodes) if (x.a) CACHE[p].set(lines.slice(x.a - 1, x.c).join("\n").replace(/\s+$/, ""), { a: x.a, html: x.n.outerHTML + "\n" });
    }
    if (unchanged && F.preview[p]) return { html: F.preview[p], stats: { kept: 0, rendered: 0 } };
    const stats = { kept: 0, rendered: 0 };
    return { html: standIn(p, text, CACHE[p], stats), stats };
  }

  // ---- settings: a schema-driven validator (type, choices; no per-key code) ----------------------------------------------------
  // rows that only the web UI has (the real ones come from the same schema file as the others, S2): the live view's own numbers are
  // settings, not constants
  const EXTRA = [
    { key: "editorKind", kind: "choice", choices: ["codemirror", "plain"], default: "codemirror", tab: "Editor", help: "which editor the page uses: the vendored CodeMirror 6, or a plain text box (the Mac app can use its native editor)" },
    { key: "symbolInsert", kind: "choice", choices: ["ascii", "unicode"], default: "ascii", tab: "Editor", help: "the symbols picker (Greek letters, math) inserts the LaTeX equivalent ($\\alpha$, plain ASCII, preferred) or the Unicode character itself" },
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

  // ---- the core: `pdfmd --serve` --------------------------------------------------------------------------------------------------
  // Decided once: a page served over http that finds the core's /api/project is live; a selftest never is (it is written for the demo).
  const probe = (async () => {
    if (!/^https?:$/.test(location.protocol) || location.hash.startsWith("#selftest")) return false;
    try { const r = await fetch("/api/project", { credentials: "same-origin" }); return r.ok && (await r.json()).api === 1; } catch { return false; }
  })();
  async function call(method, url, body) {
    const r = await fetch(url, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    const j = await r.json().catch(() => ({ error: r.statusText || "no answer", code: "bad_answer" }));
    if (!r.ok) { const e = new Error(j.error || r.statusText); e.status = r.status; e.code = j.code; e.answer = j; throw e; }
    return j;
  }
  const mtimes = {};          // the mtime each file had when it was read: a save sends it back, and the core answers 409 when the file changed on disk
  const lastHtml = {};
  const live = {
    project: () => call("GET", "/api/project"),
    readFile: async p => { const r = await call("GET", "/api/file?path=" + encodeURIComponent(p)); mtimes[p] = r.mtime; return r; },
    peekFile: p => call("GET", "/api/file?path=" + encodeURIComponent(p)),      // the same, without taking its mtime for the next save: a look at what the disk has
    createFile: async name => { const r = await call("POST", "/api/file", { path: name, text: "" }); mtimes[name] = r.mtime; return r; },
    writeFile: async (p, text) => { const r = await call("PUT", "/api/file", { path: p, text, mtime: mtimes[p] }); mtimes[p] = r.mtime; return r; },
    outline: async p => (await call("GET", "/api/outline?path=" + encodeURIComponent(p))).items,
    renderLive: async (p, text, unchanged) => {
      if (!/\.(md|markdown)$/i.test(p)) { api.lastRender = { live: true, kept: 0, rendered: 0 }; return ""; }
      if (unchanged && lastHtml[p] != null) return lastHtml[p];
      const r = await call("POST", "/api/render", { path: p, text });
      api.lastRender = { live: true, kept: 0, rendered: 1, seconds: r.seconds, warnings: r.warnings };
      return (lastHtml[p] = r.html);
    },
    history: async () => ({ note: "History is not connected to the core yet.", isRepo: false, edits: [], builds: [], diff: {} }),
    diff: async () => null,
    checks: async () => ({ note: "Checks are not connected to the core yet.", items: [] }),
    syntaxes: async () => { try { const r = await fetch("syntax/syntaxes.json"); return r.ok ? await r.json() : null; } catch { return null; } },   // the table the editor colours by (a static file of the page)
    build: (opts, onLine) => { onLine("The build is not connected to the core yet (the next slice: POST /api/build and its event stream)."); return Promise.resolve({ ok: false, seconds: 0, output: "" }); },
  };
  const choose = name => (...args) => probe.then(isLive => (isLive && live[name] ? live[name] : fixture[name])(...args));

  // ---- the API: one function per planned endpoint -----------------------------------------------------------------------------
  const fixture = {
    project: () => later(F.project),                                   // GET /project
    readFile: p => later(F.files[p]),                                  // GET /file?path=
    peekFile: p => later(F.files[p]),
    createFile: name => { F.files[name] = { text: "" }; F.project.tree.push({ name, kind: "markdown" }); F.outline[name] = []; F.preview[name] = ""; return later({ ok: true }); },   // POST /file (new)
    writeFile: (p, text) => { F.files[p].text = text; return later({ ok: true, mtime: new Date().toISOString() }); },   // PUT /file (409 on a newer mtime)
    outline: p => later(F.outline[p] || []),                           // GET /outline?path=
    // POST /render {file,text,mode:"live"}. Only the blocks that the edit touches are rendered anew; every other block keeps pandoc's own HTML (a
    // shifted line number is all that changes), which is what the core will do too: a render costs what changed, not what the file holds.
    renderLive: (p, text, unchanged) => { const r = partial(p, text, unchanged); api.lastRender = r.stats; return later(r.html); },
    exports: () => later(F.exports),                                   // GET /formats  (pdfmd --list-formats --json, S1)
    settingsSchema: () => later(schema.map(s => ({ ...s, platforms: MAC_ONLY(s.key) ? ["macos"] : ["macos", "windows", "linux", "browser"] }))),   // GET /settings/schema
    settings: () => later(Object.fromEntries(schema.map(s => [s.key, store.get("set." + s.key, s.default)]))),                                  // GET /settings
    validate,                                                          // (client-side: the same schema, the same test cases as pdfmd's)
    setSetting: (key, raw) => { const r = validate(key, raw); if (r.value != null) store.set("set." + key, r.value); return later(r); },          // PUT /settings/KEY
    history: () => later(F.history),                                   // GET /history
    diff: id => later(F.history.diff[id] || null),                     // GET /history/ID/diff
    checks: () => later(F.checks),                                     // GET /checks  (pdfmd --check --json, S1)
    syntaxes: () => later(F.syntaxes),                                 // syntax/syntaxes.json: a page opened from disk cannot fetch it, so the fixtures carry it
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
  window.api = {
    store,
    standIn: (n, t) => standIn(n, t),
    validate: fixture.validate,
    pdfUrl: fixture.pdfUrl,
    rawUrl: async p => (await probe) ? "/api/raw?path=" + encodeURIComponent(p) : null,   // GET /api/raw: a picture or a PDF of the project, as it is (null: the demo has none)
    live: () => probe,                                                  // true when the core answers
  };
  for (const name of Object.keys(fixture)) if (!(name in window.api)) window.api[name] = choose(name);
})();

// THE SYNTAX ENGINE of the page (see syntaxes.json for what it reads and the rules every client follows). It is bundled into the editor
// component (vendor/cm/entry.js) and also runs under node, so tests/test_syntax_table.py can check it against cases.json.
// No DOM, no CodeMirror: strings in, spans out. Offsets are UTF-16 units, JavaScript's own.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SyntaxEngine = factory();
})(this, function () {
  "use strict";

  const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  /** The table, ready to use: every pattern compiled once (the multiline flag makes ^ and $ mean a line's start and end; `d` gives the groups' places). */
  function compile(table) {
    const syntaxes = {}, languages = {}, roles = table.roles.map(r => r.key);
    for (const [name, s] of Object.entries(table.syntaxes)) {
      const fence = s.fences ? new RegExp("^ {0,3}(?:" + s.fences.markers.map(escape).join("|") + ")") : null;
      syntaxes[name] = {
        name, title: s.title, frontMatter: s.frontMatter || null, fences: s.fences || null, fence,
        language: s.fences && s.fences.language ? new RegExp(s.fences.language) : null,
        rules: s.rules.map(r => ({
          re: new RegExp(r.match, "gmd"),
          role: r.role == null ? -1 : roles.indexOf(r.role),
          groups: Object.entries(r.groups || {}).map(([n, role]) => [+n, roles.indexOf(role)]),
        })),
      };
      for (const word of s.languages || []) languages[word] = name;
    }
    return { roles, syntaxes, languages };
  }

  /** The syntax that colours a fenced block, from its opening line (null: none does, the block is one role). */
  function languageOf(c, name, openingLine) {
    const s = c.syntaxes[name], m = s.language && s.language.exec(openingLine);
    return (m && c.languages[m[1].toLowerCase()]) || null;
  }

  /** Where a front matter ends in `head` (the first characters of the text; the table's `frontMatter.scan` of them are looked at): the offset after its closing line, 0 if there is none. */
  function frontMatterEnd(c, name, head) {
    const fm = c.syntaxes[name].frontMatter;
    if (!fm || !head.startsWith(fm.open) || (head[fm.open.length] !== "\n" && head[fm.open.length] !== "\r")) return 0;
    const limit = Math.min(head.length, fm.open.length + fm.scan), at = fm.open.length;
    let best = -1;
    for (const closer of fm.close) {
      const i = head.slice(0, limit).indexOf("\n" + closer, at);
      if (i >= 0 && (best < 0 || i < best)) best = i;
    }
    if (best < 0) return 0;
    const nl = head.indexOf("\n", best + 1);
    return nl < 0 ? head.length : nl + 1;
  }

  /** Whether one line opens or closes a fenced block. */
  function isFenceLine(c, name, line) { const s = c.syntaxes[name]; return !!(s.fence && s.fence.test(line)); }

  /** The roles of the characters of `text` (a segment that starts at a line start) under the rules of syntax `name`, as runs [from, to, role]; the later rule wins. */
  function paint(c, name, text) {
    const rules = c.syntaxes[name].rules, owner = new Int16Array(text.length).fill(-1);
    for (const rule of rules) {
      rule.re.lastIndex = 0;
      for (const m of text.matchAll(rule.re)) {
        if (!m[0].length) continue;
        if (rule.role >= 0) owner.fill(rule.role, m.index, m.index + m[0].length);
        for (const [n, role] of rule.groups) { const at = m.indices[n]; if (at && at[1] > at[0]) owner.fill(role, at[0], at[1]); }
      }
    }
    const runs = [];
    for (let at = 0; at < owner.length;) {
      const role = owner[at]; let end = at + 1;
      while (end < owner.length && owner[end] === role) end++;
      if (role >= 0) runs.push([at, end, c.roles[role]]);
      at = end;
    }
    return runs;
  }

  /** The line starts of `text` that open or close a fence, after `from`. */
  function fenceStarts(c, name, text, from) {
    const found = [];
    for (let p = from; p < text.length;) {
      let e = text.indexOf("\n", p); e = e < 0 ? text.length : e;
      if (isFenceLine(c, name, text.slice(p, e))) found.push(p);
      p = e + 1;
    }
    return found;
  }

  /** The whole text: [from, to, role] runs, merged where two neighbours have one role. The reference for a client that colours a whole text at once. */
  function runs(c, name, text) {
    const s = c.syntaxes[name], out = [];
    const add = (from, to, role) => {
      const last = out[out.length - 1];
      if (last && last[1] === from && last[2] === role) last[1] = to; else out.push([from, to, role]);
    };
    const front = frontMatterEnd(c, name, text);
    if (front) for (const r of paint(c, s.frontMatter.syntax, text.slice(0, front))) add(r[0], r[1], r[2]);
    const lineEnd = p => { const e = text.indexOf("\n", p); return e < 0 ? text.length : e + 1; };
    const fences = s.fences ? fenceStarts(c, name, text, front) : [];
    let cursor = front, inCode = false, opener = 0;
    const code = (from, to) => {                                       // a fenced block: its language's rules, else one role
      if (to <= from) return;
      const lang = languageOf(c, name, text.slice(opener, text.indexOf("\n", opener) < 0 ? text.length : text.indexOf("\n", opener)));
      if (lang) for (const r of paint(c, lang, text.slice(from, to))) add(from + r[0], from + r[1], r[2]); else add(from, to, s.fences.role);
    };
    const body = (from, to) => { if (to > from) for (const r of paint(c, name, text.slice(from, to))) add(from + r[0], from + r[1], r[2]); };
    for (const f of fences) {
      if (inCode) code(cursor, f); else body(cursor, f);
      const end = lineEnd(f);
      add(f, end, s.fences.role);
      if (!inCode) opener = f;
      inCode = !inCode; cursor = end;
    }
    if (inCode) code(cursor, text.length); else body(cursor, text.length);
    return out;
  }

  /** The syntax for a file name: the one whose `extensions` has the file's; `markdown` for a file no syntax claims. */
  function syntaxFor(table, fileName) {
    const lower = fileName.toLowerCase(), dot = lower.lastIndexOf(".");
    const ext = dot >= 0 ? lower.slice(dot + 1) : "";
    for (const [name, s] of Object.entries(table.syntaxes)) if ((s.extensions || []).includes(ext)) return name;
    return "markdown";
  }

  return { compile, frontMatterEnd, isFenceLine, languageOf, paint, fenceStarts, runs, syntaxFor };
});

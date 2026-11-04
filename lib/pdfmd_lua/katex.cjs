// pdfmd: math for WeasyPrint (v3.28.11). WeasyPrint does not draw MathML; KaTeX's HTML, with its stylesheet and
// fonts, it prints as a browser does. pdfmd_lua/weasyprint.lua runs this once per document with node:
//
//   node katex.cjs < {"dir": "<the KaTeX folder>", "items": [{"tex": "x^2", "display": false}, ...]}
//   -> [{"html": "<span class=\"katex\">..."} | {"error": "KaTeX parse error: ..."}, ...]
//
// The KaTeX folder is the one `pdfmd --install math:katex` fills (katex.min.js, katex.min.css, fonts/, and
// contrib/mhchem.min.js, for a \ce pdfmd's own converter left alone). A formula KaTeX cannot read gets its error, and
// the filter prints that one as text. CommonJS (.cjs) whatever package.json is above it.
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const request = JSON.parse(fs.readFileSync(0, "utf8"));
const katex = require(path.join(request.dir, "katex.min.js"));
// mhchem's UMD wrapper takes the global katex when it is run as a plain script
globalThis.katex = katex;
const mhchem = path.join(request.dir, "contrib", "mhchem.min.js");
if (fs.existsSync(mhchem)) vm.runInThisContext(fs.readFileSync(mhchem, "utf8"), {filename: mhchem});

// LaTeX commands KaTeX lacks that documents use; one macros object, so a \gdef in one formula holds in the next
const macros = {"\\textmu": "\\text{\u00b5}"};
const answers = request.items.map((item) => {
  try {
    return {html: katex.renderToString(item.tex, {displayMode: Boolean(item.display), output: "html",
      throwOnError: true, strict: "ignore", trust: false, macros})};
  } catch (error) {
    return {error: String((error && error.message) || error)};
  }
});
process.stdout.write(JSON.stringify(answers));

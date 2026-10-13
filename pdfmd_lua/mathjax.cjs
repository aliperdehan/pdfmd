// pdfmd: math for WeasyPrint with MathJax (v3.28.46). WeasyPrint does not draw MathML; MathJax's CHTML (HTML and CSS, with
// the fonts of its math font package) it prints as a browser does. pdfmd_lua/weasyprint.lua runs this once per document with
// node, before KaTeX (katex.cjs), which takes what MathJax cannot read:
//
//   node mathjax.cjs < {"dir": "<the MathJax folder>", "font": "stix2", "items": [{"tex": "x^2", "display": false}, ...]}
//   -> {"css": "<the stylesheet of every formula>", "xheight": 0.479, "answers": [{"html": "<mjx-container ..."} | {"error": "..."}]}
//
// The folder is the one `pdfmd --install math:mathjax` fills: node_modules/@mathjax/src (the bundle) and, beside it,
// node_modules/@mathjax/mathjax-<font>-font. `xheight` is the height of the font's `x`, in em, for the size match with
// the body font. A formula MathJax cannot read gets its error (an undefined control sequence, an extra brace), and the
// filter hands it to KaTeX. CommonJS (.cjs) whatever package.json is above it.
"use strict";

const fs = require("fs");
const path = require("path");
const url = require("url");

const request = JSON.parse(fs.readFileSync(0, "utf8"));
const fontPackage = `mathjax-${request.font}-font`;
const fontFolder = path.join(request.dir, "node_modules", "@mathjax", fontPackage);
const MathJax = require(path.join(request.dir, "node_modules", "@mathjax", "src", "bundle", "node-main.cjs"));

// LaTeX commands MathJax lacks that documents use; one macros object, so a \gdef in one formula holds in the next
const macros = {textmu: "\\text{\u00b5}"};

MathJax.init({
  loader: {load: ["input/tex", "output/chtml"]},
  tex: {
    // no `require` (it would load extensions by name), and an error is an error, not a red box in the page
    packages: {"[-]": ["require", "noundefined", "noerrors"]},
    macros,
    formatError: (jax, error) => { throw error; },
  },
  output: {font: `mathjax-${request.font}`, fontURL: url.pathToFileURL(path.join(fontFolder, "chtml", "woff2")).href},
}).then(async (mj) => {
  const adaptor = mj.startup.adaptor;
  const answers = [];
  for (const item of request.items) {
    try {
      const node = await mj.tex2chtmlPromise(item.tex, {display: Boolean(item.display)});
      answers.push({html: adaptor.outerHTML(node)});
    } catch (error) {
      answers.push({error: String((error && error.message) || error)});
    }
  }
  // the font's x-height: the glyph of a math italic x is a box this high (`mjx-c.mjx-c1D465 {padding: .479em ...}`)
  await mj.tex2chtmlPromise("x", {display: false});
  const css = adaptor.cssText(mj.startup.output.styleSheet(mj.startup.document));
  const found = /mjx-c\.mjx-c1D465\s*\{\s*padding:\s*([0-9.]+)em/.exec(css);
  process.stdout.write(JSON.stringify({css, xheight: found ? Number(found[1]) : null, answers}));
}).catch((error) => {
  process.stderr.write(String((error && error.stack) || error) + "\n");
  process.exit(1);
});

// pdfmd: Graphviz without Graphviz (v3.28.32). `pdfmd --install diagram:dot` puts @hpcc-js/wasm-graphviz (Graphviz
// built to WebAssembly, no other files) in pdfmd's data folder, and its `dot`, `neato`, ... launchers run this script
// with node, which reads a graph on stdin or from a file and writes the drawing like the real tool:
//
//   node graphviz.cjs --lib <the wasm-graphviz folder> --engine dot [-Tsvg] [-o OUT] [FILE]
//
// Only the formats the WebAssembly build has: svg, dot, canon, json, plain. A PDF or PNG (-Tpdf, -Tpng), which
// Graphviz draws with Cairo, is an error with exit status 1; pdfmd_lua/diagram.lua then takes the SVG and converts it
// (rsvg-convert, inkscape) as it does for D2. Labels are sized by Graphviz's own estimate of the font, not by the
// installed font as a Graphviz with Pango does, so a box can differ a couple of percent from the real tool's.
// CommonJS (.cjs) whatever package.json is above it; the package itself is an ES module, loaded with import().
"use strict";

const fs = require("fs");
const path = require("path");
const {pathToFileURL} = require("url");

const FORMATS = ["svg", "dot", "canon", "json", "plain", "plain-ext"];
const ENGINES = ["dot", "neato", "fdp", "sfdp", "circo", "twopi", "osage", "patchwork"];

function fail(message) {
  process.stderr.write(`graphviz.cjs: ${message}\n`);
  process.exit(1);
}

const options = {lib: null, engine: "dot", format: "svg", output: null, input: null};
const argv = process.argv.slice(2);
for (let index = 0; index < argv.length; index += 1) {
  const word = argv[index];
  if (word === "--lib") options.lib = argv[++index];
  else if (word === "--engine") options.engine = argv[++index];
  else if (word === "-o") options.output = argv[++index];
  else if (word.startsWith("-o")) options.output = word.slice(2);
  else if (word.startsWith("-T")) options.format = word.slice(2) || "svg";
  else if (word.startsWith("-K")) options.engine = word.slice(2);
  else if (word === "-V") { process.stdout.write("dot - graphviz (WebAssembly build, pdfmd)\n"); process.exit(0); }
  else if (/^-[GNEq]/.test(word)) continue;               // attributes and quiet: the WebAssembly build has no command line
  else if (word.startsWith("-") && word !== "-") fail(`unknown option ${word}`);
  else options.input = word;
}
if (!options.lib) fail("--lib (the wasm-graphviz folder) is missing");
if (!ENGINES.includes(options.engine)) fail(`unknown layout engine ${options.engine}`);
if (!FORMATS.includes(options.format)) {
  fail(`-T${options.format} needs Graphviz with Cairo; the WebAssembly build writes ${FORMATS.join(", ")}`);
}

(async () => {
  const {Graphviz} = await import(pathToFileURL(path.join(options.lib, "dist", "index.js")).href);
  const graphviz = await Graphviz.load();
  const source = fs.readFileSync(options.input && options.input !== "-" ? options.input : 0, "utf8");
  let drawing;
  try {
    drawing = graphviz.layout(source, options.format, options.engine);
  } catch (error) {
    fail(String((error && error.message) || error));
  }
  if (options.output) fs.writeFileSync(options.output, drawing);
  else process.stdout.write(drawing);
})().catch((error) => fail(String((error && error.message) || error)));

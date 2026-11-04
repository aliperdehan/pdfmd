#!/bin/sh
# Rebuilds codemirror.js (the CodeMirror 6 editor component, MIT) from entry.js with the exact versions in package.json.
# Needs node and npm, only to build; the UI itself needs neither. Run it from anywhere: ./build.sh
set -eu
cd "$(dirname "$0")"
npm ci --no-audit --no-fund --silent
./node_modules/.bin/esbuild entry.js --bundle --minify --format=iife --target=es2020 --legal-comments=none --outfile=codemirror.js
wc -c codemirror.js

#!/usr/bin/env bash
# Smoke test of a built image: real builds in the container, as another user than root, with no network.
#   docker/smoke.sh IMAGE [tex] [office]
# `tex` says the image has TeX Live (the document is then built with lualatex as well), `office` that it has Calibre and
# LibreOffice (a Word, an EPUB and an ODT file are made, and Calibre and LibreOffice are run).
set -euo pipefail
image="$1"
variant=" ${*:2} "
work="$(mktemp -d "${SMOKE_TMP:-${TMPDIR:-/tmp}}/pdfmd-smoke.XXXXXX")"   # SMOKE_TMP: a folder the Docker VM shares (Colima shares only $HOME)
trap 'rm -rf "$work"' EXIT
chmod 777 "$work"
# shellcheck disable=SC2016  # the dollar signs are TeX math, not variables
printf '# Smoke\n\nText with $x^2$ and a table.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n' > "$work/s.md"

run() { docker run --rm --network none --user "$(id -u):$(id -g)" -v "$work":/work "$image" "$@"; }

# one output file per engine: a file removed on the host is not always gone at once inside a VM's shared folder (Colima)
run --version
run s.md -o default.pdf --no-stamp --no-backup
test -s "$work/default.pdf"
for engine in typst tectonic; do
  run s.md -e "$engine" -o "$engine.pdf" --no-stamp --no-backup
  test -s "$work/$engine.pdf"
done
if [[ "$variant" == *" tex "* ]]; then
  run s.md -e lualatex -o lualatex.pdf --no-stamp --no-backup
  test -s "$work/lualatex.pdf"
fi
if [[ "$variant" == *" office "* ]]; then
  for format in docx epub odt; do
    run s.md --to "$format" -o "s.$format" --no-stamp --no-backup
    test -s "$work/s.$format"
  done
  # the programs themselves, as the user pdfmd runs them as: Calibre (its own folder, off PATH) and LibreOffice
  docker run --rm --network none --user "$(id -u):$(id -g)" -v "$work":/work --entrypoint sh "$image" -c \
    'cd /work && /opt/pdfmd/data/pdfmd/calibre/*/ebook-convert s.epub s.mobi >/dev/null && soffice -env:UserInstallation=file:///tmp/lo --headless --convert-to pdf --outdir /work s.docx >/dev/null'
  test -s "$work/s.mobi"
  test -s "$work/s.pdf"
fi
echo "smoke test passed: $image"

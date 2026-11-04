# Vendored inkmd

This directory is a generated copy of inkmd 0.5.0 (https://github.com/eagredev/inkmd, MIT licence, see LICENSE).

- Upstream wheel: `inkmd-0.5.0-py3-none-any.whl`, SHA-256 `695c7c2ac0b317b7968b921cf2c02ba675d25a7293e483ba8301f5cd334b5b1c`
- Regenerate with `python3 scripts/vendor_inkmd.py`; never edit by hand.

Differences from upstream, all made by that script:

- the package is renamed from `inkmd` to `pdfmd_inkmd` (imports rewritten), so it
  cannot clash with a separately installed `inkmd`;
- `cli.py` and `__main__.py` are dropped;
- `assets/emoji/` (Noto Color Emoji, about 10 MB) is not shipped. Without it
  inkmd renders emoji as `[rocket]`-style labels. `pdfmd-cli[emoji]` installs the
  real `inkmd` package and pdfmd points this copy at its font.

Bundled text font: DejaVu Sans, see `assets/fonts/DejaVuSans-LICENSE.txt`.

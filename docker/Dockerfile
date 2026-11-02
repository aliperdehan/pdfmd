# syntax=docker/dockerfile:1
# pdfmd in a container: Markdown to PDF with nothing installed on the host but Docker.
#
#   docker run --rm -v "$PWD":/work ghcr.io/aliperdehan/pdfmd report.md
#
# One file, four variants chosen by build arguments (CI builds them all; see .github/workflows/publish.yml):
#   slim   (the default)  Pandoc, Typst, Tectonic, pdfmd's default fonts
#   TEX=1                 + TeX Live's LuaTeX and XeTeX, for documents that need lualatex (`engine: lualatex`)
#   OFFICE=1              + Calibre and LibreOffice, for `--to epub|docx|odt` and the office input formats
#   TEX=1 OFFICE=1        both
# The release is installed from PyPI, so PDFMD_VERSION must be a version that is already there.
FROM python:3.13-slim

ARG PDFMD_VERSION
ARG TEX=0
ARG OFFICE=0
ARG FONT_TIMEOUT=180

LABEL org.opencontainers.image.source="https://github.com/aliperdehan/pdfmd" \
      org.opencontainers.image.description="pdfmd: Markdown to a good-looking PDF (Pandoc wrapper)" \
      org.opencontainers.image.licenses="MIT"

# pdfmd keeps the tools it downloads under XDG_DATA_HOME and its caches under XDG_CACHE_HOME. Both live outside any
# user's home and are writable by everyone, so `docker run --user "$(id -u):$(id -g)"` works, and HOME is a folder
# that exists whoever runs it.
ENV XDG_DATA_HOME=/opt/pdfmd/data \
    XDG_CACHE_HOME=/opt/pdfmd/cache \
    HOME=/tmp \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=offscreen \
    CALIBRE_CONFIG_DIRECTORY=/tmp/calibre

RUN test -n "$PDFMD_VERSION" || { echo "build argument PDFMD_VERSION is required"; exit 1; }; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates fontconfig xz-utils; \
    if [ "$TEX" = 1 ]; then \
      apt-get install -y --no-install-recommends latexmk lmodern texlive-luatex texlive-xetex \
        texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-science texlive-pictures; \
    fi; \
    if [ "$OFFICE" = 1 ]; then \
      apt-get install -y --no-install-recommends libreoffice-writer-nogui \
        libegl1 libopengl0 libglx0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1 libxcb-image0 \
        libxcb-render-util0 libxkbcommon0 libxkbcommon-x11-0 libnss3 libxdamage1 libxcomposite1 libxrandr2 libxtst6 libasound2t64; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# pip may need a few seconds before a release that was uploaded a minute ago is listed.
RUN for attempt in 1 2 3 4 5 6; do \
      pip install "pdfmd-cli==$PDFMD_VERSION" && break; \
      [ "$attempt" = 6 ] && exit 1; \
      sleep 20; \
    done

# Pandoc and Typst (`full`), Tectonic (`core:tex`), Calibre when asked.
RUN mkdir -p "$XDG_DATA_HOME" "$XDG_CACHE_HOME" \
    && pdfmd --install full \
    && pdfmd --install core:tex \
    && if [ "$OFFICE" = 1 ]; then pdfmd --install calibre; fi

# The default fonts come from a CTAN mirror picked at random, and one that stalls would stall the build for ten minutes:
# each try gets a time limit, and a failed one is repeated (pdfmd itself has no retry for this yet).
RUN for attempt in 1 2 3 4 5; do \
      timeout "$FONT_TIMEOUT" pdfmd --install fonts:core && break; \
      [ "$attempt" = 5 ] && exit 1; \
      echo "fonts: try $attempt failed, trying again"; \
    done

# One build of a small document fills Tectonic's cache with the files it fetches on first use, so the first real run needs
# no network; the folders are then opened to every user.
RUN printf '# Warm\n\nText with $x^2$ and a table.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n' > /tmp/warm.md \
    && pdfmd /tmp/warm.md -e tectonic --no-stamp --no-backup \
    && rm -f /tmp/warm.* \
    && chmod -R a+rwX /opt/pdfmd

WORKDIR /work
ENTRYPOINT ["pdfmd"]

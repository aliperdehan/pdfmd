---
title: "Pandoc-flavoured"
author:
  - Ada Example
  - name: Bob Example
date: 2026-01-01
documentclass: article
header-includes:
  - \usepackage{chemfig}
pdfmd-options:
  no-auto: [monofont]
---

# Introduction {#sec:intro .unnumbered}

Text with a footnote[^note], a citation [@smith2020] and inline math $E=mc^2$.

::: {.callout}
A fenced div whose content stays.
:::

![A figure](missing.png){width=50%}

\newpage

\vspace{1cm}

```{=latex}
\begin{center}raw latex block\end{center}
```

\begin{tikzpicture}
\draw (0,0) -- (1,1);
\end{tikzpicture}

```
# Not a heading {#keep-this}
```

[^note]: The footnote text,
    continued on a second line.

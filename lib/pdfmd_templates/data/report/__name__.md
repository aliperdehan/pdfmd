---
title: "{{title}}"
subtitle: "A report"
author: "{{author}}"
date: "{{date}}"
toc: true
numbersections: true
---

# Summary

Three sentences: what was asked, what was found, what to do next.

# Data

The measurements live in `data.csv`; the table below is read from it, so editing the file edits the table.

::: {.csv file="data.csv"}
:::

# Method

```python
import statistics
rates = [0.42, 0.45, 0.51]
print(statistics.mean(rates))
```

# Conclusions

- What the data show.
- What they do not show.

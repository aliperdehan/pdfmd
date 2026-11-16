-- Native bibliography resources are literal file names, not prose. Run after citeproc and document filters.
-- Pandoc 3.1.3 otherwise escapes underscores in \bibliography / \addbibresource paths, so BibTeX/Biber cannot
-- open cached filtered sources or generated inline references. Current Pandoc already writes the literal names.

function Meta(meta)
  local method = PANDOC_WRITER_OPTIONS.cite_method
  if not meta.bibliography or (FORMAT ~= "latex" and FORMAT ~= "beamer") or (method ~= "natbib" and method ~= "biblatex") then
    return nil
  end
  local names = pandoc.utils.type(meta.bibliography) == "List" and meta.bibliography or {meta.bibliography}
  local resources = {}
  for _, name in ipairs(names) do
    resources[#resources + 1] = pandoc.MetaInlines({pandoc.RawInline("latex", pandoc.utils.stringify(name))})
  end
  meta.bibliography = pandoc.MetaList(resources)
  return meta
end

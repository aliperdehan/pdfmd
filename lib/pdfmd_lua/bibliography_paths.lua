-- Native bibliography resources are literal file names, not prose. Run after citeproc and document filters.
-- Pandoc escapes underscores in LaTeX and Typst paths, so the engine cannot open layered or cached sources.

local function typst_name(name)
  -- A native writer copies these names into its output; it does not fetch them from --resource-path.
  if not pandoc.path.is_absolute(name) and not name:match("^%a[%w+.-]*:") then
    local here = pandoc.system.get_working_directory()
    for _, folder in ipairs(PANDOC_STATE.resource_path or {"."}) do
      local candidate = pandoc.path.join({folder, name})
      if not pandoc.path.is_absolute(candidate) then candidate = pandoc.path.join({here, candidate}) end
      local file = io.open(candidate, "rb")
      if file then
        file:close()
        name = pandoc.path.normalize(candidate)
        break
      end
    end
  end
  -- The Typst template supplies the quotes: escape their contents as a string, without Markdown's \_.
  return pandoc.json.encode(name):sub(2, -2)
end

function Meta(meta)
  local method = PANDOC_WRITER_OPTIONS.cite_method
  local typst = FORMAT:match("^typst") ~= nil
  if not meta.bibliography or (not typst and
      ((FORMAT ~= "latex" and FORMAT ~= "beamer") or (method ~= "natbib" and method ~= "biblatex"))) then
    return nil
  end
  local names = pandoc.utils.type(meta.bibliography) == "List" and meta.bibliography or {meta.bibliography}
  local resources = {}
  for _, value in ipairs(names) do
    local name = pandoc.utils.stringify(value)
    resources[#resources + 1] = pandoc.MetaInlines({pandoc.RawInline(typst and "typst" or "latex", typst and typst_name(name) or name)})
  end
  meta.bibliography = pandoc.MetaList(resources)
  if typst and meta.csl then
    meta.csl = pandoc.MetaInlines({pandoc.RawInline("typst", typst_name(pandoc.utils.stringify(meta.csl)))})
  end
  return meta
end

-- Pandoc 3.1.3 writes cite("a", "b") and ignores modes/supplements. Keep that key-only rendering,
-- adapting strings and multi-key calls to current Typst's label API. Probe the writer rather than guessing a version.
local string_citations
function Cite(element)
  if not FORMAT:match("^typst") then return nil end
  if string_citations == nil then
    local fragment = pandoc.write(pandoc.Pandoc({pandoc.Plain({element})}), "typst")
    string_citations = fragment:match('^#cite%("') ~= nil
  end
  if not string_citations then return nil end
  local calls = {}
  for _, citation in ipairs(element.citations) do
    calls[#calls + 1] = "#cite(label(" .. pandoc.json.encode(citation.id) .. "))"
  end
  return pandoc.RawInline("typst", table.concat(calls))
end

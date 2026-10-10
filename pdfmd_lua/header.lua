-- pdfmd: LaTeX that pdfmd adds to the preamble when the command line has no --include-in-header (v3.27.16).
--
-- One --include-in-header replaces every `header-includes:` of the document and its metadata files (they share
-- Pandoc's one template variable, and the command line wins), so pdfmd cannot simply add a file of its own: a
-- metadata.yaml that loads a house package (nulabreport) would lose it. This filter appends the file named by
-- `-M pdfmd-header=PATH` to the header-includes Pandoc merged instead, after them, and takes the key out.

local function Meta(meta)
  local named = meta["pdfmd-header"]
  if named == nil then return nil end
  meta["pdfmd-header"] = nil
  local handle = io.open(pandoc.utils.stringify(named), "r")
  if not handle then return meta end
  local text = handle:read("a")
  handle:close()
  local block = pandoc.MetaBlocks({pandoc.RawBlock("latex", text)})
  local current = meta["header-includes"]
  if current == nil then
    meta["header-includes"] = pandoc.MetaList({block})
  elseif pandoc.utils.type(current) == "List" then
    current:insert(block)
    meta["header-includes"] = current
  else
    meta["header-includes"] = pandoc.MetaList({current, block})
  end
  return meta
end

return {{Meta = Meta}}

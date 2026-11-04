-- First of the two filters that give a Lua filter's `header-includes` back to a LaTeX build (v3.32.30; pdfmd.py,
-- headers_as_metadata). Pandoc puts --include-in-header files and `header-includes` in one template variable and the
-- files win, so every header file pdfmd passes drops what a filter (a kit's front-matter commands, say) put into the
-- metadata. pdfmd therefore passes its header files as -M pdfmd-header-file-N=PATH instead, and these two filters put
-- them into `header-includes` themselves. This one runs before the other filters and records what `header-includes`
-- holds then (the document's and the metadata files', which the header files carry already: pdfmd gave them back);
-- header_merge.lua, the last filter, adds what the filters made on top of that.
local utils = pandoc.utils

-- what an item of `header-includes` says, as LaTeX: stringify would give "" for a raw block, so every raw item would look alike
local function key(item)
  local kind = utils.type(item)
  local document
  if kind == "Blocks" then document = pandoc.Pandoc(item)
  elseif kind == "Inlines" then document = pandoc.Pandoc(pandoc.Blocks{pandoc.Plain(item)})
  elseif kind == "string" then return item
  else return utils.stringify(item) end
  local ok, text = pcall(pandoc.write, document, "latex")
  return ok and text or utils.stringify(item)
end

function Meta(meta)
  local seen = {}
  local value = meta["header-includes"]
  if value ~= nil then
    local items = utils.type(value) == "List" and value or { value }
    for _, item in ipairs(items) do seen[#seen + 1] = pandoc.MetaString(key(item)) end
  end
  meta["pdfmd-header-base"] = pandoc.MetaList(seen)
  return meta
end

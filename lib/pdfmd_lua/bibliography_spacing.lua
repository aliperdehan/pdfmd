-- CSL line-spacing belongs to refs only. Citeproc supplies the attribute on both supported Pandocs.
-- Word's newer writer already writes it; delimit the list so the XML fallback can fill only missing properties.
local target = FORMAT:lower():gsub("[+-].*$", "")
local here = (PANDOC_SCRIPT_FILE or ""):gsub("[^/\\]*$", "")
local csl_spacing = dofile(here .. "csl_spacing.lua")
local function spacing(div, meta)
  if div.identifier ~= "refs" then return nil end
  local lines = tonumber(div.attributes["line-spacing"] or "")
  if lines == nil and div.attributes["line-spacing"] == nil then lines = csl_spacing.attribute(meta, "line-spacing") end
  if not lines or lines <= 0 or lines ~= lines or lines == math.huge then return nil end
  local number = tostring(lines)
  div.attributes["line-spacing"] = number
  if target == "latex" or target == "beamer" then
    return {pandoc.RawBlock("latex", "\\begingroup\\linespread{" .. number .. "}\\selectfont"),
      div, pandoc.RawBlock("latex", "\\par\\endgroup")}
  elseif target == "typst" then
    -- typst.lua uses the existing pitch calculation and entry-spacing rule inside this local scope.
    return {pandoc.RawBlock("typst", "#[ // pdfmd CSL line-spacing"), div, pandoc.RawBlock("typst", "]")}
  elseif target:match("^html") or target:match("^epub") then
    local old = div.attributes.style
    div.attributes.style = (old and (old:gsub(";%s*$", "") .. "; ") or "") .. "line-height: " .. number .. ";"
    return {div}
  elseif target == "docx" then
    return {pandoc.RawBlock("openxml", "<!--pdfmd-csl-line-spacing:" .. number .. "-->"),
      div, pandoc.RawBlock("openxml", "<!--/pdfmd-csl-line-spacing-->")}
  end
end
function Pandoc(doc)
  return doc:walk({Blocks = function(blocks)
    local out, changed = pandoc.Blocks{}, false
    for _, block in ipairs(blocks) do
      local result = block.t == "Div" and spacing(block, doc.meta) or nil
      if result then out:extend(result); changed = true else out:insert(block) end
    end
    return changed and out or nil
  end})
end

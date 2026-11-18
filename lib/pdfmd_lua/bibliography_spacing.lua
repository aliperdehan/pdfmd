-- Bibliography line spacing belongs to refs only. In style mode, prefer citeproc's attribute.
-- Delimit the Word list so the XML finisher can fill missing properties or apply an explicit override.
local target = FORMAT:lower():gsub("[+-].*$", "")
local here = (PANDOC_SCRIPT_FILE or ""):gsub("[^/\\]*$", "")
local csl_spacing = dofile(here .. "csl_spacing.lua")
local key = "pdfmd-bibliography-line-spacing"
local function spacing(div, meta, mode)
  if div.identifier ~= "refs" then return nil end
  local number = mode
  if mode == "style" then
    local attribute = div.attributes["line-spacing"]
    local lines = attribute == nil and csl_spacing.attribute(meta, "line-spacing") or tonumber(attribute)
    if not lines or lines <= 0 or lines ~= lines or lines == math.huge then return nil end
    number = tostring(lines)
    div.attributes["line-spacing"] = number
  end
  if target == "latex" or target == "beamer" then
    return {pandoc.RawBlock("latex", "\\begingroup\\linespread{" .. number .. "}\\selectfont"),
      div, pandoc.RawBlock("latex", "\\par\\endgroup")}
  elseif target == "typst" then
    -- typst.lua uses the existing pitch calculation and entry-spacing rule inside this local scope.
    div.attributes[key] = number
    return {pandoc.RawBlock("typst", "#[ // pdfmd CSL line-spacing"), div, pandoc.RawBlock("typst", "]")}
  elseif target:match("^html") or target:match("^epub") then
    local old = div.attributes.style
    div.attributes.style = (old and (old:gsub(";%s*$", "") .. "; ") or "") .. "line-height: " .. number .. ";"
    return {div}
  elseif target == "docx" then
    local override = mode ~= "style" and ":override" or ""
    return {pandoc.RawBlock("openxml", "<!--pdfmd-csl-line-spacing:" .. number .. override .. "-->"),
      div, pandoc.RawBlock("openxml", "<!--/pdfmd-csl-line-spacing-->")}
  end
end
function Pandoc(doc)
  local mode = pandoc.utils.stringify(doc.meta[key])
  doc.meta[key] = nil
  if mode ~= "style" and not tonumber(mode) then return doc end
  return doc:walk({Blocks = function(blocks)
    local out, changed = pandoc.Blocks{}, false
    for _, block in ipairs(blocks) do
      local result = block.t == "Div" and spacing(block, doc.meta, mode) or nil
      if result then out:extend(result); changed = true else out:insert(block) end
    end
    return changed and out or nil
  end})
end

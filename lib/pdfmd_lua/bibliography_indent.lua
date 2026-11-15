-- pdfmd: the hanging indent of the combined reference list (runs AFTER --citeproc; `bibliography-indent` is the setting, see
-- pdfmd_bibliography). pdfmd passes `-M pdfmd-bibliography-indent=1.5em` when the setting is set (`0pt` for none), and
-- `-M pdfmd-bibliography-indent-default=1.5em` when it is not, which only Typst takes: Pandoc's Typst writer ignores citeproc's
-- `hanging-indent` class, so the list had none.
--
-- Only a list whose style asks for a hanging indent (the `hanging-indent` class on citeproc's `refs` div) gets one:
--   LaTeX, Beamer   `\setlength{\cslhangindent}{X}` before the list (the template's `CSLReferences` reads it)
--   Typst           `#[#set par(hanging-indent: X)` ... `]` around the list
--   HTML family     `margin-left: X; text-indent: -X` on each entry (over the writer's style sheet)
--   Word, OpenDocument  each entry in the paragraph style `pdfmd-hang-<X>` (a "." written "p"), and the class is dropped so the writer's
--                   own 0.5 in is not added; pdfmd_office writes the indent into the style afterwards
-- A zero (`0pt`) is no indent in each of them. Other writers are left as they are.

local explicit, default = nil, nil

local target = FORMAT:lower():gsub("[+-].*$", "")
local TEX = {latex = true, beamer = true}
local HTML = {html = true, html4 = true, html5 = true, epub = true, epub2 = true, epub3 = true, revealjs = true,
  slidy = true, slideous = true, s5 = true, dzslides = true, chunkedhtml = true}
local OFFICE = {docx = true, odt = true, opendocument = true}

local function zero(length) return not length:find("[1-9]") end

local function style_for(entry_content, length)
  return pandoc.Div(entry_content, pandoc.Attr("", {}, {["custom-style"] = "pdfmd-hang-" .. length:gsub("%.", "p")}))
end

local function change(div, blocks)
  local length = explicit or (target == "typst" and default) or nil
  if not length then return nil end
  local none = zero(length)
  if TEX[target] then
    if not explicit then return nil end
    return {pandoc.RawBlock("latex", "\\ifdefined\\cslhangindent\\setlength{\\cslhangindent}{" .. (none and "0pt" or length) .. "}\\fi"), div}
  end
  if not div.classes:includes("hanging-indent") then return nil end
  if target == "typst" then
    if none then return nil end
    return {pandoc.RawBlock("typst", "#[#set par(hanging-indent: " .. length .. ")"), div, pandoc.RawBlock("typst", "]")}
  elseif HTML[target] then
    local style = none and "margin-left: 0; text-indent: 0;" or ("margin-left: " .. length .. "; text-indent: -" .. length .. ";")
    div.content = div.content:map(function(entry)
      if entry.t == "Div" and entry.classes:includes("csl-entry") then entry.attributes.style = style end
      return entry
    end)
    return {div}
  elseif OFFICE[target] and explicit then
    div.classes = div.classes:filter(function(name) return name ~= "hanging-indent" end)
    if not none then
      div.content = div.content:map(function(entry)
        if entry.t == "Div" and entry.classes:includes("csl-entry") then
          entry.content = {style_for(entry.content, length)}
        end
        return entry
      end)
    end
    return {div}
  end
  return nil
end

function Pandoc(doc)
  local meta = doc.meta
  if meta["pdfmd-bibliography-indent"] then explicit = pandoc.utils.stringify(meta["pdfmd-bibliography-indent"]) end
  if meta["pdfmd-bibliography-indent-default"] then default = pandoc.utils.stringify(meta["pdfmd-bibliography-indent-default"]) end
  return doc:walk({
    Blocks = function(blocks)
      local out, changed = pandoc.List(), false
      for _, block in ipairs(blocks) do
        local result = block.t == "Div" and block.identifier == "refs" and change(block, blocks) or nil
        if result then
          out:extend(result)
          changed = true
        else
          out:insert(block)
        end
      end
      if changed then return out end
    end,
  })
end

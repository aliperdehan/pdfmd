-- Code blocks in LaTeX builds: long lines wrap instead of running past the margin (fvextra's breaklines), and
-- lines can be numbered. Per block: `.numberLines` / `startFrom="10"` (Pandoc's own), `.noNumberLines` (off when
-- numbering is on for the document), `step="5"` (number every 5th line), `numbersep="8pt"`, `wrap="false"`.
-- Per document: pdfmd-options `code-wrap: true|false` (default true), `line-numbers: true|false`,
-- `line-number-step: N`; the same keys in the global config reach this filter as -M pdfmd-code-wrap=... etc.
-- The header that loads fvextra is pdfmd_lua/code_wrap.tex, passed by pdfmd with --include-in-header (a header set from
-- here would be lost: Pandoc lets --include-in-header win over `header-includes`), together with -M pdfmd-code-header=1;
-- without that flag no block is turned into a Verbatim.

local function read(meta, key)
  local value = meta["pdfmd-" .. key]
  local options = meta["pdfmd-options"]
  if value == nil and options ~= nil and type(options) == "table" and options[key] ~= nil then value = options[key] end
  if value == nil then return nil end
  return pandoc.utils.stringify(value)
end

local function truthy(text, default)
  if text == nil then return default end
  text = text:lower()
  if text == "true" or text == "on" or text == "yes" then return true end
  if text == "false" or text == "off" or text == "no" then return false end
  return default
end

local function has(classes, name)
  for _, class in ipairs(classes) do
    if class == name then return true end
  end
  return false
end

local function without(classes, name)
  local out = {}
  for _, class in ipairs(classes) do
    if class ~= name then out[#out + 1] = class end
  end
  return out
end

function Pandoc(doc)
  local meta = doc.meta
  local wrap = truthy(read(meta, "code-wrap"), true)
  local numbers = truthy(read(meta, "line-numbers"), false)
  local step = read(meta, "line-number-step")
  local header = read(meta, "code-header") == "1"

  local function code(block)
    local attributes = block.attr.attributes
    local classes = block.classes
    local before = {}
    if numbers and not has(classes, "numberLines") and not has(classes, "noNumberLines") then
      classes = {table.unpack(classes)}
      classes[#classes + 1] = "numberLines"
    end
    local number = has(classes, "numberLines")
    local settings = {}
    if number then
      local wanted = attributes["step"] or step
      if wanted and tonumber(wanted) and tonumber(wanted) > 1 then settings[#settings + 1] = "stepnumber=" .. tonumber(wanted) end
      if attributes["numbersep"] then settings[#settings + 1] = "numbersep=" .. attributes["numbersep"] end
    end
    if attributes["wrap"] == "false" then settings[#settings + 1] = "breaklines=false" end
    classes = without(classes, "noNumberLines")
    -- a block with no language is `verbatim` for Pandoc (which cannot wrap or number it): fancyvrb's Verbatim instead
    if header and (wrap or number) and #without(classes, "numberLines") == 0 and block.identifier == "" and
        not block.text:find("\\end{Verbatim}", 1, true) then
      local options = {}
      if number then
        options[#options + 1] = "numbers=left"
        if attributes["startFrom"] then options[#options + 1] = "firstnumber=" .. attributes["startFrom"] end
      end
      for _, setting in ipairs(settings) do options[#options + 1] = setting end
      local open = "\\begin{Verbatim}" .. (#options > 0 and "[" .. table.concat(options, ",") .. "]" or "")
      return pandoc.RawBlock("latex", open .. "\n" .. block.text .. "\n\\end{Verbatim}")
    end
    local changed = number ~= has(block.classes, "numberLines") or #classes ~= #block.classes
    if #settings == 0 and not changed then return nil end
    local kept = {}
    for key, value in pairs(attributes) do
      if key ~= "step" and key ~= "numbersep" and key ~= "wrap" then kept[#kept + 1] = {key, value} end
    end
    local result = pandoc.CodeBlock(block.text, pandoc.Attr(block.identifier, classes, kept))
    if #settings == 0 then return result end
    return {pandoc.RawBlock("latex", "\\begingroup\\fvset{" .. table.concat(settings, ",") .. "}"), result,
            pandoc.RawBlock("latex", "\\endgroup")}
  end

  return pandoc.Pandoc(doc.blocks:walk({CodeBlock = code}), meta)
end

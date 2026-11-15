-- pdfmd: the full reference in place, second half (runs AFTER --citeproc; fullcite_mark.lua is the first half).
--
-- A span `[@key]{.fullcite}` (fullcite_mark.lua has turned the other spellings into it and put the keys into `pdfmd-keys`) is
-- replaced by the reference citeproc formatted for that key, taken from its `refs` div:
--   - a paragraph made only of such spans becomes the entries, as blocks, with the hanging indent of the bibliography;
--   - a span inside a sentence becomes the text of the entry.
-- A key citeproc has no reference for prints `WARN  <document>: fullcite: no reference for 'KEY'` (counted by --strict), and the
-- citation it was written as stays.
--
-- The combined list (`pdfmd-fullcite-list`, `-M` by pdfmd): `rest` takes the placed entries out of it (the default), `all` keeps
-- every entry, `none` removes the list. A list that ends up empty goes with the heading right before it. `list=keep` and
-- `list=drop` on one entry (or on its `::: {.fullcite list=keep}` block) beat that setting for that entry.
--
-- The indent (`pdfmd-fullcite-indent`, a length; none for 0) is applied when the style asks for a hanging indent (citeproc's
-- `hanging-indent` class on the list): `\hangindent` in LaTeX, `#par(hanging-indent:)` in Typst (whose writer ignores the
-- class), a margin and a negative text indent in the HTML writers, a paragraph style `pdfmd-hang-<length>` in Word and OpenDocument
-- (written by pdfmd_office; the Bibliography style when there is no indent); the other writers print the entry as it is.

local meta = {}
local hanging = false
local entries = {}                -- key -> blocks of the entry
local placed = {}                 -- key -> "" (placed) or "keep" / "drop"
local warned = {}

local target = FORMAT:lower():gsub("[+-].*$", "")
local TEX = {latex = true, beamer = true}
local HTML = {html = true, html4 = true, html5 = true, epub = true, epub2 = true, epub3 = true, revealjs = true,
  slidy = true, slideous = true, s5 = true, dzslides = true, chunkedhtml = true}
local OFFICE = {docx = true, odt = true, opendocument = true}

local function setting(name, default)
  local value = meta[name]
  if value == nil then return default end
  return pandoc.utils.stringify(value)
end

local function indent()
  local value = setting("pdfmd-fullcite-indent", "")
  if value == "" or value:match("^0+%.?0*%a*$") then return nil end
  return value
end

local function warn(key)
  if warned[key] then return end
  warned[key] = true
  io.stderr:write("WARN  " .. setting("pdfmd-fullcite-doc", "document") .. ": fullcite: no reference for '" .. key .. "'\n")
end

-- the entries of citeproc's list, by key
local function harvest(doc)
  doc:walk({
    Div = function(div)
      if div.identifier ~= "refs" then return nil end
      if div.classes:includes("hanging-indent") then hanging = true end
      for _, entry in ipairs(div.content) do
        if entry.t == "Div" and entry.identifier:match("^ref%-") then entries[entry.identifier:sub(5)] = entry end
      end
      return nil
    end,
  })
end

local function keys_of(span)
  local keys = {}
  for key in (span.attributes["pdfmd-keys"] or ""):gmatch("%S+") do keys[#keys + 1] = key end
  return keys
end

local function is_marker(element)
  return element.t == "Span" and element.classes:includes("fullcite") and element.attributes["pdfmd-keys"] ~= nil
end

local function note_placed(key, span)
  local mode = span.attributes["list"]
  placed[key] = (mode == "keep" or mode == "drop") and mode or placed[key] or ""
end

-- a paragraph whose content is spans and the separators between them
local function only_markers(block)
  local found = false
  for _, inline in ipairs(block.content) do
    if is_marker(inline) then
      found = true
    elseif not (inline.t == "Space" or inline.t == "SoftBreak" or inline.t == "LineBreak"
        or (inline.t == "Str" and inline.text:match("^[;,]$"))) then
      return false
    end
  end
  return found
end

local function hang_tex(blocks, length)
  local mark = pandoc.RawInline("latex", "\\hangindent=" .. length .. "\\hangafter=1\\relax{}")
  local copy = pandoc.List()
  for _, block in ipairs(blocks) do
    if block.t == "Para" or block.t == "Plain" then
      local content = pandoc.List({mark})
      content:extend(block.content)
      block = (block.t == "Para" and pandoc.Para or pandoc.Plain)(content)
    end
    copy:insert(block)
  end
  return copy
end

-- the blocks that stand for one placed entry
local function entry_blocks(key)
  local entry = entries[key]
  local content = entry.content
  local length = hanging and indent() or nil
  if TEX[target] then
    return length and hang_tex(content, length) or content
  elseif target == "typst" then
    if not length then return content end
    local rendered = pandoc.write(pandoc.Pandoc(content), "typst")
    return {pandoc.RawBlock("typst", "#par(hanging-indent: " .. length .. ")[\n" .. rendered .. "]")}
  elseif HTML[target] then
    local attributes = {}
    if length then attributes.style = "margin-left: " .. length .. "; text-indent: -" .. length .. ";" end
    return {pandoc.Div(content, pandoc.Attr("", entry.classes, attributes))}
  elseif OFFICE[target] then
    local style = length and ("pdfmd-hang-" .. length:gsub("%.", "p")) or "Bibliography"      -- pdfmd_office writes the indent into it
    return {pandoc.Div(content, pandoc.Attr("", {}, {["custom-style"] = style}))}
  end
  return content
end

-- the text of one entry, for a span inside a sentence
local function entry_inlines(key)
  local out = pandoc.List()
  pandoc.Blocks(entries[key].content):walk({
    Para = function(block) if #out > 0 then out:insert(pandoc.Space()) end out:extend(block.content) end,
    Plain = function(block) if #out > 0 then out:insert(pandoc.Space()) end out:extend(block.content) end,
  })
  return out
end

local function place_blocks(block)
  if not only_markers(block) then return nil end
  local out = pandoc.List()
  for _, inline in ipairs(block.content) do
    if is_marker(inline) then
      local missing = false
      for _, key in ipairs(keys_of(inline)) do
        if entries[key] then
          note_placed(key, inline)
          out:extend(entry_blocks(key))
        else
          warn(key)
          missing = true
        end
      end
      if missing and #keys_of(inline) == 1 then out:insert(pandoc.Para(inline.content)) end
    end
  end
  return out
end

local function place_span(span)
  if not is_marker(span) then return nil end
  local out = pandoc.List()
  for number, key in ipairs(keys_of(span)) do
    if entries[key] then
      note_placed(key, span)
      if number > 1 then out:insert(pandoc.Space()) end
      out:extend(entry_inlines(key))
    else
      warn(key)
    end
  end
  if #out == 0 then return span.content end        -- nothing found: the citation stays
  return out
end

-- whether an entry of the combined list goes: `list=drop` always, `list=keep` never, else by the setting
local function leaves(key, mode)
  local say = placed[key]
  if say == "drop" then return true end
  if say == "keep" then return false end
  if mode == "none" then return true end
  return mode == "rest" and say ~= nil
end

-- the combined list, less what went into the text; a list left empty goes with the heading right before it
local function list_blocks(blocks)
  local mode = setting("pdfmd-fullcite-list", "rest")
  local out = pandoc.List()
  local changed = false
  for _, block in ipairs(blocks) do
    local drop = false
    if block.t == "Div" and block.identifier == "refs" then
      local kept = pandoc.List()
      local removed = 0
      for _, entry in ipairs(block.content) do
        local key = entry.t == "Div" and entry.identifier:match("^ref%-(.+)$")
        if key and leaves(key, mode) then removed = removed + 1 else kept:insert(entry) end
      end
      if removed > 0 then
        changed = true
        if #kept == 0 then
          drop = true
          if out[#out] and out[#out].t == "Header" then out:remove(#out) end
        else
          block.content = kept
        end
      end
    end
    if not drop then out:insert(block) end
  end
  if not changed then return nil end
  return out
end

function Pandoc(doc)
  meta = doc.meta
  harvest(doc)
  doc = doc:walk({Para = place_blocks, Plain = place_blocks})
  doc = doc:walk({Span = place_span})
  doc = doc:walk({Blocks = list_blocks})
  return doc
end

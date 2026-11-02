-- Table captions from a line typed by hand (v3.31.46, entry 3dy).
--
-- Many documents write the caption of a table as a bold paragraph next to it: `**Table 1: Results**`. gfm has no table caption
-- at all, and in Pandoc Markdown that line is only a paragraph, so the engine numbers the table by itself and the typed label is
-- lost or printed twice. This filter turns such a paragraph into the table's real caption.
--
-- A paragraph is taken for a caption when it is
--   * entirely one bold span that STARTS with a label word (Table, Таблица, Tabelle ...: the list comes from pdfmd, by `lang:` and
--     the `table-caption-words` setting) followed by a number or a punctuation mark or nothing, or
--   * (only when `table-caption-colon-words` is above 0) a short paragraph that starts with `: `, which is gfm's way to
--     write a caption that Pandoc Markdown reads itself; it is short when it has at most that many words,
-- and it stands IMMEDIATELY above a table that has no caption (a caption above wins), or else immediately below one.
-- A trailing `{#tbl:id}` becomes the table's identifier when the table has none. The label words are cut off by default (the
-- engine numbers the table: `label=keep` leaves them); the rest of the line keeps its markup.
--
-- Modes, `-M pdfmd-table-captions=`: `on` does it; `note` (pdfmd's default) changes nothing and says once how many lines would
-- have been captions. Words: `-M pdfmd-table-caption-words=Table,Tabelle`; `-M pdfmd-table-caption-label=strip|keep`;
-- `-M pdfmd-table-caption-colon-words=2`; `-M pdfmd-table-caption-need-label=off` takes ANY paragraph that is one bold span for a
-- caption (a label word, when it has one, is still cut off).

local mode = "note"
local label_mode = "strip"
local colon_words = 0
local need_label = true
local words = {}
local noted = 0
local first_example = nil

local text = pandoc.text

local function setting(meta, key)
  local value = meta[key]
  if value == nil then return nil end
  return pandoc.utils.stringify(value)
end

-- the dashes are folded to "-" so a character class can hold them
local function fold(s)
  return (s:gsub("\u{2013}", "-"):gsub("\u{2014}", "-"):gsub("\u{2212}", "-"))
end

-- is `prefix` (the start of a caption) only a label: a label word, then numbers and punctuation?
local function is_label(prefix)
  local lowered = fold(text.lower(prefix))
  lowered = lowered:gsub("^%s+", "")
  for _, word in ipairs(words) do
    if lowered:sub(1, #word) == word then
      local rest = lowered:sub(#word + 1)
      local first = rest:sub(1, 1)
      -- a letter right after the word means another word (Tables, Tablet): bytes above 127 are letters of some script
      if first == "" or (first:byte() < 128 and not first:match("%a")) then
        if rest:match("^[%s%d%.:%)%-]*$") then return true end
      end
    end
  end
  return false
end

local function slice(list, from, to)
  local out = pandoc.Inlines{}
  for k = from, to do out:insert(list[k]) end
  return out
end

local function trim_leading_space(inlines)
  while #inlines > 0 and (inlines[1].t == "Space" or inlines[1].t == "SoftBreak") do inlines:remove(1) end
  return inlines
end

-- the caption inlines of a bold span led by a label (nil when it is not one)
local function caption_of_label(strong)
  local inlines = strong.content
  local best = nil
  for k = 1, #inlines do
    local prefix = pandoc.utils.stringify(slice(inlines, 1, k))
    if not is_label(prefix) then break end
    best = k
    local item = inlines[k]
    if item.t == "Str" and fold(item.text):match("[%.:%)%-]$") then break end
  end
  if best == nil then
    -- no label word: a bold line is a caption only when the setting says the label is not needed
    if need_label then return nil end
    return pandoc.Inlines(inlines)
  end
  local rest = trim_leading_space(slice(inlines, best + 1, #inlines))
  if #rest == 0 then return nil end
  if label_mode == "keep" then return pandoc.Inlines(inlines) end
  return rest
end

-- (caption inlines, identifier) of a paragraph that reads like a caption, or nil
local function candidate(block)
  if block.t ~= "Para" then return nil end
  local inlines = pandoc.Inlines(block.content)
  local id = nil
  local last = inlines[#inlines]
  if last ~= nil and last.t == "Str" then
    local found = last.text:match("^{#([^}%s]+)}$")
    if found then
      id = found
      inlines:remove(#inlines)
      while #inlines > 0 and inlines[#inlines].t == "Space" do inlines:remove(#inlines) end
    end
  end
  if #inlines == 1 and inlines[1].t == "Strong" then
    local caption = caption_of_label(inlines[1])
    if caption then return caption, id end
    return nil
  end
  if colon_words > 0 and #inlines >= 3 and inlines[1].t == "Str" and inlines[1].text == ":" and inlines[2].t == "Space" then
    local rest = slice(inlines, 3, #inlines)
    local count = 0
    for _ in pandoc.utils.stringify(rest):gmatch("%S+") do count = count + 1 end
    if count >= 1 and count <= colon_words then return rest, id end
  end
  return nil
end

local function bare(table_block)
  return table_block.t == "Table" and #table_block.caption.long == 0 and (table_block.caption.short == nil or #table_block.caption.short == 0)
end

local function give(table_block, caption, id)
  local held = table_block.caption
  held.long = pandoc.Blocks{pandoc.Plain(caption)}
  table_block.caption = held
  if id and (table_block.identifier == nil or table_block.identifier == "") then table_block.identifier = id end
  return table_block
end

local function note(caption, source)
  noted = noted + 1
  if first_example == nil then
    local shown = pandoc.utils.stringify(source)
    if text.len(shown) > 48 then shown = text.sub(shown, 1, 45) .. "..." end
    first_example = shown
  end
end

local function process(blocks)
  local out = pandoc.Blocks{}
  local i = 1
  local count = #blocks
  while i <= count do
    local block = blocks[i]
    local caption, id = candidate(block)
    local following = blocks[i + 1]
    local previous = out[#out]
    if caption and following ~= nil and bare(following) then
      if mode == "on" then
        out:insert(give(following, caption, id))
        i = i + 2
      else
        note(caption, block)
        out:insert(block)
        i = i + 1
      end
    elseif caption and previous ~= nil and bare(previous) then
      if mode == "on" then
        out[#out] = give(previous, caption, id)
      else
        note(caption, block)
        out:insert(block)
      end
      i = i + 1
    else
      out:insert(block)
      i = i + 1
    end
  end
  return out
end

function Pandoc(doc)
  local meta = doc.meta
  mode = setting(meta, "pdfmd-table-captions") or "note"
  label_mode = setting(meta, "pdfmd-table-caption-label") or "strip"
  need_label = (setting(meta, "pdfmd-table-caption-need-label") or "on") ~= "off"
  colon_words = tonumber(setting(meta, "pdfmd-table-caption-colon-words") or "0") or 0
  words = {}
  for word in (setting(meta, "pdfmd-table-caption-words") or "Table"):gmatch("[^,]+") do
    word = word:gsub("^%s+", ""):gsub("%s+$", "")
    if word ~= "" then words[#words + 1] = fold(text.lower(word)) end
  end
  -- the longest word first: "tabelle" must not lose to a shorter one that starts it
  table.sort(words, function(a, b) return #a > #b end)
  for _, key in ipairs({"pdfmd-table-captions", "pdfmd-table-caption-label", "pdfmd-table-caption-colon-words",
                        "pdfmd-table-caption-words", "pdfmd-table-caption-need-label"}) do
    doc.meta[key] = nil
  end
  if mode == "off" then return doc end
  local walked = doc:walk({ Blocks = process })
  if mode ~= "on" and noted > 0 then
    io.stderr:write(string.format(
      "NOTE  table-captions: %d line%s next to a table read%s like %s (first: \"%s\"); pdfmd-options: table-captions: on makes %s the caption, off ends this note\n",
      noted, noted == 1 and "" or "s", noted == 1 and "s" or "", noted == 1 and "a caption" or "captions", first_example,
      noted == 1 and "it" or "them"))
  end
  return walked
end

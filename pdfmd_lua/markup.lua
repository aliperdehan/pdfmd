-- pdfmd: universal markup (v3.29.13). Spellings that Markdown dialects, GitHub, Obsidian and Quarto share but Pandoc does not know,
-- carried into every writer as that writer's own. Off unless asked, one kind at a time (`pdfmd-options: markup: [callouts, ...]`,
-- `--markup`); pdfmd gives the kinds that take part as `-M pdfmd-markup=callouts,...` (run by hand without it, every kind does).
--
-- callouts   > [!NOTE]  > [!warning] A title  > [!tip]-   (GitHub, Obsidian: a block quote that starts with the marker);
--            ::: note  ::: {.warning title="Careful"}  ::: callout-tip  (a fenced div; Quarto's title is its first heading)
--            -> LaTeX a box (pdfmd's header file defines the pdfmdcallout environment: tcolorbox when installed, else a quote),
--            Typst a tinted block, HTML/EPUB a div.callout with its style, every other writer a block quote with a bold title.
-- toc        a paragraph that is [TOC], [[TOC]] or [[_TOC_]], <!-- toc -->, or a raw \tableofcontents (for the writers that are
--            not LaTeX): the table of contents where it stands. LaTeX \tableofcontents, Typst #outline(), Word a TOC field
--            (Word asks to update it when the file is opened), every other writer a list of links to the headings (to level 3).
-- center     <center>...</center>, <div align="center">, <div style="text-align: center">, ::: center, and a raw \begin{center}...
--            \end{center} (for the writers that are not LaTeX): LaTeX the center environment, Typst #align(center)[...], HTML and
--            EPUB a text-align div. Word and OpenDocument keep the text as it is and say so once (they have no centring to give a block).
-- highlight  ==marked text==, and <mark> where the reader keeps it: LaTeX \pdfmdhl{...} (soul's \hl; pdfmd's header file defines it),
--            Typst #highlight[...], HTML, EPUB and Markdown <mark>...</mark>; Word and OpenDocument keep the text, with a note once.
local enabled = nil
local function on(kind)
  return enabled == nil or enabled[kind] == true
end

local CALLOUT = {
  note = "note", tip = "tip", important = "important", warning = "warning", caution = "caution",
  info = "note", abstract = "note", summary = "note", tldr = "note", todo = "note", example = "note",
  success = "tip", check = "tip", done = "tip", hint = "tip",
  question = "important", help = "important", faq = "important",
  attention = "warning",
  failure = "caution", fail = "caution", missing = "caution", danger = "caution", error = "caution", bug = "caution",
}
local TITLE = {note = "Note", tip = "Tip", important = "Important", warning = "Warning", caution = "Caution"}
local EDGE = {note = "0969DA", tip = "1A7F37", important = "8250DF", warning = "9A6700", caution = "CF222E"}
local TINT = {note = "EEF5FD", tip = "EDF7F0", important = "F4EFFC", warning = "FBF4E3", caution = "FDEEEF"}

local CALLOUT_CSS = "<style>\n.callout { margin: 1em 0; padding: .5em 1em; border-left: 4px solid #888; break-inside: avoid; }\n"
  .. ".callout > p:first-child { margin-top: 0; } .callout > p:last-child { margin-bottom: 0; }\n"
  .. ".callout-title { font-weight: bold; }\n"
do
  for kind, edge in pairs(EDGE) do
    CALLOUT_CSS = CALLOUT_CSS .. ".callout-" .. kind .. " { border-left-color: #" .. edge .. "; background: #" .. TINT[kind] .. "; }\n"
  end
  CALLOUT_CSS = CALLOUT_CSS .. "</style>"
end

local function is_break(inline)
  return inline.t == "SoftBreak" or inline.t == "LineBreak"
end

-- (kind, title inlines or nil, body blocks) of a block quote that starts with [!KIND], else nil
local function callout_of_quote(quote)
  local first = quote.content[1]
  if not first or (first.t ~= "Para" and first.t ~= "Plain") then return nil end
  local head = first.content[1]
  if not head or head.t ~= "Str" then return nil end
  local word = head.text:match("^%[!([%w_%-]+)%]%s*[%-%+]?$")
  if not word then return nil end
  local kind = CALLOUT[word:lower()] or "note"
  local title, index = pandoc.Inlines({}), 2
  while first.content[index] and first.content[index].t == "Space" do index = index + 1 end
  while first.content[index] and not is_break(first.content[index]) do
    title[#title + 1] = first.content[index]
    index = index + 1
  end
  if #title == 0 and not CALLOUT[word:lower()] then title = pandoc.Inlines({pandoc.Str(word)}) end
  index = index + 1
  local body = pandoc.Blocks({})
  if first.content[index] then
    local rest = pandoc.Inlines({})
    for position = index, #first.content do rest[#rest + 1] = first.content[position] end
    body[#body + 1] = pandoc.Para(rest)
  end
  for position = 2, #quote.content do body[#body + 1] = quote.content[position] end
  return kind, (#title > 0 and title or nil), body
end

-- (kind, title inlines or nil, body blocks) of a div that is a callout, else nil
local function callout_of_div(div)
  local kind
  for _, class in ipairs(div.classes) do
    local name = class:lower():gsub("^callout%-", "")
    if CALLOUT[name] and (class:lower() == name or class:lower():match("^callout%-")) then kind = CALLOUT[name]; break end
  end
  if not kind then return nil end
  local title = div.attributes["title"]
  local body = pandoc.Blocks({})
  local blocks = div.content
  local first_block = 1
  if (title == nil or title == "") and blocks[1] and blocks[1].t == "Header" then
    title = blocks[1].content
    first_block = 2
  end
  for position = first_block, #blocks do body[#body + 1] = blocks[position] end
  if type(title) == "string" then title = (title ~= "") and pandoc.Inlines({pandoc.Str(title)}) or nil end
  return kind, title, body
end

local function make_callout(kind, title, body)
  local format = FORMAT or ""
  local heading = pandoc.Para({pandoc.Strong(title or pandoc.Inlines({pandoc.Str(TITLE[kind])}))})
  local out = pandoc.Blocks({})
  if format:match("^latex") then
    out[#out + 1] = pandoc.RawBlock("latex", "\\begin{pdfmdcallout}{pdfmd-" .. kind .. "}")
    out[#out + 1] = heading
    out:extend(body)
    out[#out + 1] = pandoc.RawBlock("latex", "\\end{pdfmdcallout}")
  elseif format:match("^typst") then
    out[#out + 1] = pandoc.RawBlock("typst", '#block(width: 100%, inset: 8pt, radius: 2pt, fill: rgb("#' .. EDGE[kind]
      .. '").lighten(92%), stroke: (left: 2pt + rgb("#' .. EDGE[kind] .. '")))[')
    out[#out + 1] = heading
    out:extend(body)
    out[#out + 1] = pandoc.RawBlock("typst", "]")
  elseif format:match("^html") or format:match("^epub") then
    local inner = pandoc.Blocks({pandoc.Div({heading}, pandoc.Attr("", {"callout-title"}))})
    inner:extend(body)
    out[#out + 1] = pandoc.Div(inner, pandoc.Attr("", {"callout", "callout-" .. kind}))
  else
    local inner = pandoc.Blocks({heading})
    inner:extend(body)
    out[#out + 1] = pandoc.BlockQuote(inner)
  end
  return out
end


-- ---- toc -------------------------------------------------------------------------------------------------------------
local TOC_DEPTH = 3

local function is_toc_marker(block)
  if block.t == "Para" or block.t == "Plain" then
    local text = pandoc.utils.stringify(block):gsub("%s+", ""):lower()
    return text == "[toc]" or text == "[[toc]]" or text == "[[_toc_]]" or text == "[_toc_]" or text == "{:toc}"
  elseif block.t == "RawBlock" then
    local format = block.format:lower()
    local text = block.text:gsub("^%s+", ""):gsub("%s+$", "")
    if format == "html" or format == "html5" then
      local word = text:lower():match("^<!%-%-%s*(%a+)%s*%-%->$")
      return word == "toc"
    elseif format == "tex" or format == "latex" then
      return text == "\\tableofcontents"
    end
  end
  return false
end

-- a nested bullet list of links to the headings of `headers` ({level, id, inlines})
local function toc_list(headers)
  local function build(index, level)
    local items = {}
    while index <= #headers and headers[index].level >= level do
      local header = headers[index]
      local item = pandoc.Blocks({pandoc.Plain({pandoc.Link(header.inlines, "#" .. header.id)})})
      index = index + 1
      if index <= #headers and headers[index].level > header.level then
        local nested
        nested, index = build(index, headers[index].level)
        item[#item + 1] = nested
      end
      items[#items + 1] = item
    end
    return pandoc.BulletList(items), index
  end
  local base = headers[1].level
  for _, header in ipairs(headers) do if header.level < base then base = header.level end end
  local list = build(1, base)
  return list
end

local function make_toc(headers)
  local format = FORMAT or ""
  if format:match("^latex") then
    return pandoc.Blocks({pandoc.RawBlock("latex", "\\tableofcontents")})
  elseif format:match("^typst") then
    return pandoc.Blocks({pandoc.RawBlock("typst", "#outline()")})
  elseif format:match("^docx") then
    return pandoc.Blocks({pandoc.RawBlock("openxml",
      '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-'
      .. TOC_DEPTH .. '" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>'
      .. 'Update this field to build the table of contents.</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')})
  end
  if #headers == 0 then return pandoc.Blocks({}) end
  return pandoc.Blocks({pandoc.Para({pandoc.Strong({pandoc.Str("Contents")})}), toc_list(headers)})
end


-- ---- center ----------------------------------------------------------------------------------------------------------
local center_told = false

local function make_center(blocks)
  local format = FORMAT or ""
  local out = pandoc.Blocks({})
  if format:match("^latex") then
    out[#out + 1] = pandoc.RawBlock("latex", "\\begin{center}")
    out:extend(blocks)
    out[#out + 1] = pandoc.RawBlock("latex", "\\end{center}")
  elseif format:match("^typst") then
    out[#out + 1] = pandoc.RawBlock("typst", "#align(center)[")
    out:extend(blocks)
    out[#out + 1] = pandoc.RawBlock("typst", "]")
  elseif format:match("^html") or format:match("^epub") then
    out[#out + 1] = pandoc.Div(blocks, pandoc.Attr("", {}, {{"style", "text-align: center"}}))
  else
    if not center_told and (format == "docx" or format == "odt" or format == "pptx") then
      center_told = true
      io.stderr:write("NOTE  markup: centring is not applied to " .. format .. "; the text is kept as it is\n")
    end
    out:extend(blocks)
  end
  return out
end

local function is_center_div(div)
  for _, class in ipairs(div.classes) do
    if class == "center" or class == "centered" or class == "centering" then return true end
  end
  if (div.attributes["align"] or ""):lower() == "center" then return true end
  return (div.attributes["style"] or ""):lower():match("text%-align%s*:%s*center") ~= nil
end

local function raw_is(block, format_pattern, text_pattern)
  if block.t ~= "RawBlock" then return false end
  local format = block.format:lower()
  if not format:match(format_pattern) then return false end
  return block.text:lower():gsub("^%s+", ""):gsub("%s+$", ""):match(text_pattern) ~= nil
end

-- the pairs <center> ... </center> (and \begin{center} ... \end{center} unless the writer is LaTeX) of one list of blocks
local function center_pairs(blocks)
  local latex = (FORMAT or ""):match("^latex") ~= nil
  local out, changed, index = pandoc.Blocks({}), false, 1
  while index <= #blocks do
    local block = blocks[index]
    local close_pattern
    if raw_is(block, "^html", "^<center>$") then close_pattern = {"^html", "^</center>$"}
    elseif not latex and raw_is(block, "^te?x?$", "^\\begin{center}$") then close_pattern = {"^te?x?$", "^\\end{center}$"}
    elseif not latex and raw_is(block, "^latex$", "^\\begin{center}$") then close_pattern = {"^latex$", "^\\end{center}$"} end
    local last
    if not latex and block.t == "RawBlock" and (block.format:lower() == "tex" or block.format:lower() == "latex") then
      -- the reader keeps a whole \begin{center} ... \end{center} as one raw block: its text is read as Markdown
      local inner_text = block.text:match("^%s*\\begin{center}(.-)\\end{center}%s*$")
      if inner_text then
        out:extend(make_center(pandoc.read(inner_text, "markdown").blocks))
        index, changed = index + 1, true
        goto continue
      end
    end
    if close_pattern then
      for position = index + 1, #blocks do
        if raw_is(blocks[position], close_pattern[1], close_pattern[2]) then last = position; break end
      end
    end
    if last then
      local inner = pandoc.Blocks({})
      for position = index + 1, last - 1 do inner[#inner + 1] = blocks[position] end
      out:extend(make_center(inner))
      index, changed = last + 1, true
    else
      out[#out + 1] = block
      index = index + 1
    end
    ::continue::
  end
  if changed then return out end
  return nil
end


-- ---- highlight -------------------------------------------------------------------------------------------------------
local highlight_told = false

local function marked(inlines)
  local format = FORMAT or ""
  local out = pandoc.Inlines({})
  if format:match("^latex") then
    out[#out + 1] = pandoc.RawInline("latex", "\\pdfmdhl{")
    out:extend(inlines)
    out[#out + 1] = pandoc.RawInline("latex", "}")
  elseif format:match("^typst") then
    out[#out + 1] = pandoc.RawInline("typst", "#highlight[")
    out:extend(inlines)
    out[#out + 1] = pandoc.RawInline("typst", "]")
  elseif format:match("^html") or format:match("^epub") or format:match("markdown") or format:match("^gfm")
      or format:match("^commonmark") then
    out[#out + 1] = pandoc.RawInline("html", "<mark>")
    out:extend(inlines)
    out[#out + 1] = pandoc.RawInline("html", "</mark>")
  else
    if not highlight_told and (format == "docx" or format == "odt" or format == "pptx") then
      highlight_told = true
      io.stderr:write("NOTE  markup: highlighting is not applied to " .. format .. "; the text is kept as it is\n")
    end
    out:extend(inlines)
  end
  return out
end

-- ==text== across the Str and Space elements of one list of inlines (Pandoc splits "==a b==" into "==a", Space, "b==")
local function highlight_runs(inlines)
  local out, changed, index = pandoc.Inlines({}), false, 1
  while index <= #inlines do
    local item = inlines[index]
    local done = false
    if item.t == "Str" and item.text:match("^==[^=]") then
      local last
      for position = index, #inlines do
        local other = inlines[position]
        if other.t == "Str" and other.text:match("[^=]==%p*$") and (position > index or item.text:match("^==.+[^=]==%p*$")) then
          last = position
          break
        end
        if other.t ~= "Str" and other.t ~= "Space" and other.t ~= "Emph" and other.t ~= "Strong" and other.t ~= "Code"
            and other.t ~= "Link" and other.t ~= "SoftBreak" and other.t ~= "Quoted" and other.t ~= "Span" then
          break
        end
      end
      if last then
        local inner = pandoc.Inlines({})
        for position = index, last do inner[#inner + 1] = inlines[position] end
        local tail = ""
        inner[1] = pandoc.Str(inner[1].text:gsub("^==", ""))
        local final = inner[#inner]
        local body, punct = final.text:match("^(.-)==(%p*)$")
        inner[#inner] = pandoc.Str(body)
        tail = punct or ""
        local cleaned = pandoc.Inlines({})
        for _, part in ipairs(inner) do
          if not (part.t == "Str" and part.text == "") then cleaned[#cleaned + 1] = part end
        end
        out:extend(marked(cleaned))
        if tail ~= "" then out[#out + 1] = pandoc.Str(tail) end
        index, changed, done = last + 1, true, true
      end
    end
    if not done then
      out[#out + 1] = item
      index = index + 1
    end
  end
  if changed then return out end
  return nil
end

function Pandoc(doc)
  local enabled_list = doc.meta["pdfmd-markup"]
  if enabled_list ~= nil then
    enabled = {}
    for word in pandoc.utils.stringify(enabled_list):gmatch("[%w_%-]+") do enabled[word] = true end
  end
  local used = {callouts = false}
  local walked = doc:walk({
    BlockQuote = function(quote)
      if not on("callouts") then return nil end
      local kind, title, body = callout_of_quote(quote)
      if not kind then return nil end
      used.callouts = true
      return make_callout(kind, title, body)
    end,
    Inlines = function(inlines)
      if not on("highlight") or (FORMAT or ""):match("^markdown") then return nil end
      return highlight_runs(inlines)
    end,
    Span = function(span)
      -- Pandoc 3.12 with +mark (or a Span written by hand) keeps the class: <mark> in HTML-like writers, the writer's own elsewhere
      if on("highlight") and #span.classes == 1 and span.classes[1] == "mark" and #span.attributes == 0 and span.identifier == "" then
        return marked(span.content)
      end
    end,
    Blocks = function(blocks)
      if not on("center") then return nil end
      return center_pairs(blocks)
    end,
    Div = function(div)
      if on("center") and is_center_div(div) then
        return make_center(div.content)
      end
      if not on("callouts") then return nil end
      local kind, title, body = callout_of_div(div)
      if not kind then return nil end
      used.callouts = true
      return make_callout(kind, title, body)
    end,
  })
  if on("toc") then
    local headers = {}
    walked:walk({Header = function(header)
      if header.level <= TOC_DEPTH and header.identifier ~= "" then
        headers[#headers + 1] = {level = header.level, id = header.identifier, inlines = header.content}
      end
    end})
    local blocks = pandoc.Blocks({})
    for _, block in ipairs(walked.blocks) do
      if is_toc_marker(block) and not (block.t == "RawBlock" and (FORMAT or ""):match("^latex") and block.format:match("tex")) then
        blocks:extend(make_toc(headers))
      else
        blocks[#blocks + 1] = block
      end
    end
    walked.blocks = blocks
  end
  local format = FORMAT or ""
  if used.callouts and (format:match("^html") or format:match("^epub")) then
    local before = walked.meta["include-before"]
    local style = pandoc.MetaBlocks({pandoc.RawBlock("html", CALLOUT_CSS)})
    if before == nil then
      walked.meta["include-before"] = pandoc.MetaList({style})
    elseif before.t == "MetaList" then
      before[#before + 1] = style
      walked.meta["include-before"] = before
    else
      walked.meta["include-before"] = pandoc.MetaList({before, style})
    end
  end
  return walked
end

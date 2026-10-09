-- pdfmd: ASCII text (v3.26.8). `--to ascii` makes a text output with no character above 127. The words go through
-- pdfmd_flat/asciify.py *before* the writer sees them, so the writer escapes what the ASCII spelling needs: a dash that
-- becomes `-` at a line's start is not taken for a list, `>=` for a quotation, `*` for emphasis, and a table's columns
-- are measured on the ASCII text.
--
-- The filter collects every piece of text that holds a character above 127 (words, inline code, code blocks, math, link
-- and image titles), sends them in one go to `pdfmd --ascii-stdio` (a Python process: the tables, Greek, Cyrillic, the
-- romanization packs) and puts the answers back; TeX math is sent as TeX (\alpha, \geq), a link's address has its non-ASCII
-- bytes percent-encoded. What the writer itself makes (Pandoc's plain writer sets math in Unicode, `E = mc²`, and a
-- writer with smart typography writes the quotes and dashes of the text) is mapped afterwards by pdfmd, on the file.
--
-- Configuration arrives as metadata written by pdfmd: `pdfmd-ascii` = {command, script, missing, report, smart}.

local config = nil

local function read_config(meta)
  local setting = meta["pdfmd-ascii"]
  if type(setting) ~= "table" then return false end
  config = {
    command = pandoc.utils.stringify(setting.command),
    script = pandoc.utils.stringify(setting.script),
    missing = pandoc.utils.stringify(setting.missing or "question"),
    report = pandoc.utils.stringify(setting.report or ""),
    smart = pandoc.utils.stringify(setting.smart or "all"),
  }
  return true
end

local function has_unicode(text)
  return text ~= nil and text:find("[\128-\255]") ~= nil
end

local function percent_encoded(text)
  return (text:gsub("[\128-\255]", function(byte) return string.format("%%%02X", byte:byte()) end))
end

-- a link flat text wrote after its words (`<https://example.org/é>`) is an address: percent-encoded, not transliterated
local function is_address(text)
  return text:match("^<%a[%w+.-]*:[^%s>]*>$") ~= nil
end

local function collect(doc)
  local seen, list = {}, {}
  local function note(text, prefix)
    local key = (prefix or "") .. (text or "")
    if has_unicode(text) and not seen[key] then
      seen[key] = true
      list[#list + 1] = key
    end
  end
  doc:walk({
    Str = function(item) if not is_address(item.text) then note(item.text) end end,
    Code = function(item) note(item.text) end,
    CodeBlock = function(item) note(item.text) end,
    Math = function(item) note(item.text, "\1") end,
    Link = function(item) note(item.title) end,
    Image = function(item) note(item.title) end,
  })
  return list
end

local function split(text, count)
  local pieces, from = {}, 1
  while true do
    local at = text:find("\0", from, true)
    if not at then pieces[#pieces + 1] = text:sub(from) break end
    pieces[#pieces + 1] = text:sub(from, at - 1)
    from = at + 1
  end
  if #pieces ~= count then return nil end
  return pieces
end

local function asciify(doc)
  if not read_config(doc.meta) then return nil end
  local list = collect(doc)
  local answers = {}
  if #list > 0 then
    local ok, result = pcall(pandoc.pipe, config.command, {config.script, "--ascii-stdio", config.missing, config.report, config.smart},
                             table.concat(list, "\0"))
    local pieces = ok and split(result, #list) or nil
    if not pieces then
      io.stderr:write("WARN  ascii: the transliteration helper did not answer; the text is mapped on the written file instead\n")
    else
      for index, text in ipairs(list) do answers[text] = pieces[index] end
    end
  end
  local function mapped(text, prefix)
    return answers[(prefix or "") .. (text or "")]
  end
  local function encoded(target)
    if not has_unicode(target) then return nil end
    return percent_encoded(target)
  end
  return doc:walk({
    Str = function(item)
      if is_address(item.text) then
        if has_unicode(item.text) then return pandoc.Str(percent_encoded(item.text)) end
        return nil
      end
      local text = mapped(item.text)
      if text and text ~= item.text then return pandoc.Str(text) end
    end,
    Code = function(item)
      local text = mapped(item.text)
      if text and text ~= item.text then item.text = text return item end
    end,
    CodeBlock = function(item)
      local text = mapped(item.text)
      if text and text ~= item.text then item.text = text return item end
    end,
    Math = function(item)
      local text = mapped(item.text, "\1")
      if text and text ~= item.text then return pandoc.Math(item.mathtype, text) end
    end,
    Link = function(item)
      local text, address = mapped(item.title), encoded(item.target)
      if (text and text ~= item.title) or address then
        if text then item.title = text end
        if address then item.target = address end
        return item
      end
    end,
    Image = function(item)
      local text, address = mapped(item.title), encoded(item.src)
      if (text and text ~= item.title) or address then
        if text then item.title = text end
        if address then item.src = address end
        return item
      end
    end,
  })
end

return {{Pandoc = asciify}}

-- The private record never reaches Pandoc. This file's temporary sibling
-- contains only citation fields and the settings needed to apply them.
local file = assert(io.open(PANDOC_SCRIPT_FILE .. ".json", "rb"))
local config = pandoc.json.decode(file:read("*a"))
file:close()

local references = {fig = true, tbl = true, eq = true, sec = true, lst = true}
local seen, missing = {}, 0
local smart = false
for _, extension in ipairs(PANDOC_READER_OPTIONS.extensions or {}) do
  if extension == "smart" then smart = true; break end
end

local function warn(message)
  if not seen[message] then
    io.stderr:write("WARN  ", message, "\n")
    seen[message] = true
  end
end

local function canonical(id, key)
  if key then return "@" .. key .. "#" .. id end
  return "@" .. config.prefix .. ":" .. id
end

local function resolve(citation)
  local key = citation.id
  if references[key:match("^([^:]+):")] then return nil end
  local head, id = key:match("^(.+)[:#]([0-9]+)$")
  if not id then return nil end
  id = id:gsub("^0+", "")
  if id == "" then id = "0" end
  local named = nil
  if head ~= config.prefix then named = head end
  local record = config.records and config.records[id]
  local matches = record and (not named or named == record.key)
  if config.bibliography[key] then
    if matches then
      local first = canonical(id, named)
      local options = {first, record.key ~= "" and canonical(id, record.key) or first, canonical(id)}
      local suggestion = first
      for _, alternative in ipairs(options) do
        if not config.bibliography[alternative:sub(2)] then
          suggestion = alternative
          break
        end
      end
      warn("the bibliography has a key '" .. key .. "': it is used as a source, not as excerpt " .. id ..
        (named and " of " .. named or "") .. " (write " .. suggestion .. " for the excerpt)")
    end
    return nil
  end
  if not config.records then
    missing = missing + 1
    return nil
  end
  if not record then
    warn("excerpt " .. id .. " is not in excerpts.json")
    return nil
  end
  if not matches then
    warn("@" .. key .. ": excerpt " .. id .. " belongs to " ..
      (record.key ~= "" and record.key or "a remark without a source"))
    return nil
  end
  if record.remark and citation.mode == "AuthorInText" then
    warn("excerpt " .. id .. ": removed a narrative remark marker")
  elseif not record.remark and not config.bibliography[record.key] then
    warn("excerpt " .. id .. ": its key " .. record.key .. " is not in the bibliography")
  end
  return record
end

local roman_digits = {{1000, "M"}, {900, "CM"}, {500, "D"}, {400, "CD"}, {100, "C"}, {90, "XC"},
  {50, "L"}, {40, "XL"}, {10, "X"}, {9, "IX"}, {5, "V"}, {4, "IV"}, {1, "I"}}

local function roman(number)
  local out = {}
  for _, digit in ipairs(roman_digits) do
    local count = math.floor(number / digit[1])
    out[#out + 1] = digit[2]:rep(count)
    number = number % digit[1]
  end
  return table.concat(out)
end

local function numbered_page(label)
  local prefix, digits = label:match("^(.-)([0-9]+)$")
  if digits then
    local number = tonumber(digits)
    if math.type(number) ~= "integer" then return nil end
    local width = digits:find("^0") and #digits or 0
    return "digits:" .. width .. ":" .. prefix, number, function(value)
      local printed = tostring(value)
      return prefix .. ("0"):rep(math.max(0, width - #printed)) .. printed
    end
  end
  if not label:match("^[ivxlcdmIVXLCDM]+$") then return nil end
  local number, rest = 0, label:upper()
  for _, digit in ipairs(roman_digits) do
    while rest:sub(1, #digit[2]) == digit[2] do
      number = number + digit[1]
      rest = rest:sub(#digit[2] + 1)
    end
  end
  if roman(number) ~= label:upper() then return nil end
  if label == label:lower() then
    return "roman:lower", number, function(value) return roman(value):lower() end
  end
  return "roman:upper", number, roman
end

local function page_list(pages)
  local intervals, labels, seen_labels = {}, {}, {}
  for _, page in ipairs(pages) do
    for label in page:gmatch("[^,;]+") do
      label = label:match("^%s*(.-)%s*$")
      if label ~= "" and not seen_labels[label] then
        seen_labels[label] = true
        labels[#labels + 1] = label
      end
    end
  end
  if #labels < 2 then return labels[1] or "" end
  local family, printed
  for _, label in ipairs(labels) do
    local ascii = label:gsub("–", "-"):gsub("—", "-")
    local start, stop = ascii:match("^(.-)%s*%-+%s*(.-)$")
    local kind, first, format, last
    if start then
      kind, first, format = numbered_page(start)
      local other
      other, last = numbered_page(stop)
      if other ~= kind then kind = nil end
    end
    if not kind then
      kind, first, format = numbered_page(label)
      last = first
    end
    if not kind or (family and kind ~= family) then return nil end
    family, printed = kind, format
    intervals[#intervals + 1] = {math.min(first, last), math.max(first, last)}
  end
  table.sort(intervals, function(a, b) return a[1] < b[1] end)
  local joined, result = {}, {}
  for _, interval in ipairs(intervals) do
    local last = joined[#joined]
    if last and interval[1] <= last[2] + 1 then
      last[2] = math.max(last[2], interval[2])
    else
      joined[#joined + 1] = interval
    end
  end
  for _, interval in ipairs(joined) do
    result[#result + 1] = interval[1] == interval[2] and printed(interval[1]) or
      printed(interval[1]) .. "--" .. printed(interval[2])
  end
  return table.concat(result, ", ")
end

local function append_string(inlines, text)
  local first = true
  for word in text:gmatch("%S+") do
    if not first then inlines:insert(pandoc.Space()) end
    if smart then word = word:gsub("%-%-%-", "—"):gsub("%-%-", "–") end
    inlines:insert(pandoc.Str(word))
    first = false
  end
end

local function strip_separator(inlines)
  local stripped = pandoc.List()
  local initial = true
  for _, item in ipairs(inlines) do
    if not initial or not (item.t == "Space" or item.t == "SoftBreak" or (item.t == "Str" and item.text == ",")) then
      stripped:insert(item)
      initial = false
    end
  end
  return stripped
end

local function suffix(citation, record, page, literal)
  local original = citation.suffix
  local typed = pandoc.text.lower(pandoc.utils.stringify(original):gsub(" ", " "):gsub("^[,%s]+", ""))
  if typed:match("^[0-9]") then return original end
  for _, term in ipairs(config.locator_terms) do
    term = pandoc.text.lower(term)
    if typed == term or typed:sub(1, #term + 1) == term .. " " then return original end
  end
  local locator = record.locator
  if locator == "" and page ~= "" then
    local plural = page:find("[,;]") or page:gsub("–", "-"):gsub("—", "-"):find("%S%s*%-+%s*%S")
    locator = literal and page or config.page_terms[plural and 2 or 1] .. " " .. page
  end
  if locator == "" then return original end
  local out = pandoc.List()
  if citation.mode ~= "AuthorInText" then out:insert(pandoc.Str(",")); out:insert(pandoc.Space()) end
  append_string(out, locator)
  local rest = strip_separator(original)
  if #rest > 0 then
    out:insert(pandoc.Str(","))
    out:insert(pandoc.Space())
    out:extend(rest)
  end
  return out
end

local function mergeable(citation, record)
  return record and not record.remark and record.locator == "" and
    #citation.prefix == 0 and #citation.suffix == 0
end

local function content(citations)
  local out = pandoc.List()
  local function str(value) out:insert(pandoc.Str(value)) end
  local function space() out:insert(pandoc.Space()) end
  for index, citation in ipairs(citations) do
    local narrative = index == 1 and citation.mode == "AuthorInText"
    if index == 1 and not narrative then str("[") end
    if index > 1 then str(";"); space() end
    if #citation.prefix > 0 then out:extend(citation.prefix); space() end
    str((citation.mode == "SuppressAuthor" and "-" or "") .. "@" .. citation.id)
    if #citation.suffix > 0 then
      if narrative then
        space(); str("["); out:extend(strip_separator(citation.suffix)); str("]")
      else
        out:extend(citation.suffix)
      end
    end
  end
  if citations[1].mode ~= "AuthorInText" then str("]") end
  return out
end

local function rewrite(el)
  local citations, resolved = el.citations, {}
  local changed = false
  for index, citation in ipairs(citations) do
    resolved[index] = resolve(citation)
    if resolved[index] then changed = true end
  end
  if not changed then return el end
  local out, index, repeated = pandoc.List(), 1, nil
  while index <= #citations do
    local citation, record = citations[index], resolved[index]
    index = index + 1
    if not record then
      out:insert(citation)
    elseif not record.remark then
      local page = record.page
      if mergeable(citation, record) then
        local pages, following = {page}, index
        while index <= #citations and mergeable(citations[index], resolved[index]) and
            citations[index].mode == citation.mode and resolved[index].key == record.key do
          pages[#pages + 1] = resolved[index].page
          index = index + 1
        end
        if #pages > 1 then
          local merged = page_list(pages)
          if merged then page = merged else index = following end
        end
      end
      if config.repeat_brackets and citation.mode ~= "AuthorInText" and config.bibliography[record.key] then
        local words = strip_separator(suffix(citation, record, page, true))
        if #words > 0 then
          local literal = pandoc.List({pandoc.Str(config.repeat_brackets[1])})
          if #citation.prefix > 0 then literal:extend(citation.prefix); literal:insert(pandoc.Space()) end
          literal:extend(words)
          literal:insert(pandoc.Str(config.repeat_brackets[2]))
          repeated = pandoc.Span(literal, pandoc.Attr("", {"pagecite"}))
        end
      end
      citation.id = record.key
      citation.suffix = suffix(citation, record, page)
      out:insert(citation)
    end
  end
  if #out == 0 then return nil end
  local cite = pandoc.Cite(content(out), out)
  if repeated and #out == 1 then
    return pandoc.Span({cite, repeated}, pandoc.Attr("", {"pdfmd-excerpt-repeat"}))
  end
  return cite
end

local function repeat_candidate(item)
  return item.t == "Span" and item.classes:includes("pdfmd-excerpt-repeat") and
    #item.content == 2 and item.content[1].t == "Cite"
end

local function repeat_inlines(items, state)
  local out = pandoc.List()
  for _, item in ipairs(items) do
    local candidate = repeat_candidate(item)
    local cite = candidate and item.content[1] or item
    if cite.t == "Cite" then
      out:insert(candidate and cite.citations[1].id == state.key and item.content[2] or cite)
      for _, citation in ipairs(cite.citations) do
        if not references[citation.id:match("^([^:]+):")] then state.key = citation.id end
      end
    else
      if item.content and item.t ~= "Note" and item.t ~= "Image" then
        item.content = repeat_inlines(item.content, state)
      end
      out:insert(item)
    end
  end
  return out
end

local function inlines(items)
  local out, trim, changed = pandoc.List(), false, false
  for index, item in ipairs(items) do
    if item.t == "Cite" then
      local replacement = rewrite(item)
      if replacement then
        out:insert(replacement)
      else
        if items[index + 1] and items[index + 1].t == "Space" then
          trim = true
        elseif #out > 0 and out[#out].t == "Space" then
          out:remove()
        end
      end
      if replacement ~= item then changed = true end
    elseif trim and item.t == "Space" then
      trim = false
    else
      out:insert(item)
      trim = false
    end
  end
  if changed then return out end
end

function Pandoc(doc)
  local result = doc:walk({Inlines = inlines})
  if config.repeat_brackets then
    local function block(el)
      el.content = repeat_inlines(el.content, {})
      return el
    end
    result = result:walk({Para = block, Plain = block})
    -- Citations in other contexts (e.g. nocite or a heading) keep their ordinary form.
    result = result:walk({Span = function(el)
      if repeat_candidate(el) then return el.content[1] end
    end})
  end
  if missing > 0 and config.missing then
    warn(tostring(missing) .. " excerpt marker" .. (missing == 1 and "" or "s") ..
      " but no excerpts.json (looked in " .. config.missing .. ")")
  end
  return result
end

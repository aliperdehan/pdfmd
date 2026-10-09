local DEFAULT_MAX_ROWS = 10
local DEFAULT_MAX_COLS = 7

local function parse_csv_line(line, delim)
  local fields = {}
  local field = {}
  local in_quotes = false
  local i = 1
  local n = #line
  while i <= n do
    local c = line:sub(i, i)
    if in_quotes then
      if c == '"' then
        if line:sub(i + 1, i + 1) == '"' then
          table.insert(field, '"')
          i = i + 1
        else
          in_quotes = false
        end
      else
        table.insert(field, c)
      end
    else
      if c == '"' then
        in_quotes = true
      elseif c == delim then
        table.insert(fields, table.concat(field))
        field = {}
      else
        table.insert(field, c)
      end
    end
    i = i + 1
  end
  table.insert(fields, table.concat(field))
  return fields
end

local function limit_or_all(value, default)
  if value == nil or value == "" then return default end
  if value:lower() == "all" then return math.huge end
  return tonumber(value) or default
end

local function escape_cell(text)
  text = (text or ""):gsub("\r", ""):gsub("\n", " ")
  -- A leading/trailing "|" (already escaped) still needs the pipe-table
  -- delimiter itself escaped; a literal backslash is left alone, unlike
  -- a general Markdown escaper, since a CSV cell's own backslashes (a
  -- Windows path, a regex) should render as typed, not be mistaken for
  -- Markdown escape sequences. Wrapped in parens: string.gsub returns
  -- TWO values (the string, and a count of substitutions made), and a
  -- bare `return text:gsub(...)` -- as the LAST argument to a later
  -- table.insert(escaped, escape_cell(...)) call -- leaks that count as
  -- a second, unwanted argument, which table.insert then misreads as
  -- its own `pos` parameter. Caught directly, as a real Lua runtime
  -- error ("bad argument #2 to 'insert' (number expected, got
  -- string)"), the first time this filter ran against an actual CSV.
  return (text:gsub("|", "\\|"))
end

-- the attribute block at the end of a caption, `{#tbl:id .class key=value}`, as (identifier, classes, pairs);
-- the inlines without it
local function split_attributes(inlines)
  local copy = {}
  for i, inline in ipairs(inlines) do copy[i] = inline end
  local last = copy[#copy]
  if last and last.t == "Str" then
    local inner = last.text:match("^{(.*)}$")
    if inner and inner:match("^%s*[#%.]") then
      local identifier, classes, pairs_ = "", {}, {}
      for token in inner:gmatch("%S+") do
        local id = token:match("^#(.+)$")
        local class = token:match("^%.(.+)$")
        local key, value = token:match('^([%w_%-]+)="?([^"]*)"?$')
        if id then identifier = id
        elseif class then classes[#classes + 1] = class
        elseif key then pairs_[#pairs_ + 1] = {key, value} end
      end
      table.remove(copy)
      while #copy > 0 and (copy[#copy].t == "Space" or copy[#copy].t == "SoftBreak") do table.remove(copy) end
      return identifier, classes, pairs_, copy
    end
  end
  return "", {}, {}, copy
end

local function inlines_of_text(text, reader)
  local ok, doc = pcall(pandoc.read, text, reader)
  if ok and doc.blocks[1] and (doc.blocks[1].t == "Para" or doc.blocks[1].t == "Plain") then return doc.blocks[1].content end
  return {pandoc.Str(text)}
end

-- `: Caption` or `Table: Caption` right after the block: the pipe-table caption syntax, which Pandoc's reader cannot
-- attach to a table that does not exist yet when it reads the text
local function caption_paragraph(block)
  if not block or (block.t ~= "Para" and block.t ~= "Plain") then return nil end
  local first, second = block.content[1], block.content[2]
  if not first or first.t ~= "Str" then return nil end
  local rest
  if first.text == ":" and second and second.t == "Space" then rest = 3
  elseif first.text == "Table:" and second and second.t == "Space" then rest = 3
  else return nil end
  local out = {}
  for i = rest, #block.content do out[#out + 1] = block.content[i] end
  return out
end

local function csv_blocks(div)
  local path = div.attributes["file"]
  if not path then
    io.stderr:write("WARN  .csv div has no file= attribute; leaving it empty\n")
    return {}
  end
  -- Pandoc runs in the folder of the document's metadata file, so a relative name is tried as given, then beside the
  -- document, then along the resource path
  local file = io.open(path, "r")
  if not file and not path:match("^/") and not path:match("^%a:[\\/]") then
    local candidates = {}
    for _, input in ipairs(PANDOC_STATE.input_files or {}) do
      local folder = input:match("^(.*)[/\\][^/\\]*$")
      if folder then candidates[#candidates + 1] = folder .. "/" .. path end
    end
    for _, folder in ipairs(PANDOC_STATE.resource_path or {}) do candidates[#candidates + 1] = folder .. "/" .. path end
    for _, candidate in ipairs(candidates) do
      file = io.open(candidate, "r")
      if file then break end
    end
  end
  if not file then
    io.stderr:write("WARN  .csv: could not open '" .. path .. "'; leaving it empty\n")
    return {}
  end

  local delim = div.attributes["delimiter"]
  if delim == nil or delim == "" then
    delim = path:match("%.tsv$") and "\t" or ","
  end
  local max_rows = limit_or_all(div.attributes["rows"], DEFAULT_MAX_ROWS)
  local max_cols = limit_or_all(div.attributes["cols"], DEFAULT_MAX_COLS)
  local has_header = div.attributes["header"] ~= "false"
  -- cells are read as Pandoc's own Markdown (H~2~O, $x^2$, [@key], \ce{...}); reader="gfm" restores plain GFM
  local reader = div.attributes["reader"]
  if reader == nil or reader == "" then reader = "markdown" end

  local header_fields = nil
  local data_rows = {}
  local total_data_rows = 0
  local total_cols = 0
  local rows_truncated = false
  local cols_truncated = false

  for line in file:lines() do
    line = line:gsub("\r$", "")
    if line ~= "" then
      local fields = parse_csv_line(line, delim)
      if #fields > total_cols then total_cols = #fields end
      if #fields > max_cols then
        cols_truncated = true
        local kept = {}
        for i = 1, max_cols do kept[i] = fields[i] end
        fields = kept
      end
      if has_header and header_fields == nil then
        header_fields = fields
      else
        total_data_rows = total_data_rows + 1
        if #data_rows < max_rows then
          table.insert(data_rows, fields)
        else
          rows_truncated = true
        end
      end
    end
  end
  file:close()

  local shown_cols = math.min(total_cols, max_cols)
  if not header_fields then
    header_fields = {}
    for i = 1, math.max(shown_cols, 1) do
      header_fields[i] = "Column " .. i
    end
  end

  local lines = {}
  local function emit_row(fields)
    local escaped = {}
    for i = 1, #header_fields do
      table.insert(escaped, escape_cell(fields[i]))
    end
    table.insert(lines, "| " .. table.concat(escaped, " | ") .. " |")
  end
  emit_row(header_fields)
  table.insert(lines, "|" .. string.rep(" --- |", #header_fields))
  for _, row in ipairs(data_rows) do
    emit_row(row)
  end

  -- Trailing blank line required: confirmed directly (a real generated
  -- table's last row rendered as a stray, unparsed Str/Space paragraph
  -- instead of the table's own last row) that pandoc.read(), called from
  -- inside a Lua filter, needs one to correctly close out a pipe table's
  -- final row -- pandoc's own CLI reading the identical text from a file
  -- does not need this, so this is specifically a pandoc.read()-from-a-
  -- filter quirk, not a general GFM pipe-table requirement.
  local parsed = pandoc.read(table.concat(lines, "\n") .. "\n\n", reader)
  local blocks = parsed.blocks

  if rows_truncated or cols_truncated then
    local shown_rows = #data_rows
    local note = string.format(
      "*(showing %d of %d row%s, %d of %d column%s -- use `rows=all`/`cols=all`, or " ..
      "`rows=N`/`cols=N`, on this `.csv` div to include more)*",
      shown_rows, total_data_rows, total_data_rows == 1 and "" or "s",
      shown_cols, total_cols, total_cols == 1 and "" or "s")
    for _, block in ipairs(pandoc.read(note .. "\n", "markdown").blocks) do blocks[#blocks + 1] = block end
    io.stderr:write("WARN  " .. path .. ": showing " .. shown_rows .. " of " ..
                     total_data_rows .. " row(s), " .. shown_cols .. " of " ..
                     total_cols .. " column(s) -- see the note under the table\n")
  end
  return blocks, reader
end

-- the table (first Table of `blocks`) gets its caption, identifier and attributes
local function attach_caption(blocks, inlines, div)
  local identifier, classes, pairs_, words = split_attributes(inlines)
  for _, block in ipairs(blocks) do
    if block.t == "Table" then
      if #words > 0 then block.caption = pandoc.Caption({pandoc.Plain(words)}) end
      if identifier == "" then identifier = div.identifier end
      if identifier ~= "" or #classes > 0 or #pairs_ > 0 then block.attr = pandoc.Attr(identifier, classes, pairs_) end
      return
    end
  end
end

function Blocks(blocks)
  local out, changed, i = {}, false, 1
  while i <= #blocks do
    local block = blocks[i]
    if block.t == "Div" and block.classes:includes("csv") then
      changed = true
      local made, reader = csv_blocks(block)
      local text = block.attributes["caption"]
      local following
      if text and text ~= "" then
        following = inlines_of_text(text, reader or "markdown")
      else
        following = caption_paragraph(blocks[i + 1])
        if following then i = i + 1 end
      end
      if following then attach_caption(made, following, block)
      elseif block.identifier ~= "" then
        for _, item in ipairs(made) do
          if item.t == "Table" then item.attr = pandoc.Attr(block.identifier) break end
        end
      end
      for _, item in ipairs(made) do out[#out + 1] = item end
    else
      out[#out + 1] = block
    end
    i = i + 1
  end
  if changed then return out end
  return nil
end

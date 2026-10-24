-- Pandoc before 3.2 has no pandoc.Caption, no pandoc.TableBody: a caption is the table {long, short}, a body the table
-- {attr, body, head, row_head_columns}. These stand in, so this filter and a profile written for a newer Pandoc work.
if not pandoc.Caption then
  pandoc.Caption = function(long, short) return {long = long or {}, short = short} end
end
local DEFAULT_MAX_ROWS = 10

local DEFAULT_MAX_COLS = 7

-- For every table of the document (v3.27.2): pdfmd passes --csv-rows/--csv-cols or `pdfmd-options: {csv: ...}` as
-- `-M pdfmd-csv-rows=N|all`, `pdfmd-csv-cols`, `pdfmd-csv-header=false`, `pdfmd-csv-reader=gfm`, only when they differ
-- from the defaults; a div's own attributes still win. read_defaults (run first) takes them out of the metadata.
local defaults = {rows = nil, cols = nil, header = true, reader = "markdown", delimiter = "auto", cut = "ends", note = "short"}

-- The whole text at once (a quoted field may hold a line break, and inline data arrives as one string): rows of
-- fields, RFC 4180 quoting (a doubled `""` is a quote); blank lines are skipped.
local function parse_csv(text, delim)
  local rows, row, parts = {}, {}, {}
  local special = (delim:match("%w") and "[\"\r\n" .. delim .. "]") or ("[\"\r\n%" .. delim .. "]")
  local pos, n, in_quotes = 1, #text, false
  local function end_field()
    row[#row + 1] = table.concat(parts)
    parts = {}
  end
  local function end_row()
    end_field()
    if not (#row == 1 and row[1] == "") then rows[#rows + 1] = row end
    row = {}
  end
  while pos <= n do
    if in_quotes then
      local close = text:find('"', pos, true)
      if not close then
        parts[#parts + 1] = text:sub(pos)
        pos = n + 1
      else
        parts[#parts + 1] = text:sub(pos, close - 1)
        if text:sub(close + 1, close + 1) == '"' then
          parts[#parts + 1] = '"'
          pos = close + 2
        else
          in_quotes = false
          pos = close + 1
        end
      end
    else
      local at = text:find(special, pos)
      if not at then
        parts[#parts + 1] = text:sub(pos)
        pos = n + 1
      else
        parts[#parts + 1] = text:sub(pos, at - 1)
        local c = text:sub(at, at)
        if c == '"' then
          in_quotes = true
          pos = at + 1
        elseif c == delim then
          end_field()
          pos = at + 1
        else
          end_row()
          pos = (c == "\r" and text:sub(at + 1, at + 1) == "\n") and at + 2 or at + 1
        end
      end
    end
  end
  if #parts > 0 or #row > 0 then end_row() end
  return rows
end

-- no `delimiter=`: tab for `.tsv`, else whichever of , ; tab | the first line holds most of (outside quotes)
-- the delimiter a file's name promises: tab for .tsv/.tab, else a comma
local function extension_delimiter(path)
  if path and (path:lower():match("%.tsv$") or path:lower():match("%.tab$")) then return "\t" end
  return ","
end

-- v3.27.5: the one of , ; tab | that gives the first 20 records, parsed as CSV (quotes and line breaks inside them
-- count as they should), the same number of fields, more than one; the most fields win, the name's own delimiter wins
-- a tie. Failing that, the one the first line holds most of (the rule before 3.27.4), else the name's own.
local function guess_delimiter(text, path)
  local expected = extension_delimiter(path)
  local sample, cut = text, false
  if #sample > 65536 then                       -- a long file: its first 64 KB, whose last record may be cut short
    sample, cut = sample:sub(1, 65536), true
  end
  local candidates = {expected}
  for _, candidate in ipairs({",", ";", "\t", "|"}) do
    if candidate ~= expected then candidates[#candidates + 1] = candidate end
  end
  local best, best_fields = nil, 1
  for _, candidate in ipairs(candidates) do
    local records = parse_csv(sample, candidate)
    local count = math.min(#records, 20)
    if cut and count == #records and count > 1 then count = count - 1 end
    if count >= 1 then
      local fields = #records[1]
      local steady = fields > 1
      for i = 2, count do
        if #records[i] ~= fields then steady = false break end
      end
      if steady and fields > best_fields then best, best_fields = candidate, fields end
    end
  end
  if best then return best end
  local first = text:match("^[^\r\n]*") or ""
  local best_count = 0
  best = expected
  for _, candidate in ipairs(candidates) do
    local count, in_quotes = 0, false
    for i = 1, #first do
      local c = first:sub(i, i)
      if c == '"' then in_quotes = not in_quotes
      elseif c == candidate and not in_quotes then count = count + 1 end
    end
    if count > best_count then best, best_count = candidate, count end
  end
  return best
end

local DELIMITER_WORDS = {[","] = "comma", [";"] = "semicolon", ["\t"] = "tab", ["|"] = "pipe", [" "] = "space",
                         [":"] = "colon"}

-- which of n items stay under a cap: all of them, the first `cap` (cut "head"), or the first ones and the last
-- floor(sqrt(cap)) (cut "ends", the default since v3.27.4; v3.27.7: 7 + 3 of 10, 5 + 2 of 7, 16 + 4 of 20, 25 + 5 of
-- 30; a cap under 3 keeps the head only). Returns the kept indices, and how
-- many come from the head and the tail (both nil when nothing was cut).
local function keep_indices(n, cap, cut)
  local kept = {}
  if n <= cap then
    for i = 1, n do kept[#kept + 1] = i end
    return kept, nil, nil
  end
  local tail = 0
  if cut == "ends" and cap >= 3 then tail = math.floor(math.sqrt(math.floor(cap)) + 1e-9) end
  local head = cap - tail
  for i = 1, head do kept[#kept + 1] = i end
  for i = n - tail + 1, n do kept[#kept + 1] = i end
  return kept, head, tail
end

local GAP = "\u{2026}"     -- the cells standing for what was cut

local DELIMITER_NAMES = {comma = ",", semicolon = ";", tab = "\t", pipe = "|", space = " ", colon = ":"}

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

-- what a paragraph inside the div says, as the author typed it as far as the AST allows (a code block inside the
-- div is the faithful way to write data: nothing in it is read as Markdown)
local function text_of(inlines)
  local out = {}
  for _, inline in ipairs(inlines) do
    if inline.t == "Str" then out[#out + 1] = inline.text
    elseif inline.t == "Space" then out[#out + 1] = " "
    elseif inline.t == "SoftBreak" or inline.t == "LineBreak" then out[#out + 1] = "\n"
    elseif inline.t == "Quoted" then
      local quote = inline.quotetype == "SingleQuote" and "'" or '"'
      out[#out + 1] = quote .. text_of(inline.content) .. quote
    elseif inline.t == "Code" then out[#out + 1] = inline.text
    else out[#out + 1] = pandoc.utils.stringify(inline) end
  end
  return table.concat(out)
end

local function inline_data(div)
  for _, block in ipairs(div.content) do
    if block.t == "CodeBlock" then return block.text end
  end
  local lines = {}
  for _, block in ipairs(div.content) do
    if block.t == "Para" or block.t == "Plain" then lines[#lines + 1] = text_of(block.content) end
  end
  if #lines > 0 then return table.concat(lines, "\n") end
  return nil
end

local function read_file(path)
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
  if not file then return nil end
  local text = file:read("a")
  file:close()
  return (text:gsub("^\239\187\191", ""))
end

local ALIGNMENTS = {l = "AlignLeft", left = "AlignLeft", c = "AlignCenter", center = "AlignCenter", centre = "AlignCenter",
                    r = "AlignRight", right = "AlignRight", d = "AlignDefault", default = "AlignDefault"}

-- `align="lcr"`, `align="left,center,right"`: one per column; fewer than the columns leaves the rest as they are
local function read_align(value)
  if not value or value == "" then return nil end
  local out = {}
  if value:match("^[lcrdLCRD]+$") then
    for letter in value:lower():gmatch(".") do out[#out + 1] = ALIGNMENTS[letter] end
  else
    for word in value:lower():gmatch("[^,%s]+") do out[#out + 1] = ALIGNMENTS[word] or "AlignDefault" end
  end
  return out
end

-- `widths="2,5,1"`: relative widths of the columns; with a % on every number (`widths="30%,60%"`) the share of the
-- text width itself, so the table may be narrower than the text (what a grid table's column layout asks for)
local function read_widths(value)
  if not value or value == "" then return nil end
  local out, total, percent = {}, 0, true
  for word in value:gmatch("[^,%s]+") do
    local number = tonumber((word:gsub("%%$", "")))
    if not number or number <= 0 then return nil end
    if not word:match("%%$") then percent = false end
    out[#out + 1] = number
    total = total + number
  end
  local divisor = (percent and total <= 100.5) and 100 or total
  for i = 1, #out do out[i] = out[i] / divisor end
  return out
end

-- a row of nothing but `---`, `:--`, `--:`, `:-:` is a separator row, as in a pipe table
local function separator_row(fields)
  if #fields == 0 then return false end
  for _, field in ipairs(fields) do
    if not field:match("^%s*:?%-+:?%s*$") then return false end
  end
  return true
end

local function separator_settings(fields)
  local aligns, dashes, equal = {}, {}, true
  for i, field in ipairs(fields) do
    local cell = field:match("^%s*(.-)%s*$")
    local left, right = cell:sub(1, 1) == ":", cell:sub(-1) == ":"
    aligns[i] = (left and right) and "AlignCenter" or left and "AlignLeft" or right and "AlignRight" or "AlignDefault"
    dashes[i] = #cell          -- as Pandoc counts them, colons included
    if dashes[i] ~= dashes[1] then equal = false end
  end
  local widths
  if not equal then
    widths = {}
    local total = 0
    for i = 1, #dashes do total = total + dashes[i] end
    for i = 1, #dashes do widths[i] = dashes[i] / total end
  end
  return aligns, widths
end

-- a spreadsheet (v3.29.23): pdfmd has turned each sheet a .csv div names into a CSV file and says where in `pdfmd-sheet-map`
local sheet_map = {}
local function is_spreadsheet(path)
  local lower = path:lower()
  return lower:match("%.xlsx$") or lower:match("%.xlsm$") or lower:match("%.xls$") or lower:match("%.ods$")
end

local function csv_blocks(div)
  local path = div.attributes["file"]
  local text, label
  if path and path ~= "" and is_spreadsheet(path) then
    local converted = sheet_map[path .. "|" .. (div.attributes["sheet"] or "")]
    if not converted then
      io.stderr:write("WARN  .csv: '" .. path .. "' is a spreadsheet pdfmd did not convert (see the note above); leaving it empty\n")
      return {}
    end
    text = read_file(converted)
    label = path
    if not text then
      io.stderr:write("WARN  .csv: could not open the converted sheet of '" .. path .. "'; leaving it empty\n")
      return {}
    end
  elseif path and path ~= "" then
    text = read_file(path)
    label = path
    if not text then
      io.stderr:write("WARN  .csv: could not open '" .. path .. "'; leaving it empty\n")
      return {}
    end
  else
    text = inline_data(div)
    label = "inline data"
    if not text then
      io.stderr:write("WARN  .csv div has neither file= nor data inside it; leaving it empty\n")
      return {}
    end
  end

  local delim = div.attributes["delimiter"]
  if (delim == nil or delim == "") and defaults.delimiter ~= "auto" then delim = defaults.delimiter end
  if delim == nil or delim == "" or delim:lower() == "auto" then
    delim = guess_delimiter(text, path)
    if delim ~= extension_delimiter(path) then
      local word = DELIMITER_WORDS[delim] or delim
      io.stderr:write("WARN  " .. label .. ": read with " .. word .. "s as the delimiter (its records all have the same number of fields " ..
                       "with them); say delimiter=\"" .. word .. "\" on the div, or `csv: {delimiter: " .. word ..
                       "}` in pdfmd-options, to make it explicit\n")
    end
  else
    delim = DELIMITER_NAMES[delim:lower()] or delim:sub(1, 1)
  end
  local cut = (div.attributes["cut"] or defaults.cut or "ends"):lower()
  -- the note under a table that was cut: short (the fact), off, full (the fact and how to show more); see CSV_NOTES in pdfmd.py
  local note_mode = (div.attributes["note"] or defaults.note or "short"):lower()
  if note_mode == "false" or note_mode == "no" or note_mode == "none" then note_mode = "off" end
  if note_mode == "true" or note_mode == "yes" or note_mode == "on" then note_mode = "short" end
  if note_mode ~= "short" and note_mode ~= "off" and note_mode ~= "full" then
    io.stderr:write("WARN  " .. label .. ": note=" .. note_mode .. " is not short, off or full; short is used\n")
    note_mode = "short"
  end
  local max_rows = limit_or_all(div.attributes["rows"], defaults.rows or DEFAULT_MAX_ROWS)
  local max_cols = limit_or_all(div.attributes["cols"], defaults.cols or DEFAULT_MAX_COLS)
  local has_header = defaults.header
  if div.attributes["header"] ~= nil then has_header = div.attributes["header"] ~= "false" end
  local separator = (div.attributes["separator"] or "auto"):lower()
  -- cells are read as Pandoc's own Markdown (H~2~O, $x^2$, [@key], \ce{...}); reader="gfm" restores plain GFM
  local reader = div.attributes["reader"]
  if reader == nil or reader == "" then reader = defaults.reader end

  local parsed_rows = parse_csv(text, delim)
  local header_fields = nil
  local data_rows = {}
  local total_data_rows = 0
  local total_cols = 0
  local rows_truncated = false
  local cols_truncated = false
  local aligns, widths

  local all_rows = {}
  for index, fields in ipairs(parsed_rows) do
    if #fields > total_cols then total_cols = #fields end
    if has_header and index == 1 then
      header_fields = fields
    elseif has_header and index == 2 and separator ~= "none" and separator ~= "false" and separator_row(fields) then
      aligns, widths = separator_settings(fields)
    else
      total_data_rows = total_data_rows + 1
      all_rows[#all_rows + 1] = fields
    end
  end
  if not header_fields then
    header_fields = {}
    for i = 1, math.max(total_cols, 1) do header_fields[i] = "Column " .. i end
  end
  -- attributes win over a separator row; they name the columns of the file, like the separator row
  aligns = read_align(div.attributes["align"]) or aligns
  local own_widths = read_widths(div.attributes["widths"])
  widths = own_widths or widths

  local kept_cols, col_head, col_tail = keep_indices(total_cols, max_cols, cut)
  local kept_rows, row_head, row_tail = keep_indices(#all_rows, max_rows, cut)
  cols_truncated, rows_truncated = col_head ~= nil, row_head ~= nil
  local shown_cols = #kept_cols
  local width_count = #kept_cols + ((col_tail and col_tail > 0) and 1 or 0)
  local function project(list, gap)                 -- a row (or the alignments, widths) cut to the kept columns
    local out, n = {}, 0
    for position, index in ipairs(kept_cols) do
      n = n + 1
      out[n] = list and list[index] or nil
      if col_tail and col_tail > 0 and position == col_head then n = n + 1; out[n] = gap end
    end
    return out
  end
  if cols_truncated then
    header_fields = project(header_fields, GAP)
    if aligns then aligns = project(aligns, "AlignCenter") end
    if widths then
      local before, after = 0, 0
      for i = 1, total_cols do before = before + (widths[i] or 0) end
      widths = project(widths, 0.04)
      for i = 1, width_count do widths[i] = widths[i] or 0.04; after = after + widths[i] end
      for i = 1, width_count do widths[i] = widths[i] * before / after end
    end
  end
  for position, index in ipairs(kept_rows) do
    data_rows[#data_rows + 1] = cols_truncated and project(all_rows[index], GAP) or all_rows[index]
    if row_tail and row_tail > 0 and position == row_head then
      local gap_row = {}
      for i = 1, #header_fields do gap_row[i] = GAP end
      data_rows[#data_rows + 1] = gap_row
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

  for _, block in ipairs(blocks) do
    if block.t == "Table" then
      for i, spec in ipairs(block.colspecs) do
        local align = aligns and aligns[i] or spec[1]
        local width = widths and widths[i]
        if width then block.colspecs[i] = {align, width} else block.colspecs[i] = {align} end
      end
      if own_widths then block.attr.attributes["data-pdfmd-widths"] = "fixed" end
      break
    end
  end

  if rows_truncated or cols_truncated then
    local shown_rows = #kept_rows
    local function part(head, tail, shown, total, noun)
      local plural = total == 1 and "" or "s"
      if head and tail and tail > 0 then
        return string.format("the first %d and the last %d of %d %s%s", head, tail, total, noun, plural)
      end
      return string.format("%d of %d %s%s", shown, total, noun, plural)
    end
    local facts = {}
    if rows_truncated then facts[#facts + 1] = part(row_head, row_tail, shown_rows, total_data_rows, "row") end
    if cols_truncated then facts[#facts + 1] = part(col_head, col_tail, shown_cols, total_cols, "column") end
    local shown_text = table.concat(facts, ", ")
    local note
    if note_mode == "full" then
      note = "*(showing " .. shown_text .. " -- use `rows=all`/`cols=all`, or `rows=N`/`cols=N`, on this `.csv` div to include more, " ..
        "or `--csv-rows`/`--csv-cols` for every table)*"
    elseif note_mode == "short" then
      note = "*(showing " .. shown_text .. ")*"
    end
    if note then
      for _, block in ipairs(pandoc.read(note .. "\n", "markdown").blocks) do blocks[#blocks + 1] = block end
    end
    local advice = {}
    if rows_truncated then advice[#advice + 1] = "rows=all or rows=N on the .csv div shows more rows, --csv-rows for every table" end
    if cols_truncated then advice[#advice + 1] = "cols=all or cols=N on the .csv div shows more columns, --csv-cols for every table" end
    io.stderr:write("WARN  " .. label .. ": showing " .. shown_text .. " -- " .. table.concat(advice, "; ") .. "\n")
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
      if identifier ~= "" or #classes > 0 or #pairs_ > 0 then
        local marker = block.attr.attributes["data-pdfmd-widths"]
        if marker then pairs_[#pairs_ + 1] = {"data-pdfmd-widths", marker} end
        block.attr = pandoc.Attr(identifier, classes, pairs_)
      end
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
          if item.t == "Table" then
            local marker = item.attr.attributes["data-pdfmd-widths"]
            item.attr = pandoc.Attr(block.identifier, {}, marker and {{"data-pdfmd-widths", marker}} or {})
            break
          end
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


local function read_defaults(meta)
  local changed = false
  local function take(key)
    local value = meta["pdfmd-csv-" .. key]
    if value == nil then return nil end
    meta["pdfmd-csv-" .. key] = nil
    changed = true
    if type(value) == "boolean" then return tostring(value) end
    return pandoc.utils.stringify(value)
  end
  local map = meta["pdfmd-sheet-map"]
  if map ~= nil then
    for key, value in pairs(map) do sheet_map[key] = pandoc.utils.stringify(value) end
    meta["pdfmd-sheet-map"] = nil
    changed = true
  end
  local rows, cols, header, reader = take("rows"), take("cols"), take("header"), take("reader")
  local delimiter, cut, note = take("delimiter"), take("cut"), take("note")
  if note and note ~= "" then defaults.note = note:lower() end
  if delimiter and delimiter ~= "" then
    defaults.delimiter = delimiter:lower() == "auto" and "auto" or (DELIMITER_NAMES[delimiter:lower()] or delimiter:sub(1, 1))
  end
  if cut and cut ~= "" then defaults.cut = cut:lower() end
  if rows then defaults.rows = limit_or_all(rows, DEFAULT_MAX_ROWS) end
  if cols then defaults.cols = limit_or_all(cols, DEFAULT_MAX_COLS) end
  if header then defaults.header = header ~= "false" end
  if reader and reader ~= "" then defaults.reader = reader end
  if changed then return meta end
end

return {{Meta = read_defaults}, {Blocks = Blocks}}

-- pdfmd supplies the estimated line budget. Standalone filter use and unknown
-- layouts use the table-chars fallback.
local FALLBACK_BUDGET = 95
-- Rough per-column overhead (rule padding + inter-column gap) so a table
-- with many columns, each individually short, doesn't dodge the budget
-- check on a technicality -- \tabcolsep-scale, not a real measurement.
local PER_COLUMN_OVERHEAD = 3
-- pandoc.utils.stringify() renders a Math inline as its raw LaTeX SOURCE
-- (e.g. "\frac{1.0 \times 10^{-14}}{[OH^-]}", 34 characters), not its
-- typeset width (a fraction that renders at a fraction of that) -- found
-- via a real chemistry-report table (Ksp/uncertainty-propagation cells)
-- getting stretched by cell_length() treating that raw command text as
-- 34 characters of visual width. No exact fix is possible here either
-- (no font has been measured yet
-- when this filter runs), so this is a flat divisor, not a real LaTeX-
-- width estimator: a short subscript/superscript like "K_{sp}" (6 raw
-- characters, renders about as wide as "Ksp") and a stacked fraction
-- like the one above (34 raw characters, renders roughly as wide as its
-- widest of numerator/denominator, maybe 10-12) both land closer to
-- their real rendered width divided by roughly 3 than left undivided.
local MATH_LENGTH_DIVISOR = 3

local function math_overcount(contents)
  local overcount = 0
  contents:walk({
    Math = function(m)
      local source_len = #m.text
      overcount = overcount + (source_len - math.ceil(source_len / MATH_LENGTH_DIVISOR))
    end
  })
  return overcount
end

-- KLUDGE, until the true width estimator exists (TODO "A true width estimator"): `pandoc.utils.stringify` counts a raw
-- TeX inline as nothing, so a cell of "respiratory tract \SIrange{10}{20}{\minute}" was measured as 17 characters and
-- printed as 34. These guesses stand in for the typeset text: `\SI{a}{u}` is the number and a unit word,
-- `\SIrange{a}{b}{u}` is "a unit to b unit", `\num{a}` is a, `\ce{...}` is its text, any other raw TeX is the characters
-- outside command names. A unit is 2 characters per command in it (`\milli\gram` is 4) or its own characters. The
-- number stands for how it is printed, not for the source. Switch: `column-count-raw-tex: off`.
local function unit_word(unit)
  local _, commands = unit:gsub("\\%a+", "")
  local rest = unit:gsub("\\%a+", ""):gsub("[{}%s]", "")
  return string.rep("x", math.max(2, 2 * commands + #rest))
end

local function raw_estimate(code)
  local name, rest = code:match("^\\(%a+)%*?(.*)$")
  if name == "SI" or name == "qty" then
    local number, unit = rest:match("^%s*%[?[^%]{]*%]?%s*{([^}]*)}%s*{([^}]*)}")
    if number then return number .. "_" .. unit_word(unit) end
  elseif name == "SIrange" or name == "qtyrange" then
    local low, high, unit = rest:match("^%s*%[?[^%]{]*%]?%s*{([^}]*)}%s*{([^}]*)}%s*{([^}]*)}")
    if low then return low .. "_" .. unit_word(unit) .. " to " .. high .. "_" .. unit_word(unit) end
  elseif name == "num" then
    local number = rest:match("^%s*%[?[^%]{]*%]?%s*{([^}]*)}")
    if number then return number end
  end
  return (code:gsub("\\%a+", ""):gsub("[{}\\^_$]", ""))
end

local function cell_text(cell, count_raw)
  if not count_raw then return pandoc.utils.stringify(cell.contents) end
  local counted = cell.contents:walk({
    RawInline = function(raw)
      if raw.format == "tex" or raw.format == "latex" then return pandoc.Str(raw_estimate(raw.text)) end
    end
  })
  return pandoc.utils.stringify(counted)
end

local function cell_length(cell, count_raw)
  local length = #cell_text(cell, count_raw) - math_overcount(cell.contents)
  if length < 1 then length = 1 end
  return length
end


-- Where a table's text goes: for every column, the length of each row's cell, so that the height a row
-- takes at a given column width can be worked out (a row is as tall as its tallest cell).
local function collect(tbl, count_raw)
  local ncols = #tbl.colspecs
  local rows, longest, word = {}, {}, {}
  for i = 1, ncols do longest[i] = 1; word[i] = 1 end
  local function add(row)
    local lengths = {}
    for i = 1, ncols do lengths[i] = 0 end
    for i, cell in ipairs(row.cells) do
      local span = cell.col_span or 1
      local share = math.max(1, math.ceil(cell_length(cell, count_raw) / span))
      local widest = 1
      for text in cell_text(cell, count_raw):gmatch("%S+") do
        if #text > widest then widest = #text end
      end
      widest = math.ceil(widest / span)
      for k = i, math.min(i + span - 1, ncols) do
        lengths[k] = share
        if share > longest[k] then longest[k] = share end
        if widest > word[k] then word[k] = widest end
      end
    end
    rows[#rows + 1] = lengths
  end
  for _, row in ipairs(tbl.head.rows) do add(row) end
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.head) do add(row) end
    for _, row in ipairs(body.body) do add(row) end
  end
  for _, row in ipairs(tbl.foot.rows) do add(row) end
  return rows, longest, word
end

-- Loaded only for the opt-in mode. Measurements are taken at this filter's table position in the document.
local tables_seen = 0
local measurements = nil
local writer_widths = false
local function dimensions(tbl, o)
  local char_rows, char_longest, char_word = collect(tbl, o.count_raw)
  local data = o.estimate == "measure" and measurements and measurements.tables[tostring(tables_seen)]
  if not data then
    return char_rows, char_longest, char_word, o.chars - #tbl.colspecs * PER_COLUMN_OVERHEAD
  end
  local rows, longest, word, char_totals, point_totals = {}, {}, {}, {}, {}
  for c = 1, #tbl.colspecs do longest[c], word[c], char_totals[c], point_totals[c] = 1, 1, 0, 0 end
  local row_number = 0
  local function add(row)
    row_number = row_number + 1
    local lengths, counts = {}, {}
    for c = 1, #tbl.colspecs do lengths[c], counts[c] = 0, 0 end
    for c, cell in ipairs(row.cells) do
      local measured = data.cells[row_number][c]
      local span = cell.col_span or 1
      for k = c, math.min(c + span - 1, #tbl.colspecs) do
        local width, floor = math.max(1, measured.width / span), math.max(1, measured.word / span)
        lengths[k] = width
        counts[k] = math.max(1, cell_length(cell, o.count_raw) / span)
        longest[k], word[k] = math.max(longest[k], width), math.max(word[k], floor)
        char_totals[k], point_totals[k] = char_totals[k] + counts[k], point_totals[k] + width
      end
    end
    rows[#rows + 1] = lengths
    char_rows[row_number] = counts
  end
  for _, row in ipairs(tbl.head.rows) do add(row) end
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.head) do add(row) end
    for _, row in ipairs(body.body) do add(row) end
  end
  for _, row in ipairs(tbl.foot.rows) do add(row) end
  local scale = {}
  for c = 1, #tbl.colspecs do scale[c] = point_totals[c] / math.max(1, char_totals[c]) end
  return rows, longest, word, data.line - #tbl.colspecs * data.sep, char_rows, scale
end

-- A cell that is far longer than every other cell of its column (a 66-character note among cells of 8 to 24) must not
-- size the column: the others would starve to hold it on one line. The cap of such a column is its next-longest cell
-- and the outlier wraps; what is left over goes back to the outlier's column at the end (best_widths). `ratio` is the
-- times-longer threshold (`column-outlier`, 0 switches it off); a column of fewer than `column-outlier-rows` rows,
-- or an outlier shorter than `column-outlier-length` characters, is never judged.
local function outlier_caps(rows, longest, o, char_rows)
  local ratio, min_rows, min_length = o["column-outlier"], o["column-outlier-rows"], o["column-outlier-length"]
  local caps = {}
  for c = 1, #longest do
    caps[c] = longest[c]
    if ratio > 0 then
      local first, second, count, first_chars = 0, 0, 0, 0
      for r, lengths in ipairs(rows) do
        local length = lengths[c] or 0
        if length > 0 then
          count = count + 1
          if length > first then
            first, second = length, first
            first_chars = char_rows and char_rows[r][c] or length
          elseif length > second then second = length end
        end
      end
      if count >= min_rows and first_chars >= min_length and second > 0 and first > ratio * second then
        caps[c] = second
      end
    end
  end
  return caps
end

-- A long table is judged on an even sample of its rows: the widths do not need every row to be right.
local SAMPLE = 200

local function sample(rows)
  if #rows <= SAMPLE then return rows end
  local picked = {}
  for i = 1, SAMPLE do picked[i] = rows[math.ceil(i * #rows / SAMPLE)] end
  return picked
end

-- How many lines the rows take altogether when column c is widths[c] characters wide.
local function total_height(rows, widths)
  local total = 0
  for _, lengths in ipairs(rows) do
    local tallest = 1
    for c, length in ipairs(lengths) do
      if length > 0 then
        local lines = math.ceil(length / widths[c])
        if lines > tallest then tallest = lines end
      end
    end
    total = total + tallest
  end
  return total
end

-- The widths (in characters, summing to `room`) that make the rows take the fewest lines. A column is never
-- narrower than its longest word, nor wider than its longest cell. Widths are handed out where they buy the
-- most, by steps of 1, 2, 4 and 8 characters (a single character often buys nothing at all and several do);
-- what is left over after that goes to the columns that still have text to unwrap.
local function best_widths(rows, longest, word, room, caps)
  caps = caps or longest
  local n = #longest
  local widths, floor_sum = {}, 0
  for c = 1, n do
    widths[c] = math.min(word[c], caps[c])
    floor_sum = floor_sum + widths[c]
  end
  if floor_sum >= room then            -- not even the words fit: shrink them evenly
    for c = 1, n do widths[c] = math.max(1, widths[c] * room / floor_sum) end
    return widths
  end
  local sampled = sample(rows)
  local remaining = room - floor_sum
  local current = total_height(sampled, widths)
  while remaining > 0 do
    local best_c, best_step, best_rate, best_room = nil, nil, 0, 0
    for c = 1, n do
      local spare = caps[c] - widths[c]
      if spare > 0 then
        for _, step in ipairs({1, 2, 4, 8}) do
          if step <= remaining and step <= spare then
            widths[c] = widths[c] + step
            local rate = (current - total_height(sampled, widths)) / step
            widths[c] = widths[c] - step
            if rate > best_rate + 1e-9 or (rate > 0 and math.abs(rate - best_rate) <= 1e-9 and spare > best_room) then
              best_c, best_step, best_rate, best_room = c, step, rate, spare
            end
          end
        end
      end
    end
    if not best_c then break end
    widths[best_c] = widths[best_c] + best_step
    remaining = remaining - best_step
    current = total_height(sampled, widths)
  end
  -- nothing buys a line any more: let the long cells breathe, first up to each column's cap (every ordinary cell on
  -- one line), and only what is left after that up to an outlier's real length
  for _, limit in ipairs({caps, longest}) do
    if remaining > 0 then
      local wanted = 0
      for c = 1, n do wanted = wanted + (limit[c] - widths[c]) end
      if wanted > 0 then
        local share = math.min(1, remaining / wanted)
        for c = 1, n do widths[c] = widths[c] + (limit[c] - widths[c]) * share end
        remaining = remaining - wanted * share
      end
    end
  end
  return widths
end

-- Pandoc gives a pipe table whose lines are too long the widths of its `---|---` separator dashes, and the
-- same number of dashes in every column is the usual "I did not choose" separator. Unequal dashes are a choice.
local function equal_widths(colspecs)
  local low, high
  for _, spec in ipairs(colspecs) do
    local width = spec[2]
    if width == nil then return false end
    if low == nil or width < low then low = width end
    if high == nil or width > high then high = width end
  end
  return high - low < 0.005
end

local function has_default(colspecs)
  for _, spec in ipairs(colspecs) do
    if spec[2] == nil then return true end
  end
  return false
end

-- pdfmd asks to hear about a table it had to resize (PDFMD_TABLEWIDTH_LOG: a file it reads afterwards); nothing
-- is written when the variable is not set, or for a table that already fits
-- tables_seen is the table's place in the document; shared by measurement and balancing
local function report(kind)
  local path = os.getenv("PDFMD_TABLEWIDTH_LOG")
  if path == nil or path == "" then return end
  local handle = io.open(path, "a")
  if handle then
    handle:write(tables_seen .. (kind or "") .. "\n")
    handle:close()
  end
end

local cache_dir, cache_layout

local function cache_path(tbl, options)
  if not cache_dir then return nil end
  local fields = {cache_layout, tostring(PANDOC_VERSION), FORMAT, pandoc.write(pandoc.Pandoc({tbl}), "json")}
  local settings = {}
  for key, value in pairs(options) do settings[#settings + 1] = key .. "=" .. tostring(value) end
  table.sort(settings)
  fields[#fields + 1] = table.concat(settings, "\0")
  local data = options.estimate == "measure" and measurements and measurements.tables[tostring(tables_seen)]
  if data then
    fields[#fields + 1] = string.format("%.17g %.17g %.17g", data.line, data.sep, data.inset or 0)
    for _, row in ipairs(data.cells) do
      fields[#fields + 1] = tostring(#row)
      for _, cell in ipairs(row) do
        fields[#fields + 1] = string.format("%.17g %.17g", cell.width, cell.word)
      end
    end
  end
  return pandoc.path.join({cache_dir, pandoc.utils.sha1(table.concat(fields, "\n")) .. ".widths"})
end

local function parse_widths(text, count)
  local kind, values = text:match("^([wc]*)\n([%d%.%+%-%seE]+)$")
  if not kind or (kind ~= "" and kind ~= "w" and kind ~= "c" and kind ~= "wc") then return nil end
  local widths = {}
  for value in values:gmatch("%S+") do
    local width = tonumber(value)
    if not width or width <= 0 or width > 1 then return nil end
    widths[#widths + 1] = width
  end
  if #widths == count then return widths, kind end
  return nil
end

local function cached_widths(path, count)
  if not path then return nil end
  local handle = io.open(path, "r")
  if not handle then return nil end
  local text = handle:read("*a")
  handle:close()
  if not text then return nil end
  local widths, kind = parse_widths(text, count)
  if not widths then os.remove(path) end
  return widths, kind
end

local function save_widths(path, tbl, kind)
  if not path then return end
  local values = {}
  for c, spec in ipairs(tbl.colspecs) do values[c] = string.format("%.17g", spec[2]) end
  -- A failed or concurrent write can leave only a complete entry. The temporary file is on the same volume.
  pcall(pandoc.system.with_temporary_directory, cache_dir, "widths-", function(folder)
    local temporary = pandoc.path.join({folder, "widths"})
    local handle = io.open(temporary, "w")
    if not handle then return end
    local written = handle:write(kind .. "\n" .. table.concat(values, " ") .. "\n")
    local closed = handle:close()
    if written and closed then os.rename(temporary, path) end
  end)
end

-- Widths the author chose are kept, except for one thing nobody chooses: a column too narrow for its own longest
-- word, which LaTeX then breaks in the middle ("Sus-tained"). Such a column is raised to that word (a word longer
-- than `column-word-floor-limit` characters, a URL say, is not worth the room) and the other columns give up the space in
-- proportion to what they were given, none below its own floor. A table where every column already holds its
-- longest word is returned untouched; one whose floors do not fit at all keeps the choice.
local function keep_words(chars, longest, word, room, scale, o)
  local floor_, floor_sum, short = {}, 0, false
  for c = 1, #chars do
    floor_[c] = math.min(word[c], longest[c], o["column-word-floor-limit"] * (scale and scale[c] or 1))
    floor_sum = floor_sum + floor_[c]
    if chars[c] < floor_[c] - 1e-9 then short = true end
  end
  if not short or floor_sum >= room then return nil end
  local widths, locked = {}, {}
  for c = 1, #chars do
    if chars[c] < floor_[c] then widths[c] = floor_[c]; locked[c] = true end
  end
  local changed = true
  while changed do
    changed = false
    local left, free = room, 0
    for c = 1, #chars do
      if locked[c] then left = left - widths[c] else free = free + chars[c] end
    end
    for c = 1, #chars do
      if not locked[c] then
        widths[c] = chars[c] * left / free
        if widths[c] < floor_[c] then widths[c] = floor_[c]; locked[c] = true; changed = true end
      end
    end
  end
  return widths
end

-- Leave the margin above the longest cell. Share the released space in proportion to the
-- room the other columns are missing, up to their longest cells.
local function take_air(widths, longest, margin)
  local released, wanted = 0, 0
  for c, width in ipairs(widths) do
    local cap = longest[c] + margin
    if width > cap then
      released = released + width - cap
      widths[c] = cap
    end
    wanted = wanted + math.max(0, longest[c] - width)
  end
  if released <= 0 then return false end
  if wanted > 0 then
    local share = math.min(1, released / wanted)
    for c, width in ipairs(widths) do
      widths[c] = width + math.max(0, longest[c] - width) * share
    end
  end
  return true
end

local function adjust_chosen(tbl, o)
  local margin = o.ceil and o["column-ceil-margin"] or 0
  if not o.floor and margin == 0 then return nil end
  local _, longest, word, room, _, scale = dimensions(tbl, o)
  if room <= 0 then return nil end
  local data = o.estimate == "measure" and measurements and measurements.tables[tostring(tables_seen)]
  local chars = {}
  for c, spec in ipairs(tbl.colspecs) do
    chars[c] = spec[2] * room
    if data and data.inset then chars[c] = spec[2] * data.line - data.inset end
  end
  local widened = o.floor and keep_words(chars, longest, word, room, scale, o)
  local widths = widened or chars
  local narrowed = margin > 0 and take_air(widths, longest, margin * (data and data.line or o.chars))
  if not widened and not narrowed then return nil end
  for c, spec in ipairs(tbl.colspecs) do
    local width = widths[c] / room
    if data and data.inset then width = (widths[c] + data.inset) / data.line end
    tbl.colspecs[c] = {spec[1], width}
  end
  return tbl, (widened and "w" or "") .. (narrowed and "c" or "")
end

-- The settings, set from the metadata before the walk (see Pandoc below); a table's own attributes
-- (`{widths=force word-floor=off column-outlier=3}` after its caption) win over them. widths: auto (equal dashes are
-- "no opinion", unequal ones a choice), keep (every table as written), force (the dashes are ignored, every table is
-- balanced). word-floor: on or off, whether a chosen column is raised to its longest word. The numbers are
-- settings too, none is a constant: column-outlier (times longer than the next cell; 0 = off), column-outlier-rows,
-- column-outlier-length, column-word-floor-limit (the longest word the floor protects).
local MODES = {auto = true, keep = true, force = true}
local SWITCH = {on = true, ["true"] = true, yes = true, off = false, ["false"] = false, no = false}
local GLOBAL = {
  mode = "auto", floor = true, ceil = true, count_raw = true, estimate = "count", ["column-ceil-margin"] = 0.25,
  ["column-outlier"] = 2, ["column-outlier-rows"] = 4, ["column-outlier-length"] = 30, ["column-word-floor-limit"] = 16,
}
local table_style, row_spacing = "off", "1.4"
local NUMBERS = {"column-outlier", "column-outlier-rows", "column-outlier-length", "column-word-floor-limit"}

local function number_of(text)
  if text == nil then return nil end
  text = text:lower()
  if text == "off" or text == "false" then return 0 end
  local value = tonumber(text)
  if value ~= nil and value >= 0 then return value end
  return nil
end

local function char_budget(text)
  local value = number_of(text)
  if value and value > 0 and value < math.huge and value == math.floor(value) then return value end
end

local function style_of(text)
  local word = (text or ""):lower():match("^%s*(.-)%s*$")
  if word == "spaced" or word == "off" then return word end
  if word == "false" then return "off" end
end

local function spacing_of(text)
  local word = (text or ""):match("^%s*(.-)%s*$")
  local value = tonumber(word)
  -- TeX needs a decimal multiplier in front of a length.
  if value and value >= 1 and value < math.huge and word:match("^%d+%.?%d*$") then return word end
end

local function margin_of(text)
  if text == nil then return nil end
  text = text:match("^%s*(.-)%s*$"):lower()
  local percent = text:sub(-1) == "%"
  local value = number_of(percent and text:sub(1, -2) or text)
  if value ~= nil then
    if percent then value = value / 100 end
    if value <= 1 then return value end
  end
  return nil
end

-- the settings of one table: the global ones, then its own attributes (which are taken off the table)
local function table_options(attributes)
  local o = {}
  for key, value in pairs(GLOBAL) do o[key] = value end
  o.chars = GLOBAL.chars or char_budget(attributes["table-chars"]) or GLOBAL.fallback_chars
  attributes["table-chars"] = nil
  local given = attributes["widths"]
  if given ~= nil then
    if MODES[given:lower()] then o.mode = given:lower() end
    attributes["widths"] = nil
  end
  given = attributes["column-estimate"]
  if given ~= nil then
    local estimate = given:lower():match("^%s*(.-)%s*$")
    if estimate == "count" or estimate == "measure" then o.estimate = estimate end
    attributes["column-estimate"] = nil
  end
  given = attributes["word-floor"]
  if given ~= nil then
    if SWITCH[given:lower()] ~= nil then o.floor = SWITCH[given:lower()] end
    attributes["word-floor"] = nil
  end
  given = attributes["word-ceil"]
  if given ~= nil then
    if SWITCH[given:lower()] ~= nil then o.ceil = SWITCH[given:lower()] end
    attributes["word-ceil"] = nil
  end
  o["column-ceil-margin"] = margin_of(attributes["column-ceil-margin"]) or o["column-ceil-margin"]
  attributes["column-ceil-margin"] = nil
  given = attributes["count-raw-tex"]
  if given ~= nil then
    if SWITCH[given:lower()] ~= nil then o.count_raw = SWITCH[given:lower()] end
    attributes["count-raw-tex"] = nil
  end
  for _, key in ipairs(NUMBERS) do
    if attributes[key] ~= nil then
      local value = number_of(attributes[key])
      if value ~= nil then o[key] = value end
      attributes[key] = nil
    end
  end
  return o
end

-- pdfmd's cell tags (cellalign.lua) can make a source line longer than Pandoc's column limit, which makes Pandoc read the separator's
-- dashes as widths. The pre-pass then marks the table `<pt nw ...>` in its first header cell: the table is measured as it would have been.
local function without_dash_widths(tbl)
  local row = tbl.head.rows[1]
  local cell = row and row.cells[1]
  local block = cell and cell.contents[1]
  local first = block and block.content and block.content[1]
  if not (first and first.t == "RawInline" and (first.text:find("^<pt [^>]*[ ]nw[ >]") or first.text:find("^<pt nw[ >]"))) then return end
  for index, spec in ipairs(tbl.colspecs) do tbl.colspecs[index] = {spec[1]} end
end

-- Pandoc gives a long pipe table with equal dashes exactly 1/n per column.
-- A narrower grid table or even slightly unequal separator widths carry a choice.
local function restore_writer_widths(tbl, mode)
  if mode == "keep" or #tbl.colspecs == 0 then return nil end
  local share = 1 / #tbl.colspecs
  for _, spec in ipairs(tbl.colspecs) do
    if spec[2] ~= share then return nil end
  end
  for index, spec in ipairs(tbl.colspecs) do tbl.colspecs[index] = {spec[1]} end
  return tbl
end

local function rebalance(tbl, o)
  local ncols = #tbl.colspecs
  if ncols == 0 then return nil end
  local typst = FORMAT:match("typst") ~= nil
  local measured_typst = typst and o.estimate == "measure" and measurements and measurements.tables[tostring(tables_seen)]
  if not measured_typst then
    if writer_widths then return restore_writer_widths(tbl, o.mode) end
    if typst then return nil end
  end
  without_dash_widths(tbl)
  if o.mode == "keep" then return nil end
  local path = cache_path(tbl, o)
  local cached, kind = cached_widths(path, ncols)
  if cached then
    for c, spec in ipairs(tbl.colspecs) do tbl.colspecs[c] = {spec[1], cached[c]} end
    if typst then tbl.attributes["data-pdfmd-measured"] = "true" end
    report(kind)
    return tbl
  end
  local chosen = not has_default(tbl.colspecs) and not equal_widths(tbl.colspecs) and o.mode ~= "force"
  if chosen then
    local adjusted, mark = adjust_chosen(tbl, o)
    if adjusted then
      if typst then adjusted.attributes["data-pdfmd-measured"] = "true" end
      save_widths(path, adjusted, mark)
      report(mark)
    end
    return adjusted
  end
  if ncols == 1 and not has_default(tbl.colspecs) then
    tbl.colspecs[1] = {tbl.colspecs[1][1]}
    return tbl
  end

  local rows, longest, word, room, char_rows = dimensions(tbl, o)
  if room <= 0 and char_rows then return nil end
  local total = 0
  for i = 1, ncols do total = total + longest[i] end
  -- The table's own content already fits a line: leave it at its natural size (and give back the natural
  -- size to a table whose equal widths were only the separator's), rather than stretching a table nobody
  -- asked to have stretched.
  if total <= room then
    if has_default(tbl.colspecs) then return nil end
    for i, spec in ipairs(tbl.colspecs) do tbl.colspecs[i] = {spec[1]} end
    return tbl
  end

  local widths = best_widths(rows, longest, word, room, outlier_caps(rows, longest, o, char_rows))
  local sum = 0
  for i = 1, ncols do sum = sum + widths[i] end
  local data = o.estimate == "measure" and measurements and measurements.tables[tostring(tables_seen)]
  for i, spec in ipairs(tbl.colspecs) do
    local width = widths[i] / sum
    if data and data.inset then width = (widths[i] + data.inset) / data.line end
    tbl.colspecs[i] = {spec[1], width}
  end
  if typst then tbl.attributes["data-pdfmd-measured"] = "true" end
  save_widths(path, tbl, "")
  report()
  return tbl
end

local function wraps(tbl, o)
  local _, longest, _, room = dimensions(tbl, o)
  local data = o.estimate == "measure" and measurements and measurements.tables[tostring(tables_seen)]
  for c, spec in ipairs(tbl.colspecs) do
    local share = spec[2]
    if share and share > 0 then
      local width = data and data.inset and share * data.line - data.inset or share * room
      if longest[c] > width then return true end
    end
  end
  return false
end

local function format_table(tbl)
  tables_seen = tables_seen + 1
  local attributes = tbl.attr.attributes
  local fixed = attributes["data-pdfmd-widths"] == "fixed"
  if writer_widths and not measurements then
    if fixed then return nil end
    local given = attributes["widths"] and attributes["widths"]:lower()
    return restore_writer_widths(tbl, MODES[given] and given or GLOBAL.mode)
  end
  local style = style_of(attributes["table-style"]) or table_style
  local spacing = spacing_of(attributes["table-row-spacing"]) or row_spacing
  attributes["table-style"], attributes["table-row-spacing"] = nil, nil
  local spaced = style == "spaced" and (FORMAT == "latex" or FORMAT == "beamer")
  if fixed and not spaced then return nil end
  local o = table_options(attributes)
  local balanced
  if not fixed then balanced = rebalance(tbl, o) end        -- widths= on a .csv div
  local result = balanced or tbl
  if spaced and wraps(result, o) then
    -- Keep a Table in the AST so the filters after this one still see it.
    return {pandoc.RawBlock("latex", "\\begingroup\n\\renewcommand{\\arraystretch}{" .. spacing .. "}"),
            result, pandoc.RawBlock("latex", "\\endgroup")}
  end
  return balanced
end

-- A setting comes from the document's own `pdfmd-options` first, then from the global one pdfmd hands over
-- (`-M pdfmd-column-widths=...`, from the config or --setup). `table-widths` and `table-word-floor` are older names.
local function setting(meta, name, global_name)
  local options = meta["pdfmd-options"]
  local value = nil
  if options ~= nil then value = options[name] end                    -- YAML `off` is the boolean false
  if value == nil then value = meta["pdfmd-" .. (global_name or name)] end
  if value == nil then return nil end
  return pandoc.utils.stringify(value):lower()
end

function Pandoc(doc)
  writer_widths = doc.meta["pdfmd-writer-widths"] == true and FORMAT ~= "latex" and FORMAT ~= "beamer"
  doc.meta["pdfmd-writer-widths"] = nil
  local directory, layout = doc.meta["pdfmd-width-cache-dir"], doc.meta["pdfmd-width-cache-layout"]
  if directory and layout then
    cache_dir = pandoc.utils.stringify(directory)
    local metadata = {}
    for _, key in ipairs({"paper", "papersize", "geometry", "margin", "margin-left", "margin-right", "margin-top",
                          "margin-bottom", "mainfont", "mainfontoptions", "monofont", "monofontoptions", "mathfont",
                          "mathfontoptions", "sansfont", "sansfontoptions", "fontfamily", "fontfamilyoptions", "fontsize",
                          "documentclass", "classoption", "header-includes", "include-before"}) do
      metadata[key] = doc.meta[key]
    end
    cache_layout = pandoc.utils.stringify(layout) .. pandoc.write(pandoc.Pandoc({}, metadata), "json")
  end
  doc.meta["pdfmd-width-cache-dir"], doc.meta["pdfmd-width-cache-layout"] = nil, nil
  GLOBAL.chars = char_budget(pandoc.utils.stringify(doc.meta["pdfmd-table-chars"] or ""))
  GLOBAL.fallback_chars = char_budget(setting(doc.meta, "table-chars", "table-chars-fallback"))
    or char_budget(pandoc.utils.stringify(doc.meta["pdfmd-table-chars-fallback"] or "")) or FALLBACK_BUDGET
  doc.meta["pdfmd-table-chars"], doc.meta["pdfmd-table-chars-fallback"] = nil, nil
  table_style = style_of(setting(doc.meta, "table-style")) or table_style
  row_spacing = spacing_of(setting(doc.meta, "table-row-spacing")) or row_spacing
  local estimate = setting(doc.meta, "column-estimate")
  if estimate then estimate = estimate:match("^%s*(.-)%s*$") end
  if estimate == "count" or estimate == "measure" then GLOBAL.estimate = estimate end
  local mode = setting(doc.meta, "column-widths") or setting(doc.meta, "table-widths")
  if mode ~= nil and MODES[mode] then GLOBAL.mode = mode end
  local floor = SWITCH[setting(doc.meta, "column-word-floor") or setting(doc.meta, "table-word-floor") or ""]
  if floor ~= nil then GLOBAL.floor = floor end
  local ceil = SWITCH[setting(doc.meta, "column-word-ceil") or ""]
  if ceil ~= nil then GLOBAL.ceil = ceil end
  GLOBAL["column-ceil-margin"] = margin_of(setting(doc.meta, "column-ceil-margin")) or GLOBAL["column-ceil-margin"]
  local raw = SWITCH[setting(doc.meta, "column-count-raw-tex") or ""]
  if raw ~= nil then GLOBAL.count_raw = raw end
  for _, key in ipairs(NUMBERS) do
    local value = number_of(setting(doc.meta, key))
    if value ~= nil then GLOBAL[key] = value end
  end
  if doc.meta["pdfmd-measure-role"] and pandoc.utils.stringify(doc.meta["pdfmd-measure-role"]) == "dump" then
    local measuring = dofile(PANDOC_SCRIPT_FILE:match("^(.*[/\\])") .. "table_measure.lua")
    return measuring.dump(doc, table_options)
  end
  if doc.meta["pdfmd-column-measurements"] then
    local handle = assert(io.open(pandoc.utils.stringify(doc.meta["pdfmd-column-measurements"]), "r"))
    measurements = pandoc.json.decode(handle:read("*a"))
    handle:close()
  end
  return pandoc.Pandoc(doc.blocks:walk({Table = format_table}), doc.meta)
end

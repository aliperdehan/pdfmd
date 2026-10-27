-- ~95 characters is a commonly-cited rule of thumb for how much 12pt serif
-- text fits on one line within a standard 1in-margin A4/Letter page -- see
-- the long comment above this filter's Python source for what this is and
-- is not measuring, and why an estimate is all that's available here.
local CHAR_BUDGET = 95
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
-- (same reasoning as CHAR_BUDGET above -- no font has been measured yet
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

local function cell_length(cell)
  local length = #pandoc.utils.stringify(cell.contents) - math_overcount(cell.contents)
  if length < 1 then length = 1 end
  return length
end


-- Where a table's text goes: for every column, the length of each row's cell, so that the height a row
-- takes at a given column width can be worked out (a row is as tall as its tallest cell).
local function collect(tbl)
  local ncols = #tbl.colspecs
  local rows, longest, word = {}, {}, {}
  for i = 1, ncols do longest[i] = 1; word[i] = 1 end
  local function add(row)
    local lengths = {}
    for i = 1, ncols do lengths[i] = 0 end
    for i, cell in ipairs(row.cells) do
      local span = cell.col_span or 1
      local share = math.max(1, math.ceil(cell_length(cell) / span))
      local widest = 1
      for text in pandoc.utils.stringify(cell.contents):gmatch("%S+") do
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
  return rows, longest, word
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
local function best_widths(rows, longest, word, room)
  local n = #longest
  local widths, floor_sum = {}, 0
  for c = 1, n do
    widths[c] = math.min(word[c], longest[c])
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
      local spare = longest[c] - widths[c]
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
  if remaining > 0 then                -- nothing buys a line any more: let the long cells breathe
    local wanted = 0
    for c = 1, n do wanted = wanted + (longest[c] - widths[c]) end
    if wanted > 0 then
      local share = math.min(1, remaining / wanted)
      for c = 1, n do widths[c] = widths[c] + (longest[c] - widths[c]) * share end
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
local tables_seen = 0           -- the table's place in the document: engines tried one after the other count it once
local function report(kind)
  local path = os.getenv("PDFMD_TABLEWIDTH_LOG")
  if path == nil or path == "" then return end
  local handle = io.open(path, "a")
  if handle then
    handle:write(tables_seen .. (kind or "") .. "\n")
    handle:close()
  end
end

-- Widths the author chose are kept, except for one thing nobody chooses: a column too narrow for its own longest
-- word, which LaTeX then breaks in the middle ("Sus-tained"). Such a column is raised to that word (a word longer
-- than WORD_CAP characters, a URL say, is not worth the room) and the other columns give up the space in
-- proportion to what they were given, none below its own floor. A table where every column already holds its
-- longest word is returned untouched; one whose floors do not fit at all keeps the choice.
local WORD_CAP = 16

local function keep_words(tbl)
  local ncols = #tbl.colspecs
  local _, longest, word = collect(tbl)
  local room = CHAR_BUDGET - ncols * PER_COLUMN_OVERHEAD
  local floor_, chars, floor_sum, short = {}, {}, 0, false
  for c = 1, ncols do
    floor_[c] = math.min(word[c], longest[c], WORD_CAP)
    chars[c] = tbl.colspecs[c][2] * room
    floor_sum = floor_sum + floor_[c]
    if chars[c] < floor_[c] - 1e-9 then short = true end
  end
  if not short or floor_sum >= room then return nil end
  local widths, locked = {}, {}
  for c = 1, ncols do
    if chars[c] < floor_[c] then widths[c] = floor_[c]; locked[c] = true end
  end
  local changed = true
  while changed do
    changed = false
    local left, free = room, 0
    for c = 1, ncols do
      if locked[c] then left = left - widths[c] else free = free + chars[c] end
    end
    for c = 1, ncols do
      if not locked[c] then
        widths[c] = chars[c] * left / free
        if widths[c] < floor_[c] then widths[c] = floor_[c]; locked[c] = true; changed = true end
      end
    end
  end
  for c, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[c] = {spec[1], widths[c] / room}
  end
  report("w")
  return tbl
end

-- The two settings, set from the metadata before the walk (see Pandoc below), and a table's own attributes
-- (`{widths=force word-floor=off}` after its caption) win over them. widths: auto (equal dashes are "no opinion",
-- unequal ones a choice), keep (every table as written), force (the dashes are ignored, every table is balanced).
-- word-floor: on or off, whether a chosen column is raised to its longest word.
local MODE, FLOOR = "auto", true
local MODES = {auto = true, keep = true, force = true}
local SWITCH = {on = true, ["true"] = true, yes = true, off = false, ["false"] = false, no = false}

local function rebalance(tbl)
  tables_seen = tables_seen + 1
  local ncols = #tbl.colspecs
  if ncols == 0 then return nil end
  local attributes = tbl.attr.attributes
  if attributes["data-pdfmd-widths"] == "fixed" then return nil end     -- widths= on a .csv div
  local mode, floor = MODE, FLOOR
  if attributes["widths"] ~= nil then
    local given = attributes["widths"]:lower()
    if MODES[given] then mode = given end
    attributes["widths"] = nil
  end
  if attributes["word-floor"] ~= nil then
    local given = SWITCH[attributes["word-floor"]:lower()]
    if given ~= nil then floor = given end
    attributes["word-floor"] = nil
  end
  if mode == "keep" then return nil end
  local chosen = not has_default(tbl.colspecs) and not equal_widths(tbl.colspecs) and mode ~= "force"
  if chosen then
    if floor then return keep_words(tbl) end
    return nil
  end
  if ncols == 1 and not has_default(tbl.colspecs) then
    tbl.colspecs[1] = {tbl.colspecs[1][1]}
    return tbl
  end

  local rows, longest, word = collect(tbl)
  local total = 0
  for i = 1, ncols do total = total + longest[i] end
  -- The table's own content already fits a line: leave it at its natural size (and give back the natural
  -- size to a table whose equal widths were only the separator's), rather than stretching a table nobody
  -- asked to have stretched.
  if total + ncols * PER_COLUMN_OVERHEAD <= CHAR_BUDGET then
    if has_default(tbl.colspecs) then return nil end
    for i, spec in ipairs(tbl.colspecs) do tbl.colspecs[i] = {spec[1]} end
    return tbl
  end

  local widths = best_widths(rows, longest, word, CHAR_BUDGET - ncols * PER_COLUMN_OVERHEAD)
  local sum = 0
  for i = 1, ncols do sum = sum + widths[i] end
  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = {spec[1], widths[i] / sum}
  end
  report()
  return tbl
end

-- A setting comes from the document's own `pdfmd-options` first, then from the global one pdfmd hands over
-- (`-M pdfmd-table-widths=...`, from the config or --setup).
local function setting(meta, name)
  local options = meta["pdfmd-options"]
  local value = nil
  if options ~= nil then value = options[name] end                    -- YAML `off` is the boolean false
  if value == nil then value = meta["pdfmd-" .. name] end
  if value == nil then return nil end
  return pandoc.utils.stringify(value):lower()
end

function Pandoc(doc)
  local mode = setting(doc.meta, "table-widths")
  if mode ~= nil and MODES[mode] then MODE = mode end
  local floor = SWITCH[setting(doc.meta, "table-word-floor") or ""]
  if floor ~= nil then FLOOR = floor end
  return pandoc.Pandoc(doc.blocks:walk({Table = rebalance}), doc.meta)
end

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

local function rebalance(tbl)
  local ncols = #tbl.colspecs
  if ncols == 0 then return nil end
  if tbl.attr.attributes["data-pdfmd-widths"] == "fixed" then return nil end     -- widths= on a .csv div
  local chosen = not has_default(tbl.colspecs) and not equal_widths(tbl.colspecs)
  if chosen then return nil end
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
  return tbl
end

-- `table-widths: keep` (pdfmd-options, or the global setting) leaves every table as the document wrote it.
local function setting(meta)
  local value = meta["pdfmd-table-widths"]
  local options = meta["pdfmd-options"]
  if value == nil and options ~= nil and options["table-widths"] ~= nil then value = options["table-widths"] end
  return value and pandoc.utils.stringify(value) or "auto"
end

function Pandoc(doc)
  if setting(doc.meta) == "keep" then return nil end
  return pandoc.Pandoc(doc.blocks:walk({Table = rebalance}), doc.meta)
end

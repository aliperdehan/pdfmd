--[[ pdfmd_office/office.lua -- LaTeX the document uses, made native for Word/OpenDocument output.

Pandoc writes `$x^2$` as a Word equation and nothing else of LaTeX: `\ce{H2O}` stays literal text, a
`\begin{equation}` block is dropped, raw `figure`/`tabular` environments vanish. This filter climbs a
ladder, native first:

  1. math Pandoc can convert (texmath) is left alone;
  2. mhchem `\ce{}` and siunitx `\si{} \SI{}{} \num{}` are translated, in math and in text;
  3. raw LaTeX that Pandoc's own LaTeX reader understands (figure, tabular, lists, \emph, ...) is read;
  4. what is left is recorded (pdfmd renders it to an image, or reports it).

Settings arrive in metadata `pdfmd-office` (set by pdfmd): `latex` (auto | off), `report` (a file to
write the list of left-over fragments to).
]]

local stringify = pandoc.utils.stringify
local settings = {latex = "auto", report = nil}
local equation_block   -- defined below
local current_meta     -- the document's metadata, for a profile
local profile = {ignore = {}, commands = {}}   -- a house style's own macros (office.lua beside the document)
local labels, crefnames, caption_sep, cref_capital = {}, {}, ". ", true
local counters_by = {equation = 0, figure = 0, table = 0}
local left_over = {}      -- {kind=, tex=}
local counters = {math = 0, native = 0}

---------------------------------------------------------------------------
-- small helpers

local function trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

-- the {...} group starting at or after `pos`: content, position after it
local function group(s, pos)
  local start = s:find("{", pos, true)
  if not start then return nil end
  local depth, i = 0, start
  while i <= #s do
    local c = s:sub(i, i)
    if c == "\\" then i = i + 1
    elseif c == "{" then depth = depth + 1
    elseif c == "}" then
      depth = depth - 1
      if depth == 0 then return s:sub(start + 1, i - 1), i + 1 end
    end
    i = i + 1
  end
  return nil
end

-- the optional [...] argument at `pos` (right there, whitespace allowed): content, position after
local function optional(s, pos)
  local a = s:match("^%s*%[()", pos)
  if not a then return nil, pos end
  local b = s:find("]", a, true)
  if not b then return nil, pos end
  return s:sub(a, b - 1), b + 1
end

local function record(kind, tex)
  left_over[#left_over + 1] = {kind = kind, tex = tex}
end

---------------------------------------------------------------------------
-- fragments: what cannot be native is drawn by LaTeX (pdfmd compiles it between two runs of this filter)
-- mode "collect": note the fragment; mode "render": use the picture pdfmd made (or leave the piece out)

local wanted = {}          -- id -> {kind, tex}
local wanted_order = {}
local fragment_meta = {}

local function counter_prefix(tex)
  local label = tex:match("\\label%s*{([^}]*)}")
  local entry = label and labels[label]
  if entry and entry.type and entry.type ~= "" and tonumber(entry.num) then
    local counter = (entry.type == "equation" or entry.type == "figure" or entry.type == "table") and entry.type or nil
    if counter then return string.format("\\setcounter{%s}{%d}", counter, tonumber(entry.num) - 1) end
  end
  return ""
end

-- the picture of a fragment as an Image, or nil (collect mode, or no picture)
local function fragment_image(kind, tex)
  if settings.mode ~= "collect" and settings.mode ~= "render" then return nil end
  tex = counter_prefix(tex) .. tex
  local id = pandoc.sha1(kind .. "\0" .. tex)
  if settings.mode == "collect" then
    if not wanted[id] then wanted[id] = {id = id, kind = kind, tex = tex}; wanted_order[#wanted_order + 1] = id end
    return nil
  end
  if fragment_meta[id] == nil then
    local file = io.open(settings.fragments .. "/" .. id .. ".json", "r")
    if file then
      local ok, data = pcall(pandoc.json.decode, file:read("a"), false)
      file:close()
      fragment_meta[id] = ok and data or false
    else fragment_meta[id] = false end
  end
  local meta = fragment_meta[id]
  if not meta then return nil end
  local src = (FORMAT == "docx") and meta.png or meta.svg
  local width, height = meta.width, meta.height
  local alt = ("LaTeX: " .. tex:gsub("%s+", " ")):sub(1, 160)
  local attrs = {{"width", string.format("%.2fpt", width)}, {"height", string.format("%.2fpt", height)}}
  local title = "pdfmd:svg=" .. meta.svg .. ";dp=" .. string.format("%.3f", meta.depth or 0)
  return pandoc.Image({pandoc.Str(alt)}, src, title, pandoc.Attr("", {}, attrs))
end

---------------------------------------------------------------------------
-- units (siunitx)

local PREFIX = {
  yocto = "y", zepto = "z", atto = "a", femto = "f", pico = "p", nano = "n", micro = "µ", milli = "m",
  centi = "c", deci = "d", deca = "da", hecto = "h", kilo = "k", mega = "M", giga = "G", tera = "T", peta = "P",
}
local UNIT = {
  gram = "g", liter = "L", litre = "L", meter = "m", metre = "m", second = "s", mole = "mol", molar = "M",
  kelvin = "K", ampere = "A", candela = "cd", hertz = "Hz", newton = "N", pascal = "Pa", joule = "J",
  watt = "W", coulomb = "C", volt = "V", farad = "F", ohm = "Ω", siemens = "S", weber = "Wb", tesla = "T",
  henry = "H", lumen = "lm", lux = "lx", becquerel = "Bq", gray = "Gy", sievert = "Sv", katal = "kat",
  celsius = "°C", degreeCelsius = "°C", degree = "°", arcminute = "′", arcsecond = "″",
  minute = "min", hour = "h", day = "d", bar = "bar", atm = "atm", torr = "torr", angstrom = "Å",
  percent = "%", dalton = "Da", electronvolt = "eV", tonne = "t", hectare = "ha", mmHg = "mmHg",
  calorie = "cal", ppm = "ppm", ppb = "ppb", molal = "m", dB = "dB", bit = "bit", byte = "B", psi = "psi",
  rpm = "rpm", gauss = "G", debye = "D", neper = "Np", radian = "rad", steradian = "sr", fg = "fg",
}
local POWER = {squared = 2, cubed = 3, tothe = false}

-- "\gram\per\milli\liter" -> { {sym="g", pow=1}, {sym="mL", pow=-1} }; nil when a macro is unknown
local function parse_unit(s)
  local out, per, pending, power = {}, false, "", nil
  local i = 1
  s = s:gsub("%s+", " ")
  while i <= #s do
    local c = s:sub(i, i)
    if c == "\\" then
      local name = s:match("^\\([%a]+)", i)
      if not name then return nil end
      i = i + 1 + #name
      if name == "per" then per = true; pending = ""
      elseif name == "squared" or name == "cubed" then
        if #out == 0 then return nil end
        out[#out].pow = out[#out].pow * (name == "squared" and 2 or 3)
      elseif name == "tothe" then
        local arg, nxt = group(s, i)
        if not arg or #out == 0 or not tonumber(arg) then return nil end
        out[#out].pow = out[#out].pow * tonumber(arg); i = nxt
      elseif name == "cdot" or name == "times" then pending = ""
      elseif PREFIX[name] then pending = pending .. PREFIX[name]
      elseif UNIT[name] then
        out[#out + 1] = {sym = pending .. UNIT[name], pow = per and -1 or 1}
        pending = ""
      else return nil end
    elseif c == "^" then
      local arg, nxt = s:match("^%^{?(%-?%d+)}?()", i)
      if not arg or #out == 0 then return nil end
      out[#out].pow = out[#out].pow * tonumber(arg); i = nxt
    elseif c == " " or c == "." then i = i + 1
    elseif c:match("[%a°%%]") then   -- a bare symbol such as `m` or `mol`
      local word = s:match("^[%a°%%]+", i)
      out[#out + 1] = {sym = pending .. word, pow = per and -1 or 1}
      pending = ""; i = i + #word
    else return nil end
  end
  if #out == 0 then return nil end
  return out
end

local SUP = {["-"] = "−", ["0"] = "0", ["1"] = "1", ["2"] = "2", ["3"] = "3", ["4"] = "4", ["5"] = "5",
             ["6"] = "6", ["7"] = "7", ["8"] = "8", ["9"] = "9"}
local function sup_text(n)
  return (tostring(n):gsub(".", function(ch) return SUP[ch] or ch end))
end

local function unit_math(units)
  local parts = {}
  for _, u in ipairs(units) do
    local sym = "\\text{" .. u.sym:gsub("%%", "\\%%") .. "}"
    if u.sym == "°C" then sym = "\\text{°C}" end
    if u.pow ~= 1 then sym = sym .. "^{" .. u.pow .. "}" end
    parts[#parts + 1] = sym
  end
  return table.concat(parts, "\\,")
end

local function unit_inlines(units)
  local out = {}
  for index, u in ipairs(units) do
    if index > 1 then out[#out + 1] = pandoc.Str("\u{00A0}") end
    out[#out + 1] = pandoc.Str(u.sym)
    if u.pow ~= 1 then out[#out + 1] = pandoc.Superscript({pandoc.Str(sup_text(u.pow))}) end
  end
  return out
end

-- siunitx number: 1.5e-3 -> {text="1.5 × 10", exp="−3"}
local function number_parts(s)
  s = trim(s):gsub("[{}]", "")
  local mantissa, exp = s:match("^(.-)[eE]([+-]?%d+)$")
  if not mantissa then return (s:gsub("%+%-", "±"):gsub("%-", "−")), nil end
  mantissa = mantissa:gsub("%-", "−")
  return mantissa .. "\u{00A0}×\u{00A0}10", (tostring(tonumber(exp)):gsub("%-", "−"))
end

local function number_math(s)
  s = trim(s):gsub("[{}]", "")
  local mantissa, exp = s:match("^(.-)[eE]([+-]?%d+)$")
  if mantissa then return mantissa .. "\\times 10^{" .. tonumber(exp) .. "}" end
  return (s:gsub("%+%-", "\\pm "))
end

---------------------------------------------------------------------------
-- mhchem \ce{...}

local ARROWS = {
  {"<=>", "⇌", "\\rightleftharpoons"}, {"<->", "⟷", "\\longleftrightarrow"}, {"<-->", "⟷", "\\longleftrightarrow"},
  {"-->", "⟶", "\\longrightarrow"}, {"->", "⟶", "\\longrightarrow"}, {"<--", "⟵", "\\longleftarrow"},
  {"<-", "⟵", "\\longleftarrow"}, {"<=", "⇐", "\\Leftarrow"}, {"=>", "⇒", "\\Rightarrow"},
}

-- one species such as `2Ag+(aq)`, `SO4^2-`, `(NH4)2SO4`, `[Cu(NH3)4]^2+`, `CuSO4.5H2O`
-- -> list of parts {t = text, sub = , sup = } or nil
local function species(word)
  local parts = {}
  local i = 1
  local coefficient = word:match("^(%d+)%a") or word:match("^(%d+)[%(%[]")
  if coefficient then
    parts[#parts + 1] = {t = coefficient, coef = true}
    i = #coefficient + 1
  end
  local function push(t) parts[#parts + 1] = {t = t} end
  while i <= #word do
    local c = word:sub(i, i)
    if c:match("%u") then
      local el = word:match("^%u%l?", i)
      push(el); i = i + #el
    elseif c:match("%l") then          -- R-groups and lower-case labels (e.g. `aq`, `x`)
      push(c); i = i + 1
    elseif c:match("%d") then
      local digits = word:match("^%d+", i)
      local last = parts[#parts]
      if not last then return nil end
      if last.coef or last.dot then parts[#parts + 1] = {t = digits, coef = true}   -- 5 in CuSO4.5H2O
      else last.sub = (last.sub or "") .. digits end
      i = i + #digits
    elseif c == "(" or c == "[" then
      -- a state label (aq) (s) (l) (g) stays text; other groups open normally
      local state = word:match("^%((aq)%)", i) or word:match("^%((s)%)", i) or word:match("^%((l)%)", i)
          or word:match("^%((g)%)", i) or word:match("^%((cr)%)", i)
      if c == "(" and state then push("(" .. state .. ")"); i = i + #state + 2
      else push(c); i = i + 1 end
    elseif c == ")" or c == "]" then
      push(c); i = i + 1
    elseif c == "^" then
      local arg, nxt = group(word, i + 1)
      if arg then
        local last = parts[#parts]
        if not last then return nil end
        last.sup = arg:gsub("%-", "−"); i = nxt
      else
        local tail = word:match("^%^(%d*[%+%-]?)", i)
        local last = parts[#parts]
        if not last or tail == "" then return nil end
        last.sup = tail:gsub("%-", "−"); i = i + 1 + #tail
      end
    elseif c == "_" then
      local arg, nxt = group(word, i + 1)
      local last = parts[#parts]
      if not arg or not last then return nil end
      last.sub = arg; i = nxt
    elseif c == "+" or c == "-" then
      -- a charge when it follows a species and is not followed by another species
      local last = parts[#parts]
      local nextc = word:sub(i + 1, i + 1)
      local charge = last and not last.coef and not last.dot and not last.bond
      if charge and c == "-" and nextc:match("%a") then charge = false end   -- a bond: R-O, C-Cl
      if charge then
        local sign = (c == "-") and "−" or "+"
        last.sup = (last.sup or "") .. sign; i = i + 1
      elseif c == "-" then
        push("-"); parts[#parts].bond = true; i = i + 1
      else push("+"); i = i + 1 end
    elseif c == "." or c == "*" then
      push("·"); parts[#parts].dot = true; i = i + 1
    elseif c == "{" then
      local arg, nxt = group(word, i)
      if not arg then return nil end
      push(arg); i = nxt
    elseif c == "\\" then
      local name = word:match("^\\(%a+)", i)
      if name == "Delta" then push("Δ"); i = i + 6
      elseif name == "text" then
        local arg, nxt = group(word, i)
        if not arg then return nil end
        push(arg); i = nxt
      else return nil end
    else return nil end
  end
  return parts
end

local function ce_parse(src)
  src = trim(src)
  local out, i = {}, 1
  while i <= #src do
    local c = src:sub(i, i)
    if c:match("%s") then
      i = i + 1
      out[#out + 1] = {kind = "space"}
    else
      local arrow
      for _, a in ipairs(ARROWS) do
        if src:sub(i, i + #a[1] - 1) == a[1] then arrow = a; break end
      end
      if arrow then
        -- arrow decorations: ->[above][below]
        i = i + #arrow[1]
        local above, below
        above, i = optional(src, i)
        if above then below, i = optional(src, i) end
        out[#out + 1] = {kind = "arrow", text = arrow[2], math = arrow[3], above = above, below = below}
      else
        -- a word runs to the next space or arrow
        local j = i
        while j <= #src do
          local d = src:sub(j, j)
          if d:match("%s") then break end
          local at_arrow = false
          for _, a in ipairs(ARROWS) do
            if j > i and src:sub(j, j + #a[1] - 1) == a[1] then at_arrow = true end
          end
          if at_arrow then break end
          if d == "{" then local _, nxt = group(src, j); j = (nxt or j + 1) else j = j + 1 end
        end
        local word = src:sub(i, j - 1)
        if word == "+" then out[#out + 1] = {kind = "plus"}
        elseif word == "-" then out[#out + 1] = {kind = "minus"}
        else
          local parts = species(word)
          if not parts then return nil end
          out[#out + 1] = {kind = "species", parts = parts}
        end
        i = j
      end
    end
  end
  return out
end

local function ce_math(tokens)
  local out = {}
  local run = ""
  local function flush()
    if run ~= "" then out[#out + 1] = "\\text{" .. run .. "}"; run = "" end
  end
  local function mathrm(text) return "\\text{" .. text:gsub("%%", "\\%%") .. "}" end
  for _, t in ipairs(tokens) do
    if t.kind == "space" then
      flush(); if #out > 0 and out[#out] ~= "\\ " then out[#out + 1] = "\\ " end
    elseif t.kind == "plus" then flush(); out[#out + 1] = "+"
    elseif t.kind == "minus" then flush(); out[#out + 1] = "-"
    elseif t.kind == "arrow" then
      flush()
      local arrow = t.math
      if t.above or t.below then
        if t.math == "\\rightleftharpoons" then
          arrow = "\\overset{" .. mathrm(t.above or "") .. "}{" .. (t.below and ("\\underset{" .. mathrm(t.below) .. "}{\\rightleftharpoons}") or "\\rightleftharpoons") .. "}"
        else
          arrow = "\\xrightarrow" .. (t.below and ("[" .. mathrm(t.below) .. "]") or "") .. "{" .. mathrm(t.above or "") .. "}"
        end
      end
      out[#out + 1] = arrow
    else
      for _, p in ipairs(t.parts) do
        if p.coef then flush(); out[#out + 1] = p.t .. "\\,"
        elseif p.bond then flush(); out[#out + 1] = "\\text{-}"
        elseif p.sub or p.sup then
          flush()
          local text = mathrm(p.t)
          if p.sub then text = text .. "_{" .. p.sub .. "}" end
          if p.sup then text = text .. "^{" .. p.sup .. "}" end
          out[#out + 1] = text
        else run = run .. p.t end
      end
    end
  end
  flush()
  return (table.concat(out):gsub("−", "-"))
end

local function ce_inlines(tokens)
  local out = {}
  local function add(x) out[#out + 1] = x end
  for _, t in ipairs(tokens) do
    if t.kind == "space" then add(pandoc.Space())
    elseif t.kind == "plus" then add(pandoc.Str("+"))
    elseif t.kind == "minus" then add(pandoc.Str("−"))
    elseif t.kind == "arrow" then
      add(pandoc.Str(t.text))
    else
      for _, p in ipairs(t.parts) do
        add(pandoc.Str(p.t))
        if p.sub then add(pandoc.Subscript({pandoc.Str(p.sub)})) end
        if p.sup then add(pandoc.Superscript({pandoc.Str(p.sup)})) end
      end
    end
  end
  -- `2` `Ag` ... : a coefficient is followed by a thin space
  return out
end

---------------------------------------------------------------------------
-- macro translation shared by math and text

-- Replace \ce{..}, \si{..}, \SI{..}{..}, \num{..}, \qty{..}{..} in a math string. nil when one fails.
local function math_translate(tex)
  local out, i = {}, 1
  while i <= #tex do
    local at = tex:find("\\", i, true)
    if not at then out[#out + 1] = tex:sub(i); break end
    out[#out + 1] = tex:sub(i, at - 1)
    local name = tex:match("^\\(%a+)", at)
    local after = at + 1 + (name and #name or 0)
    if name == "ce" then
      local arg, nxt = group(tex, after)
      local tokens = arg and ce_parse(arg)
      if not tokens then return nil end
      out[#out + 1] = ce_math(tokens); i = nxt
    elseif name == "si" or name == "unit" then
      local _, after_opt = optional(tex, after)
      local arg, nxt = group(tex, after_opt)
      local units = arg and parse_unit(arg)
      if not units then return nil end
      out[#out + 1] = unit_math(units); i = nxt
    elseif name == "SI" or name == "qty" then
      local _, after_opt = optional(tex, after)
      local number, n1 = group(tex, after_opt)
      local unit, n2 = nil, nil
      if number then unit, n2 = group(tex, n1) end
      local units = unit and parse_unit(unit)
      if not units then return nil end
      out[#out + 1] = number_math(number) .. "\\," .. unit_math(units); i = n2
    elseif name == "num" then
      local _, after_opt = optional(tex, after)
      local arg, nxt = group(tex, after_opt)
      if not arg then return nil end
      out[#out + 1] = number_math(arg); i = nxt
    elseif name == "xoverline" then
      local _, after_opt = optional(tex, after)
      out[#out + 1] = "\\overline"; i = after_opt
    else
      out[#out + 1] = tex:sub(at, after - 1) ; i = after
      if not name then out[#out + 1] = tex:sub(at + 1, at + 1); i = at + 2 end
    end
  end
  return table.concat(out)
end

local math_cache = {}
local mathml = pandoc.WriterOptions({html_math_method = "mathml"})

-- does Pandoc's own converter (texmath) understand this math? A failure leaves literal TeX in the output.
local function math_native(tex, display)
  local key = (display and "D" or "I") .. tex
  if math_cache[key] ~= nil then return math_cache[key] end
  local kind = display and "DisplayMath" or "InlineMath"
  local result = false
  pandoc.log.silence(function()
    local ok, html = pcall(pandoc.write, pandoc.Pandoc({pandoc.Plain({pandoc.Math(kind, tex)})}), "html", mathml)
    result = ok and html:find("<math", 1, true) ~= nil
  end)
  math_cache[key] = result
  return result
end

---------------------------------------------------------------------------
-- references: \\ref \\eqref \\cref \\Cref \\autoref \\pageref, numbers from LaTeX's own .aux

local function split_labels(arg)
  local out = {}
  for label in arg:gmatch("[^,]+") do out[#out + 1] = trim(label) end
  return out
end

local function number_of(label)
  local entry = labels[label]
  return entry and entry.num ~= "" and entry.num or nil
end

local function names_for(kind, capital)
  local names = crefnames[kind]
  local singular = names and names[1] or (kind:sub(1, 1):upper() .. kind:sub(2))
  local plural = names and names[2] or (singular .. "s")
  if not capital then singular, plural = singular:lower(), plural:lower() end
  return singular, plural
end

-- "Equation (1)", "Figures 2 and 3", "Tables 1, 2, and 3"
local function cref_text(list, capital)
  local groups = {}
  for _, label in ipairs(list) do
    local entry = labels[label]
    if not entry or not number_of(label) then return nil end
    local kind = entry.type ~= "" and entry.type or "section"
    local last = groups[#groups]
    if last and last.kind == kind then last.numbers[#last.numbers + 1] = entry.num
    else groups[#groups + 1] = {kind = kind, numbers = {entry.num}} end
  end
  local pieces = {}
  for _, g in ipairs(groups) do
    local shown = {}
    for _, n in ipairs(g.numbers) do shown[#shown + 1] = (g.kind == "equation") and ("(" .. n .. ")") or n end
    local text
    if #shown == 1 then text = shown[1]
    elseif #shown == 2 then text = shown[1] .. " and " .. shown[2]
    else text = table.concat(shown, ", ", 1, #shown - 1) .. ", and " .. shown[#shown] end
    local singular, plural = names_for(g.kind, capital)
    pieces[#pieces + 1] = (#shown == 1 and singular or plural) .. "\u{00A0}" .. text
  end
  if #pieces == 1 then return pieces[1] end
  if #pieces == 2 then return pieces[1] .. " and " .. pieces[2] end
  return table.concat(pieces, ", ", 1, #pieces - 1) .. ", and " .. pieces[#pieces]
end

local function ref_inlines(raw)
  local name, rest = raw:match("^\\([%a]+)%*?()")
  if not name then return nil end
  local arg = group(raw, rest)
  if not arg or trim(raw:sub(select(2, group(raw, rest)))) ~= "" then return nil end
  local list = split_labels(arg)
  local text
  if name == "ref" or name == "labelcref" or name == "vref" then
    local parts = {}
    for _, label in ipairs(list) do
      local n = number_of(label)
      if not n then return nil end
      parts[#parts + 1] = n
    end
    text = table.concat(parts, ", ")
  elseif name == "eqref" then
    local parts = {}
    for _, label in ipairs(list) do
      local n = number_of(label)
      if not n then return nil end
      parts[#parts + 1] = "(" .. n .. ")"
    end
    text = table.concat(parts, ", ")
  elseif name == "pageref" or name == "cpageref" then
    local parts = {}
    for _, label in ipairs(list) do
      local entry = labels[label]
      if not entry or entry.page == "" then return nil end
      parts[#parts + 1] = entry.page
    end
    text = (name == "cpageref" and "page\u{00A0}" or "") .. table.concat(parts, ", ")
  elseif name == "cref" or name == "Cref" or name == "autoref" then
    text = cref_text(list, name == "Cref" or name == "autoref" or cref_capital)
  else
    return nil
  end
  if not text then return nil end
  local inline = pandoc.Str(text)
  if #list == 1 and labels[list[1]] then
    return {pandoc.Link({inline}, "#" .. list[1], "", pandoc.Attr("", {"pdfmd-ref"}))}
  end
  return {inline}
end

-- captions: "Figure 3. " in front of a figure's or table's caption, as the PDF prints it
local function caption_label(kind)
  return (kind == "figure") and "Figure" or "Table"
end

local function number_caption(el, kind)
  local caption = el.caption
  if not caption or not caption.long or #caption.long == 0 then return nil end
  local identifier = el.identifier or (el.attr and el.attr.identifier) or ""
  local entry = identifier ~= "" and labels[identifier] or nil
  local number
  if entry and entry.num ~= "" then
    number = entry.num
    counters_by[kind] = tonumber(number) or counters_by[kind] + 1
  else
    counters_by[kind] = counters_by[kind] + 1
    number = tostring(counters_by[kind])
  end
  local first = caption.long[1]
  if first.t == "Plain" or first.t == "Para" then
    table.insert(first.content, 1, pandoc.Str(caption_label(kind) .. "\u{00A0}" .. number .. caption_sep))
  end
  return el
end

---------------------------------------------------------------------------
-- the filter

local function off() return settings.latex == "off" end

function Math(el)
  if off() then return nil end
  local display = el.mathtype == "DisplayMath"
  local text = el.text
  local translated = math_translate(text)
  if translated == nil or not math_native(translated, display) then
    local image = fragment_image(display and "math-display" or "math-inline", text)
    if image then return image end
    record("math", text)
    return nil
  end
  if translated ~= text then counters.math = counters.math + 1 end
  if translated ~= text then return pandoc.Math(el.mathtype, translated) end
  return nil
end

local function inlines_of(blocks)
  if #blocks == 1 and (blocks[1].t == "Para" or blocks[1].t == "Plain") then return blocks[1].content end
  return nil
end

-- text-level commands handled directly
local function text_command(raw)
  local name = raw:match("^\\(%a+)")
  if not name then return nil end
  if name == "ce" then
    local arg, nxt = group(raw, #name + 2)
    if arg and trim(raw:sub(nxt)) == "" then
      local tokens = ce_parse(arg)
      if tokens then return ce_inlines(tokens) end
    end
  elseif name == "si" or name == "unit" or name == "SI" or name == "qty" or name == "num" then
    local _, p = optional(raw, #name + 2)
    local first, n1 = group(raw, p)
    if not first then return nil end
    if name == "num" then
      local text, exp = number_parts(first)
      local out = {pandoc.Str(text)}
      if exp then out[#out + 1] = pandoc.Superscript({pandoc.Str(exp)}) end
      return out
    elseif name == "si" or name == "unit" then
      local units = parse_unit(first)
      return units and unit_inlines(units) or nil
    else
      local second = group(raw, n1)
      local units = second and parse_unit(second)
      if not units then return nil end
      local text, exp = number_parts(first)
      local out = {pandoc.Str(text)}
      if exp then out[#out + 1] = pandoc.Superscript({pandoc.Str(exp)}) end
      out[#out + 1] = pandoc.Str("\u{00A0}")
      for _, item in ipairs(unit_inlines(units)) do out[#out + 1] = item end
      return out
    end
  elseif name == "newline" or name == "linebreak" then return {pandoc.LineBreak()}
  elseif name == "label" then return {}
  elseif name == "relax" or name == "noindent" or name == "centering" or name == "protect" or name == "xspace"
      or name == "ignorespaces" or name == "par" or name == "hfill" or name == "quad" or name == "qquad" then
    return {pandoc.Space()}
  end
  return nil
end

local MATH_ENVS = {equation = "", align = "aligned", gather = "gathered", multline = "gathered",
                   eqnarray = "aligned", flalign = "aligned", alignat = "aligned", reaction = "", split = "split"}

local function math_block(raw)
  local env, star, body = raw:match("^\\begin{(%a+)(%*?)}(.*)\\end{%1%*?}%s*$")
  if not env or MATH_ENVS[env] == nil then return nil end
  local labels = {}
  body = body:gsub("\\label%b{}", function(l) labels[#labels + 1] = l:sub(8, -2); return "" end)
  body = body:gsub("\\nonumber", ""):gsub("\\notag", "")
  body = trim(body)
  if env == "alignat" then body = body:gsub("^%b{}", "") end
  local wrapper = MATH_ENVS[env]
  local tex = body
  if wrapper ~= "" then tex = "\\begin{" .. wrapper .. "}" .. body .. "\\end{" .. wrapper .. "}" end
  if env == "reaction" then tex = body end
  return tex, labels, star == "*"
end

-- every {group} argument after a command name, and what follows them
local function command_args(raw)
  local name, position = raw:match("^\\(%a+)%*?()")
  if not name then return nil end
  local args = {}
  while true do
    local _, after_optional = optional(raw, position)
    local brace = raw:match("^%s*(){", after_optional)
    if not brace then break end
    local content, nxt = group(raw, brace)
    if not content then break end
    args[#args + 1] = content
    position = nxt
  end
  return name, args, trim(raw:sub(position))
end

local helpers = {
  inlines = function(tex)
    local ok, doc = pcall(pandoc.read, tex, "latex")
    if ok then return inlines_of(doc.blocks) end
    return nil
  end,
  blocks = function(tex)
    local ok, doc = pcall(pandoc.read, tex, "latex")
    if ok then return doc.blocks end
    return nil
  end,
  group = group, trim = trim,
  labels = function() return labels end,
  -- the text of the document's LaTeX preamble files (the house style's per-course macros live there)
  preamble = function()
    if not settings.preamble then return "" end
    local file = io.open(settings.preamble, "r")
    if not file then return "" end
    local text = file:read("a")
    file:close()
    return text
  end,
  meta = function() return current_meta end,
  number_of = function(label) return number_of(label) end,
  fragment = function(kind, tex) return fragment_image(kind, tex) end,
}

local INLINE_TYPES = {Str = true, Space = true, SoftBreak = true, LineBreak = true, Emph = true, Strong = true,
  Underline = true, Strikeout = true, Superscript = true, Subscript = true, SmallCaps = true, Quoted = true,
  Cite = true, Code = true, Math = true, RawInline = true, Link = true, Image = true, Note = true, Span = true}

-- the profile's answer for a command: Inlines/Blocks, {} to drop it, or nil
local function profile_command(raw, as_block)
  local name, args, rest = command_args(raw)
  if not name or rest ~= "" then return nil end
  if profile.ignore[name] then return {} end
  local handler = profile.commands[name]
  if not handler then return nil end
  local ok, result = pcall(handler, args, raw, helpers, as_block)
  if not ok then
    io.stderr:write("[pdfmd] profile command \\" .. name .. " failed: " .. tostring(result) .. "\n")
    return nil
  end
  if type(result) ~= "table" then return nil end
  local first = result[1]
  if as_block and first and INLINE_TYPES[first.t] then return {pandoc.Para(result)} end
  if not as_block and first and not INLINE_TYPES[first.t] then return nil end
  return result
end

function RawInline(el)
  if off() or el.format ~= "latex" and el.format ~= "tex" then return nil end
  local raw = trim(el.text)
  local reference = ref_inlines(raw)
  if reference then counters.native = counters.native + 1; return reference end
  local custom = profile_command(raw, false)
  if custom then counters.native = counters.native + 1; return custom end
  if raw:match("^\\%a*ref%*?{") or raw:match("^\\[cC]ref%*?{") then
    record("reference", raw)
    return {pandoc.Str("??")}
  end
  if raw:match("^\\begin{") then
    local tex, eq_labels, unnumbered = math_block(raw)
    if tex then
      local translated = math_translate(tex)
      if translated and math_native(translated, true) then
        counters.math = counters.math + 1
        return pandoc.Span({pandoc.Math("DisplayMath", translated)}, pandoc.Attr(eq_labels[1] or "", {"pdfmd-equation"},
          {{"labels", table.concat(eq_labels, ",")}, {"numbered", unnumbered and "no" or "yes"}}))
      end
      local image = fragment_image("math-display", tex)
      if image then
        return pandoc.Span({image}, pandoc.Attr(eq_labels[1] or "", {"pdfmd-equation"},
          {{"labels", table.concat(eq_labels, ",")}, {"numbered", unnumbered and "no" or "yes"}}))
      end
      record("equation", raw)
      return nil
    end
  end
  local done = text_command(raw)
  if done then
    counters.native = counters.native + 1
    return done
  end
  if raw == "\\\\" then return pandoc.LineBreak() end
  if raw == "~" then return pandoc.Str("\u{00A0}") end
  -- let Pandoc's own LaTeX reader try (\emph, \textbf, \textsuperscript, \%, ...)
  local ok, doc = pcall(pandoc.read, raw, "latex")
  if ok then
    local inlines = inlines_of(doc.blocks)
    if inlines then
      local raw_left = false
      for _, inline in ipairs(inlines) do if inline.t == "RawInline" then raw_left = true end end
      if not raw_left then
        counters.native = counters.native + 1
        return inlines
      end
    end
  end
  local image = fragment_image("inline", raw)
  if image then return image end
  record("inline", raw)
  return nil
end

local READER_ENVS = {figure = true, table = true, tabular = true, tabularx = true, center = true, itemize = true,
  enumerate = true, description = true, quote = true, quotation = true, verbatim = true, abstract = true,
  flushleft = true, flushright = true, minipage = true, subfigure = true, longtable = true, tabbing = false}

-- only environments Pandoc's LaTeX reader keeps, and no \input (it would read a file it cannot draw)
local function reader_safe(raw)
  if raw:find("\\input%s*{") or raw:find("\\include%s*{") then return false end
  for env in raw:gmatch("\\begin{([%a]+)%*?}") do
    if not READER_ENVS[env] then return false end
  end
  return true
end

-- a PDF/EPS picture cannot go into Word: pdfmd converts it (collect mode names it, render mode swaps it)
local function asset_image(img)
  if off() or (settings.mode ~= "collect" and settings.mode ~= "render") then return nil end
  local ext = img.src:lower():match("%.(%w+)$")
  if ext ~= "pdf" and ext ~= "eps" and ext ~= "ps" then return nil end
  local new = fragment_image("asset", img.src)
  if not new then return nil end
  if img.attributes.width or img.attributes.height then
    new.attributes = img.attributes
  end
  if #img.caption > 0 then new.caption = img.caption end
  new.title = new.title
  return new
end

-- a `figure`/`table` whose body Pandoc cannot read: the body is drawn, the caption stays text
local function captioned_float(raw, env)
  local inner = raw:match("^\\begin{" .. env .. "%*?}%s*%b[]%s*(.*)\\end{" .. env .. "%*?}%s*$")
      or raw:match("^\\begin{" .. env .. "%*?}(.*)\\end{" .. env .. "%*?}%s*$")
  if not inner then return nil end
  local caption, label
  local at = inner:find("\\caption", 1, true)
  if at then
    local _, after_optional = optional(inner, at + 8)
    local text, stop = group(inner, after_optional)
    if text then
      caption = text
      inner = inner:sub(1, at - 1) .. inner:sub(stop)
    end
  end
  if caption then
    label = caption:match("\\label%s*{([^}]*)}")
    caption = caption:gsub("\\label%s*{[^}]*}", "")
  end
  label = label or inner:match("\\label%s*{([^}]*)}")
  inner = inner:gsub("\\label%s*{[^}]*}", ""):gsub("\\centering", ""):gsub("\\noindent", "")
  local image = fragment_image("block", inner)
  if not image then
    if settings.mode == "collect" then return {} end    -- the first run only lists the body
    return nil
  end
  local caption_blocks = {}
  if caption then
    local ok, doc = pcall(pandoc.read, trim(caption), "latex")
    if ok then caption_blocks = doc.blocks end
  end
  local figure = pandoc.Figure({pandoc.Plain({image})}, pandoc.Caption(caption_blocks),
    pandoc.Attr(label or ""))
  return number_caption(figure, env == "table" and "table" or "figure")
end

local PAGE_BREAK
if FORMAT == "docx" then PAGE_BREAK = pandoc.RawBlock("openxml", '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
elseif FORMAT:match("^html") then PAGE_BREAK = pandoc.RawBlock("html", '<div style="page-break-after: always"></div>')
else PAGE_BREAK = {} end

function RawBlock(el)
  if off() or el.format ~= "latex" and el.format ~= "tex" then return nil end
  local raw = trim(el.text)
  -- layout commands a house-style filter wrapped around a block (\par\nointerlineskip ...)
  for _ = 1, 3 do
    raw = trim(raw:gsub("^\\par%s*", ""):gsub("^\\nointerlineskip%s*", ""):gsub("%s*\\par%s*$", ""):gsub("%s*\\nointerlineskip%s*$", ""))
  end
  if raw == "" then return {} end
  local custom = profile_command(raw, true)
  if custom then counters.native = counters.native + 1; return custom end
  local name = raw:match("^\\(%a+)")
  if name == "newpage" or name == "clearpage" or name == "pagebreak" or name == "cleardoublepage" then
    return PAGE_BREAK
  end
  if name == "vspace" or name == "bigskip" or name == "medskip" or name == "smallskip" or name == "noindent"
      or name == "centering" or name == "hfill" or name == "vfill" or name == "label" or name == "thispagestyle"
      or name == "pagestyle" or name == "setlength" or name == "FloatBarrier" or name == "linespread" then
    return {}
  end
  -- \[ ... \] : a display nothing refers to (the house style's filter wraps $$...$$ like this)
  local display = raw:match("^\\%[(.*)\\%]$")
  if display then
    local translated = math_translate(display)
    if translated and math_native(translated, true) then
      counters.math = counters.math + 1
      return pandoc.Para({pandoc.Math("DisplayMath", translated)})
    end
    local image = fragment_image("math-display", display)
    if image then return pandoc.Para({image}) end
    record("equation", raw)
    return nil
  end
  local tex, eq_labels, unnumbered = math_block(raw)
  if tex then
    local translated = math_translate(tex)
    if translated and math_native(translated, true) then
      counters.math = counters.math + 1
      return equation_block(pandoc.Span({pandoc.Math("DisplayMath", translated)}, pandoc.Attr(eq_labels[1] or "", {"pdfmd-equation"},
        {{"labels", table.concat(eq_labels, ",")}, {"numbered", unnumbered and "no" or "yes"}})))
    end
    local image = fragment_image("math-display", tex)
    if image then
      return equation_block(pandoc.Span({image}, pandoc.Attr(eq_labels[1] or "", {"pdfmd-equation"},
        {{"labels", table.concat(eq_labels, ",")}, {"numbered", unnumbered and "no" or "yes"}})))
    end
    record("equation", raw)
    return nil
  end
  -- Pandoc's own LaTeX reader: figure, table, tabular, itemize, center, quote... It silently drops the
  -- environments it does not know (tikzpicture, axis...), so only text made of the ones it does goes through.
  local ok, doc = false, nil
  if reader_safe(raw) then ok, doc = pcall(pandoc.read, raw, "latex") end
  if ok then
    local has_raw = false
    doc:walk({RawBlock = function() has_raw = true end, RawInline = function() has_raw = true end})
    if not has_raw and #doc.blocks > 0 then
      counters.native = counters.native + 1
      -- what the reader made is not seen by the filter again: do its inline work here
      doc = doc:walk({Math = Math, RawInline = RawInline, Image = asset_image})
      doc = doc:walk({Figure = function(f) return number_caption(f, "figure") end,
                      Table = function(t) return number_caption(t, "table") end})
      return doc.blocks
    end
  end
  local env = raw:match("^\\begin{(%a+)%*?}")
  if env == "figure" or env == "table" then
    local figure = captioned_float(raw, env)
    if figure then return figure end
  end
  local image = fragment_image("block", raw)
  if image then return pandoc.Para({image}) end
  record("block", raw)
  return nil
end


-- a display equation with its number at the right, as the PDF sets it: a borderless three-cell table
function equation_block(span)
  local numbered = span.attributes["numbered"] ~= "no"
  local math = span.content[1]
  local mid = pandoc.Plain({math})
  local right = pandoc.Plain({})
  local anchor = span.identifier
  if numbered then
    local entry = anchor ~= "" and labels[anchor] or nil
    local number
    if entry and entry.num ~= "" then
      number = entry.num
      counters_by.equation = tonumber(number) or counters_by.equation + 1
    else
      counters_by.equation = counters_by.equation + 1
      number = tostring(counters_by.equation)
    end
    right = pandoc.Plain({pandoc.Strong({pandoc.Str("(" .. number .. ")")})})
  end
  local function cell(blocks) return pandoc.Cell(blocks) end
  local row = pandoc.Row({cell({}), cell({mid}), cell({right})})
  local table_ = pandoc.Table(pandoc.Caption({}),
    {{pandoc.AlignDefault, 0.1}, {pandoc.AlignCenter, 0.8}, {pandoc.AlignRight, 0.1}},
    pandoc.TableHead({}), {pandoc.TableBody({row})}, pandoc.TableFoot({}),
    pandoc.Attr("", {}, {{"custom-style", "PdfmdEquation"}}))
  if anchor ~= "" then return pandoc.Div({table_}, pandoc.Attr(anchor)) end
  return table_
end

local function is_equation(inline)
  return inline.t == "Span" and inline.classes:includes("pdfmd-equation")
end

function Para(el)
  if off() then return nil end
  local has = false
  for _, inline in ipairs(el.content) do if is_equation(inline) then has = true break end end
  if not has then return nil end
  local out, current = {}, {}
  local function flush()
    -- drop the soft breaks and spaces an equation leaves around itself
    while #current > 0 and (current[#current].t == "SoftBreak" or current[#current].t == "Space") do table.remove(current) end
    while #current > 0 and (current[1].t == "SoftBreak" or current[1].t == "Space") do table.remove(current, 1) end
    if #current > 0 then out[#out + 1] = pandoc.Para(current) end
    current = {}
  end
  for _, inline in ipairs(el.content) do
    if is_equation(inline) then flush(); out[#out + 1] = equation_block(inline)
    else current[#current + 1] = inline end
  end
  flush()
  return out
end

function Figure(el)
  if off() then return nil end
  return number_caption(el, "figure")
end

function Table(el)
  if off() or el.classes:includes("pdfmd-keep") then return nil end
  local style = el.attributes and el.attributes["custom-style"]
  if style == "PdfmdEquation" then return nil end
  return number_caption(el, "table")
end

function Meta(meta)
  current_meta = meta
  if meta["pdfmd-office-latex"] then settings.latex = stringify(meta["pdfmd-office-latex"]) end
  if meta["pdfmd-office-report"] then settings.report = stringify(meta["pdfmd-office-report"]) end
  if meta["pdfmd-office-profile"] then
    local path = stringify(meta["pdfmd-office-profile"])
    local ok, loaded = pcall(dofile, path)
    if ok and type(loaded) == "table" then
      profile.ignore = {}
      for _, name in ipairs(loaded.ignore or {}) do profile.ignore[(name:gsub("^\\", ""))] = true end
      profile.commands = loaded.commands or {}
      profile.pandoc = loaded.pandoc
      profile.name = loaded.name or path
    else
      io.stderr:write("[pdfmd] the office profile " .. path .. " could not be loaded: " .. tostring(loaded) .. "\n")
    end
  end
  if meta["pdfmd-office-preamble"] then settings.preamble = stringify(meta["pdfmd-office-preamble"]) end
  if meta["pdfmd-office-mode"] then settings.mode = stringify(meta["pdfmd-office-mode"]) end
  if meta["pdfmd-office-fragments"] then settings.fragments = stringify(meta["pdfmd-office-fragments"]) end
  if meta["pdfmd-office-wanted"] then settings.wanted = stringify(meta["pdfmd-office-wanted"]) end
  if meta["pdfmd-office-labels"] then
    local file = io.open(stringify(meta["pdfmd-office-labels"]), "r")
    if file then
      local ok, data = pcall(pandoc.json.decode, file:read("a"), false)
      file:close()
      if ok and data then
        labels = data.labels or {}
        crefnames = data.crefnames or {}
        caption_sep = data.captionsep or caption_sep
        if data.crefcap ~= nil then cref_capital = data.crefcap end
      end
    end
  end
  return nil
end

local function write_report()
  if not settings.report then return end
  local file = io.open(settings.report, "w")
  if not file then return end
  file:write(pandoc.json and pandoc.json.encode and pandoc.json.encode({
    left_over = left_over, math = counters.math, native = counters.native}) or "")
  file:close()
end

function Pandoc(doc)
  current_meta = doc.meta
  if profile.pandoc then
    local ok, result = pcall(profile.pandoc, doc, helpers)
    if ok and result then doc = result
    elseif not ok then io.stderr:write("[pdfmd] the office profile's pandoc hook failed: " .. tostring(result) .. "\n") end
  end
  write_report()
  if settings.mode == "collect" and settings.wanted then
    local file = io.open(settings.wanted, "w")
    if file then
      local list = {}
      for _, id in ipairs(wanted_order) do list[#list + 1] = wanted[id] end
      file:write(pandoc.json.encode(list))
      file:close()
    end
  end
  return doc
end

-- for the tests: `pandoc lua` can load this file and reach the helpers
if PDFMD_OFFICE_EXPORT then
  PDFMD_OFFICE_EXPORT.ce_parse, PDFMD_OFFICE_EXPORT.ce_math = ce_parse, ce_math
  PDFMD_OFFICE_EXPORT.math_translate, PDFMD_OFFICE_EXPORT.parse_unit = math_translate, parse_unit
  PDFMD_OFFICE_EXPORT.unit_math, PDFMD_OFFICE_EXPORT.math_native = unit_math, math_native
end

return {
  {Meta = Meta},
  {Math = Math, RawInline = RawInline, Image = asset_image},
  {RawBlock = RawBlock, Para = Para, Figure = Figure, Table = Table},
  {Pandoc = Pandoc},
}

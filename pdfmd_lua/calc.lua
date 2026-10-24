-- pdfmd: an inline calculator (v3.30.4). Inline code followed at once by a bare `{=}`
--
--   Two years, `2026 - 2006`{=}, give `2 * 20 / 10`{=} points.
--
-- is replaced by its value ("Two years, 20, give 4 points."). Only pure arithmetic is evaluated, by the small parser
-- below: nothing is run (no load, no R, no Python), so a document from anybody is safe. Code that is not followed by
-- `{=}`, and code blocks, are never touched. Anything the parser cannot evaluate (a name it does not know, a division
-- by zero, an unfinished expression) is kept as the code it was, with one WARN on stderr naming it.
--
-- Operators, loosest first:  + -   |   * /  % %% (remainder)  // %/% (floor division)   |   unary - +   |   ^ ** (right to left)
--   so -2^2 is -4 and 2^3^2 is 512, as in R, Python and Lua.   7 % 3 is 1, -7 % 3 is 2, 7 %/% 2 is 3.
-- |x| is the absolute value (|a - b| / c). A % that no operand follows is a percent sign, a label like a unit and not an
-- operator: 0.5 / 4 * 100% is 12.5, as in a lab report's "... * 100% = 12.5%". × · ÷ − (Unicode) are * * / -.
-- Numbers: 12, 0.5, .5, 6.022e23, 1e-3.   Constants: pi, deg (= pi/180, so sin(30*deg) is 0.5).
-- Functions (angles in radians; the d forms take degrees):
--   sin cos tan cot sec csc   asin acos atan acot (atan(y, x) is the two-argument arctangent)   sinh cosh tanh asinh acosh atanh
--   sind cosd tand asind acosd atand (degrees in / out)   exp ln log (log(x) is natural, log(x, base))   log10 log2 sqrt cbrt abs sign
--   floor ceil trunc round(x) round(x, digits) (half to even like R and Python: round(2.5) is 2; -M pdfmd-calc-round=away: 3)   min max (any number of arguments)
--   hypot(x, y)   factorial(n)
-- The result prints like R: up to 7 significant digits, 20 and not 20.0, no trailing zeros.
--
-- This filter is added only when a document has a `{=}` after inline code and `calc` is not off (pdfmd.py: calc_filter_args()).

local EPS = 1e-15          -- a trig result this close to 0 is 0 (sin(pi) is 1.2e-16 in floating point)

local function fail(message) error({calc = message}, 0) end

local function finite(x)
  if x ~= x then fail("the result is not a number") end
  if x == math.huge or x == -math.huge then fail("the result is infinite") end
  return x
end

local function snap(x) return math.abs(x) < EPS and 0 or x end

local function argument(args, count, name)
  if #args ~= count then
    fail(string.format("%s takes %d argument%s", name, count, count == 1 and "" or "s"))
  end
  return args[1], args[2]
end

local function domain(ok, name) if not ok then fail(name .. " is not defined there") end end

local ROUND = "even"        -- "even" (R and Python: 2.5 is 2) or "away" (half away from zero: 2.5 is 3); -M pdfmd-calc-round

local function round(x, digits)
  digits = digits or 0
  if digits ~= math.floor(digits) or digits < 0 or digits > 15 then fail("round takes a whole number of digits from 0 to 15") end
  if ROUND == "even" then
    return tonumber(string.format("%." .. math.floor(digits) .. "f", x)) + 0.0    -- exact: 0.15 is 0.1499.. so 0.1, as in R and Python
  end
  local scale = 10 ^ digits
  local v = math.abs(x) * scale
  local r = math.floor(v + 0.5 + v * 1e-13) / scale        -- the 1e-13 lets 2.675 (binary 2.67499..) round to 2.68
  return x < 0 and -r or r
end

local function sign(x) return x > 0 and 1 or (x < 0 and -1 or 0) end

local FUNCTIONS = {
  sin = function(args) return snap(math.sin((argument(args, 1, "sin")))) end,
  cos = function(args) return snap(math.cos((argument(args, 1, "cos")))) end,
  tan = function(args) return snap(math.tan((argument(args, 1, "tan")))) end,
  cot = function(args)
    local x = argument(args, 1, "cot"); domain(math.tan(x) ~= 0 and math.abs(math.tan(x)) > EPS, "cot"); return 1 / math.tan(x)
  end,
  sec = function(args)
    local x = argument(args, 1, "sec"); domain(math.abs(math.cos(x)) > EPS, "sec"); return 1 / math.cos(x)
  end,
  csc = function(args)
    local x = argument(args, 1, "csc"); domain(math.abs(math.sin(x)) > EPS, "csc"); return 1 / math.sin(x)
  end,
  asin = function(args) local x = argument(args, 1, "asin"); domain(math.abs(x) <= 1, "asin"); return math.asin(x) end,
  acos = function(args) local x = argument(args, 1, "acos"); domain(math.abs(x) <= 1, "acos"); return math.acos(x) end,
  atan = function(args)
    if #args == 2 then return math.atan(args[1], args[2]) end
    return math.atan((argument(args, 1, "atan")))
  end,
  acot = function(args)
    local x = argument(args, 1, "acot"); return x == 0 and math.pi / 2 or math.atan(1 / x) + (x < 0 and math.pi or 0)
  end,
  sinh = function(args) local x = argument(args, 1, "sinh"); return (math.exp(x) - math.exp(-x)) / 2 end,
  cosh = function(args) local x = argument(args, 1, "cosh"); return (math.exp(x) + math.exp(-x)) / 2 end,
  tanh = function(args)
    local x = argument(args, 1, "tanh"); if x > 20 then return 1 elseif x < -20 then return -1 end
    local a, b = math.exp(x), math.exp(-x); return (a - b) / (a + b)
  end,
  asinh = function(args) local x = argument(args, 1, "asinh"); return math.log(x + math.sqrt(x * x + 1)) end,
  acosh = function(args) local x = argument(args, 1, "acosh"); domain(x >= 1, "acosh"); return math.log(x + math.sqrt(x * x - 1)) end,
  atanh = function(args) local x = argument(args, 1, "atanh"); domain(math.abs(x) < 1, "atanh"); return 0.5 * math.log((1 + x) / (1 - x)) end,
  sind = function(args) return snap(math.sin(math.rad((argument(args, 1, "sind"))))) end,
  cosd = function(args) return snap(math.cos(math.rad((argument(args, 1, "cosd"))))) end,
  tand = function(args)
    local x = argument(args, 1, "tand"); domain(math.abs(math.cos(math.rad(x))) > EPS, "tand"); return snap(math.tan(math.rad(x)))
  end,
  asind = function(args) local x = argument(args, 1, "asind"); domain(math.abs(x) <= 1, "asind"); return math.deg(math.asin(x)) end,
  acosd = function(args) local x = argument(args, 1, "acosd"); domain(math.abs(x) <= 1, "acosd"); return math.deg(math.acos(x)) end,
  atand = function(args)
    if #args == 2 then return math.deg(math.atan(args[1], args[2])) end
    return math.deg(math.atan((argument(args, 1, "atand"))))
  end,
  exp = function(args) return math.exp((argument(args, 1, "exp"))) end,
  ln = function(args) local x = argument(args, 1, "ln"); domain(x > 0, "ln"); return math.log(x) end,
  log = function(args)
    if #args == 2 then
      domain(args[1] > 0 and args[2] > 0 and args[2] ~= 1, "log"); return math.log(args[1]) / math.log(args[2])
    end
    local x = argument(args, 1, "log"); domain(x > 0, "log"); return math.log(x)
  end,
  log10 = function(args) local x = argument(args, 1, "log10"); domain(x > 0, "log10"); return math.log(x, 10) end,
  log2 = function(args) local x = argument(args, 1, "log2"); domain(x > 0, "log2"); return math.log(x, 2) end,
  sqrt = function(args) local x = argument(args, 1, "sqrt"); domain(x >= 0, "sqrt"); return math.sqrt(x) end,
  cbrt = function(args) local x = argument(args, 1, "cbrt"); return x < 0 and -((-x) ^ (1 / 3)) or x ^ (1 / 3) end,
  abs = function(args) return math.abs((argument(args, 1, "abs"))) end,
  sign = function(args) return sign((argument(args, 1, "sign"))) end,
  floor = function(args) return math.floor((argument(args, 1, "floor"))) + 0.0 end,
  ceil = function(args) return math.ceil((argument(args, 1, "ceil"))) + 0.0 end,
  trunc = function(args) local x = argument(args, 1, "trunc"); return (x < 0 and math.ceil(x) or math.floor(x)) + 0.0 end,
  round = function(args)
    if #args == 2 then return round(args[1], args[2]) end
    return round((argument(args, 1, "round")))
  end,
  min = function(args)
    if #args == 0 then fail("min needs a number") end
    local m = args[1]; for i = 2, #args do if args[i] < m then m = args[i] end end; return m
  end,
  max = function(args)
    if #args == 0 then fail("max needs a number") end
    local m = args[1]; for i = 2, #args do if args[i] > m then m = args[i] end end; return m
  end,
  hypot = function(args) local x, y = argument(args, 2, "hypot"); return math.sqrt(x * x + y * y) end,
  factorial = function(args)
    local n = argument(args, 1, "factorial")
    if n ~= math.floor(n) or n < 0 or n > 170 then fail("factorial takes a whole number from 0 to 170") end
    local f = 1.0; for i = 2, n do f = f * i end; return f
  end,
}

local CONSTANTS = {pi = math.pi, deg = math.pi / 180}

-- tokens: {kind = "num"|"name"|"op"|"end", value = ..., from = first byte, to = last byte}
local UNICODE_OPERATORS = {["\u{2212}"] = "-", ["\u{00D7}"] = "*", ["\u{00B7}"] = "*", ["\u{22C5}"] = "*", ["\u{00F7}"] = "/"}

local function tokenize(text)
  local tokens, i, n = {}, 1, #text
  local function add(kind, value, from, to) tokens[#tokens + 1] = {kind = kind, value = value, from = from, to = to} end
  while i <= n do
    local c = text:sub(i, i)
    local unicode                                              -- first: the locale's %a may take the lead byte of × for a letter
    if c:byte() >= 0x80 then
      for symbol, operator in pairs(UNICODE_OPERATORS) do
        if text:sub(i, i + #symbol - 1) == symbol then unicode = {symbol, operator}; break end
      end
    end
    if unicode then
      add("op", unicode[2], i, i + #unicode[1] - 1); i = i + #unicode[1]
    elseif c:match("%s") then
      i = i + 1
    elseif c:match("%d") or (c == "." and text:sub(i + 1, i + 1):match("%d")) then
      local s, e = text:find("^%d*%.?%d*", i)
      local exp_s, exp_e = text:find("^[eE][+-]?%d+", e + 1)
      if exp_s then e = exp_e end
      add("num", tonumber(text:sub(s, e)) + 0.0, s, e)
      i = e + 1
    elseif c:match("[%a_]") then
      local s, e = text:find("^[%a_][%w_]*", i)
      add("name", text:sub(s, e), s, e)
      i = e + 1
    else
      local three, two = text:sub(i, i + 2), text:sub(i, i + 1)
      if three == "%/%" then
        add("op", "//", i, i + 2); i = i + 3
      elseif two == "%%" then
        add("op", "%", i, i + 1); i = i + 2
      elseif two == "//" then
        add("op", "//", i, i + 1); i = i + 2
      elseif two == "**" then
        add("op", "^", i, i + 1); i = i + 2
      elseif c == "%" then
        local nextchar = text:match("^%s*(.)", i + 1)            -- an operand after it: the remainder; else a percent sign
        if nextchar and nextchar:match("[%w_%.%(|]") then add("op", "%", i, i) end
        i = i + 1
      elseif c:match("[%+%-%*/%^%(%),|]") then
        add("op", c, i, i); i = i + 1
      else
        fail("'" .. c .. "' is not arithmetic")
      end
    end
  end
  tokens[#tokens + 1] = {kind = "end", from = n + 1, to = n + 1}
  return tokens
end

local function evaluate(text, lookup)
  local tokens = tokenize(text)
  local position = 1
  local expression

  local function peek() return tokens[position] end
  local function take() position = position + 1; return tokens[position - 1] end
  local function is_op(token, ...)
    if token.kind ~= "op" then return false end
    for _, value in ipairs({...}) do if token.value == value then return true end end
    return false
  end
  local function expect(value)
    if not is_op(peek(), value) then fail("expected '" .. value .. "'") end
    take()
  end

  local unary

  local function atom()
    local token = take()
    if token.kind == "num" then return token.value end
    if token.kind == "name" then
      if is_op(peek(), "(") then
        local f = FUNCTIONS[token.value]
        if not f then fail("'" .. token.value .. "' is not a function pdfmd knows") end
        take()
        local args = {}
        if not is_op(peek(), ")") then
          repeat args[#args + 1] = expression() until not (is_op(peek(), ",") and take())
        end
        expect(")")
        return finite(f(args))
      end
      local constant = CONSTANTS[token.value]
      if constant ~= nil then return constant end
      if not lookup then fail("'" .. token.value .. "' is not a number or a name pdfmd knows") end
      return finite(lookup(token.value))
    end
    if is_op(token, "(") then
      local value = expression()
      expect(")")
      return value
    end
    if is_op(token, "|") then
      local value = expression()
      expect("|")
      return math.abs(value)
    end
    fail(token.kind == "end" and "the expression ends too soon" or ("unexpected '" .. tostring(token.value) .. "'"))
  end

  local function power()
    local base = atom()
    if is_op(peek(), "^") then
      take()
      return finite(base ^ unary())                           -- right to left: 2^3^2 is 2^(3^2); 2^-1 works
    end
    return base
  end

  unary = function()
    if is_op(peek(), "-") then take(); return -unary() end
    if is_op(peek(), "+") then take(); return unary() end
    return power()
  end

  local function term()
    local value = unary()
    while is_op(peek(), "*", "/", "%", "//") do
      local operator = take().value
      local right = unary()
      if operator == "*" then
        value = value * right
      else
        if right == 0 then fail("division by zero") end
        if operator == "/" then value = value / right
        elseif operator == "%" then value = value % right
        else value = math.floor(value / right) + 0.0 end
      end
      finite(value)
    end
    return value
  end

  expression = function()
    local value = term()
    while is_op(peek(), "+", "-") do
      local operator = take().value
      local right = term()
      value = operator == "+" and value + right or value - right
      finite(value)
    end
    return value
  end

  local value = expression()
  if peek().kind ~= "end" then fail("unexpected '" .. tostring(peek().value) .. "'") end
  return finite(value)
end

-- ---------------------------------------------------------------------------------------------------------------------
-- Showing a number

-- 20 and not 20.0; up to 7 significant digits, no trailing zeros; -0 is 0
local function show_plain(x)
  if x == 0 then return "0" end
  if x == math.floor(x) and math.abs(x) < 1e15 then return string.format("%.0f", x) end
  return (string.format("%.7g", x))
end

local function clean_zero(text) return (text:gsub("^%-(0%.?0*)$", "%1")) end

-- fmt: nil (plain), {kind = "sf", n = 4}: 4 significant figures (20.60, 0.02027, trailing zeros kept; the digits before
-- the point are never dropped, 1049 at 3sf is 1049), {kind = "dp", n = 2}: 2 decimal places (20.60)
local function show(x, fmt)
  if not fmt then return show_plain(x) end
  if fmt.kind == "dp" then return clean_zero(string.format("%." .. fmt.n .. "f", x)) end
  if x == 0 then return fmt.n > 1 and ("0." .. string.rep("0", fmt.n - 1)) or "0" end
  local mantissa_exponent = string.format("%." .. (fmt.n - 1) .. "e", x)
  local exponent = tonumber(mantissa_exponent:match("e([+-]%d+)$"))
  if exponent >= 15 or exponent < -6 then return (mantissa_exponent:gsub("e([+-])0*(%d)", "e%1%2")) end
  local decimals = fmt.n - 1 - exponent
  if decimals < 0 then decimals = 0 end
  return clean_zero(string.format("%." .. decimals .. "f", x))
end

local function parse_fmt(text)
  local number, kind = text:match("^%s*(%d+)%s*(%a%a)%s*$")
  if not number or (kind ~= "sf" and kind ~= "dp") then
    fail("'" .. text .. "' is not a number format (4sf: four significant figures, 2dp: two decimal places)")
  end
  local n = tonumber(number)
  if kind == "sf" and (n < 1 or n > 15) then fail("sf takes 1 to 15 significant figures") end
  if kind == "dp" and n > 15 then fail("dp takes 0 to 15 decimal places") end
  return {kind = kind, n = n}
end

-- ---------------------------------------------------------------------------------------------------------------------
-- Statements and variables
--
-- A text is read as statements. `[names =] EXPRESSION = {ans[:fmt]}` calculates and prints; `names = EXPRESSION` alone
-- (a span without {ans}) only stores; a lone `EXPRESSION` prints its value. `<-` assigns like `=`. Names are plain
-- identifiers (C_EDTA, ppm1); anything before them that is not one (`Run 1: V`) is a label and is left as written. A name
-- refers to the nearest definition above its use, else to the first below it, so Results may cite what Calculations defines.
--
-- More than one {ans} in a text: after text that ends in = it is a new calculation, whose expression is the longest tail of
-- that text that reads as one (`so round(n) = {ans:0dp}`: the words before `round(n)` are prose); after text that does not
-- end in = it repeats the value just printed in its own format (`= {ans:1dp}, so {ans:0dp}`).
--
-- {subs} between two = signs prints the expression with each name replaced by its value, written to the digits the name
-- was defined with (the computation always uses the full value): `ppm = C * V = {subs} = {ans:2dp}`. With
-- calc: {subs: true} every {ans} that follows an expression holding names gets that substituted copy in front of it;
-- {nosubs} (or {subs:off}) anywhere in the text turns it off for that text.

local DEFAULT_FMT = nil
local AUTO_SUBS = false
local STATEMENTS = {}          -- every statement, in document order (id = position)
local NAMED = {}               -- name -> its statements, in order
local OCCURRENCES = {}         -- the n-th place in the document that holds statements -> its statements and text
local pass = 1
local occurrence = 0

local function reason_of(err) return type(err) == "table" and err.calc or tostring(err) end

-- the pieces of a text between = and <- signs
local function split_equals(text)
  local parts, start, from = {}, 1, 1
  while true do
    local at = text:find("[=<]", from)
    if not at then parts[#parts + 1] = text:sub(start); break end
    if text:sub(at, at) == "=" then
      parts[#parts + 1] = text:sub(start, at - 1); start = at + 1; from = start
    elseif text:sub(at, at + 1) == "<-" then
      parts[#parts + 1] = text:sub(start, at - 1); start = at + 2; from = start
    else
      from = at + 1
    end
  end
  return parts
end

local function trim(text) return (text:gsub("^%s+", ""):gsub("%s+$", "")) end

local function is_identifier(text) return text:match("^[%a_][%w_]*$") ~= nil end

-- does `text` read as an expression? (a value a name might take does not matter; a division by zero is still an expression)
local SYNTAX_ERRORS = {"^unexpected", "^expected", "ends too soon", "is not arithmetic", "is not a function pdfmd knows",
  "is not a number or a name"}
local function parses(text)
  local ok, err = pcall(evaluate, text, function() return 1.2345678 end)
  if ok then return true end
  local reason = reason_of(err)
  for _, pattern in ipairs(SYNTAX_ERRORS) do
    if reason:find(pattern) then return false end
  end
  return true
end

-- the longest tail of `piece` that is an expression: ", so round(n)" -> "round(n)"
local function tail_expression(piece)
  piece = trim((piece:gsub("^[%s,;:]+", "")))
  local starts = {1}
  for at in piece:gmatch("%s()%S") do starts[#starts + 1] = at end
  for _, at in ipairs(starts) do
    local candidate = piece:sub(at)
    if parses(candidate) then return candidate end
  end
  fail("'" .. piece .. "' holds no expression to calculate")
end

-- every {ans[:fmt]}, {subs}, {subs:off} and {nosubs} of a text, in order
local function find_markers(text)
  local list, position = {}, 1
  while true do
    local s, e, word, spec = text:find("{(%a+)([^}]*)}", position)
    if not s then break end
    if word == "ans" then
      if spec ~= "" and spec:sub(1, 1) ~= ":" then fail("'{ans" .. spec .. "}': a format goes after a colon, {ans:4sf}") end
      list[#list + 1] = {kind = "ans", s = s, e = e, spec = spec}
    elseif word == "subs" and spec == "" then
      list[#list + 1] = {kind = "subs", s = s, e = e}
    elseif (word == "subs" and spec:lower() == ":off") or (word == "nosubs" and spec == "") then
      list[#list + 1] = {kind = "nosubs", s = s, e = e}
    end
    position = e + 1
  end
  return list
end

-- the statements of `text`; `default` is the format a {=4sf} after a span gave. Returns the statements, whether the text has
-- an {ans}, the edits that remove {nosubs}, and whether {nosubs} was there.
local function read_statements(text, default)
  local statements, edits, nosubs = {}, {}, false
  local function add(piece, kind, fmt)           -- kind: "plain" (no {ans}), "first" or "later" {ans} of the text
    local parts = split_equals(piece)
    local statement = {fmt = fmt or default, names = {}, placeholder = kind ~= "plain"}
    for index = 1, #parts - 1 do
      local part = trim(parts[index])
      if kind == "plain" then
        if not is_identifier(part) then fail("'" .. part .. "' is not a name; a name is letters, digits and _, such as C_EDTA") end
        statement.names[#statement.names + 1] = part
      else
        local name
        if kind == "first" then
          name = is_identifier(part) and part or part:match("[:;,]%s*([%a_][%w_]*)$")     -- `Run 1: V` names V
        else
          local word = part:match("(%S+)$")                                          -- `, so n2` names n2
          name = word and is_identifier(word) and word or nil
        end
        if name then statement.names[#statement.names + 1] = name end
      end
    end
    statement.expr = kind == "later" and tail_expression(parts[#parts]) or trim(parts[#parts])
    if statement.expr == "" then fail("there is nothing to calculate before the =") end
    for _, name in ipairs(statement.names) do
      if FUNCTIONS[name] or CONSTANTS[name] then fail("'" .. name .. "' is built in; choose another name") end
    end
    statements[#statements + 1] = statement
    return statement
  end
  local markers = find_markers(text)
  local found, previous, pending = false, nil, nil
  local position, segment = 1, ""
  for _, marker in ipairs(markers) do
    segment = segment .. text:sub(position, marker.s - 1)
    position = marker.e + 1
    if marker.kind == "nosubs" then
      nosubs = true
      edits[#edits + 1] = {s = marker.s, e = marker.e, text = "", swallow = true}
    elseif marker.kind == "subs" then
      segment = trim(segment)
      if segment:sub(-1) ~= "=" then segment = segment .. " =" end
      local _, stop = text:find("^%s*=", position)                  -- the = after {subs} is the one before {ans}: already there
      if stop then position = stop + 1 end
      pending = marker
    else
      found = true
      local fmt = nil
      if marker.spec ~= "" then fmt = parse_fmt(marker.spec:sub(2)) end
      local piece = trim(segment)
      segment = ""
      local statement
      if previous and piece:sub(-1) ~= "=" then                      -- the value just printed, in another format
        local source = previous.repeat_of or previous
        statement = {fmt = fmt or default, names = {}, expr = source.expr, repeat_of = source, placeholder = true}
        statements[#statements + 1] = statement
        if pending then fail("{subs} has to stand in front of an {ans} that follows its own expression") end
      else
        if piece:sub(-1) ~= "=" then fail("{ans} has to come right after an =, as in `2 + 2 = {ans}`") end
        statement = add(piece:sub(1, -2), previous and "later" or "first", fmt)
      end
      statement.start, statement.stop = marker.s, marker.e
      if pending then statement.subs_start, statement.subs_stop = pending.s, pending.e; pending = nil end
      previous = statement
    end
  end
  if pending then fail("{subs} has to stand in front of an {ans}, as in `x = a * b = {subs} = {ans}`") end
  if not found then add(text, "plain", nil) end
  return statements, found, edits, nosubs
end

local function resolve(name, id)
  local list = NAMED[name]
  if not list then fail("'" .. name .. "' is not defined; give it a value with `" .. name .. " = 2 + 2`{=} somewhere") end
  local chosen = list[1]
  for _, statement in ipairs(list) do
    if statement.id < id then chosen = statement end
  end
  return chosen
end

local function value_of(statement)
  if statement.repeat_of then return value_of(statement.repeat_of) end
  if statement.value ~= nil then return statement.value end
  if statement.failure then fail(statement.failure) end
  if statement.busy then fail("'" .. (statement.names[1] or statement.expr) .. "' depends on itself") end
  statement.busy = true
  local ok, result = pcall(evaluate, statement.expr, function(name) return value_of(resolve(name, statement.id)) end)
  statement.busy = nil
  if not ok then
    local reason = reason_of(result)
    statement.failure = statement.names[1] and ("'" .. statement.names[1] .. "' could not be computed: " .. reason) or reason
    fail(statement.failure)
  end
  statement.value = result
  return result
end

-- pass 1: record the statements of a text; returns the occurrence
local function register(text, default)
  occurrence = occurrence + 1
  local ok, statements, found, edits, nosubs = pcall(read_statements, text, default)
  local record = {text = text, found = found}
  if ok then
    record.statements, record.edits, record.nosubs = statements, edits, nosubs
    for _, statement in ipairs(statements) do
      STATEMENTS[#STATEMENTS + 1] = statement
      statement.id = #STATEMENTS
      for _, name in ipairs(statement.names) do
        NAMED[name] = NAMED[name] or {}
        table.insert(NAMED[name], statement)
      end
    end
  else
    record.error = reason_of(statements)
  end
  OCCURRENCES[occurrence] = record
  return record
end

-- pass 2: the n-th occurrence again; returns its record, or nil and a reason
local function fetch(text)
  occurrence = occurrence + 1
  local record = OCCURRENCES[occurrence]
  if not record or record.text ~= text then return nil, "internal: the passes disagree about this place" end
  if record.error then return nil, record.error end
  return record
end

-- the expression of a statement with every name replaced by its value, in the digits that name was defined with; and
-- whether any name was replaced. A negative value gets parentheses unless nothing before it could take it for a sign.
local function substitute(statement)
  local text = statement.expr
  local tokens = tokenize(text)
  local out, position, changed = {}, 1, false
  for index, token in ipairs(tokens) do
    if token.kind == "name" then
      local following = tokens[index + 1]
      local call = following and following.kind == "op" and following.value == "("
      if not call and CONSTANTS[token.value] == nil and not FUNCTIONS[token.value] then
        local source = resolve(token.value, statement.id)
        local value = value_of(source)
        local shown = show(value, source.fmt or DEFAULT_FMT)
        if shown:sub(1, 1) == "-" then
          local before = tokens[index - 1]
          local open = not before or (before.kind == "op" and (before.value == "(" or before.value == ","))
          local power = following and following.kind == "op" and following.value == "^"
          if not open or power then shown = "(" .. shown .. ")" end
        end
        out[#out + 1] = text:sub(position, token.from - 1)
        out[#out + 1] = shown
        position = token.to + 1
        changed = true
      end
    end
  end
  out[#out + 1] = text:sub(position)
  return table.concat(out), changed
end

-- what each {ans}, {subs} and {nosubs} of a record is replaced by: a list of {s, e, text} over the record's text
local function edits_of(record, default)
  local edits = {}
  for _, edit in ipairs(record.edits) do edits[#edits + 1] = edit end
  for _, statement in ipairs(record.statements) do
    local shown = show(value_of(statement), statement.fmt or default)
    if statement.subs_start then
      edits[#edits + 1] = {s = statement.subs_start, e = statement.subs_stop, text = (substitute(statement))}
    elseif AUTO_SUBS and not record.nosubs and not statement.repeat_of then
      local substituted, changed = substitute(statement)
      local lone_name = #tokenize(statement.expr) == 2          -- `y = C = {ans}`: the copy would only repeat the value
      if changed and not lone_name and substituted ~= shown then shown = substituted .. " = " .. shown end
    end
    edits[#edits + 1] = {s = statement.start, e = statement.stop, text = shown}
  end
  table.sort(edits, function(a, b) return a.s < b.s end)
  return edits
end

-- the text with the edits put in
local function splice(text, edits)
  local out, position = {}, 1
  for _, edit in ipairs(edits) do
    local s = edit.s
    if edit.swallow and s > position and text:sub(s - 1, s - 1):match("%s") then s = s - 1 end
    out[#out + 1] = text:sub(position, s - 1)
    out[#out + 1] = edit.text
    position = edit.e + 1
  end
  out[#out + 1] = text:sub(position)
  return table.concat(out)
end

-- the text of a record with each {ans} replaced by its value (or, with no {ans}: the value, or nothing for a stored one)
local function render(record, default)
  if record.found then return trim(splice(record.text, edits_of(record, default))) end
  local statement = record.statements[1]
  local value = value_of(statement)
  if #statement.names > 0 then return "" end
  local fmt = statement.fmt
  if not fmt and is_identifier(statement.expr) and NAMED[statement.expr] then
    fmt = resolve(statement.expr, statement.id).fmt
  end
  return show(value, fmt or default)
end

local function warn(shown, reason, kept)
  io.stderr:write(string.format("WARN  calc: %s is not evaluated (%s); %s\n", shown, reason, kept))
end

-- ---------------------------------------------------------------------------------------------------------------------
-- Finding the places in the document

local function raw_format(item)
  local fmt = item.t == "RawInline" and item.format:match("^(%d+%a%a)$") or nil
  if fmt then
    local ok, parsed = pcall(parse_fmt, fmt)
    if ok then return parsed end
  end
  return nil
end

-- a `code`{=} / `code`{=4sf} span at inlines[i]: its text, its format, how many items it uses, the rest of the string
local function span_at(inlines, i)
  local item, following = inlines[i], inlines[i + 1]
  if item.t == "Code" and following and following.t == "Str" and following.text:sub(1, 3) == "{=}" then
    return item.text, nil, 2, following.text:sub(4)
  end
  if item.t == "RawInline" then
    local fmt = raw_format(item)
    if fmt then return item.text, fmt, 1, "" end
  end
  return nil
end

local function process_inlines(inlines)
  local out, changed, i = pandoc.Inlines({}), false, 1
  while i <= #inlines do
    local text, fmt, used, rest = span_at(inlines, i)
    if text then
      changed = true
      if pass == 1 then
        register(text, fmt)
        out:insert(inlines[i]); if used == 2 then out:insert(inlines[i + 1]) end
      else
        local record, problem = fetch(text)
        local ok, result
        if record then ok, result = pcall(render, record, DEFAULT_FMT) else ok, result = false, problem end
        if ok then
          if result ~= "" then out:insert(pandoc.Str(result .. rest)) elseif rest ~= "" then out:insert(pandoc.Str(rest)) end
        else
          warn("`" .. text .. "`{=}", reason_of(result), "the code is kept")
          out:insert(inlines[i])
          if rest ~= "" then out:insert(pandoc.Str(rest)) end
        end
      end
      i = i + used
    else
      out:insert(inlines[i])
      i = i + 1
    end
  end
  if pass == 2 and changed then return out end
end

local function has_marker(item)
  return item.t == "Str" and (item.text:find("{ans", 1, true) or item.text:find("{subs", 1, true)
    or item.text:find("{nosubs", 1, true)) and true or false
end

-- one line (items a..b) of a ::: calc paragraph. The line's own {ans} come first (the text up to the last marker has to be
-- plain; what follows may hold anything: a unit, \ce{Ca^2+}, math), then the `code`{=} spans of the line, so that
-- everything is registered in the order it is read. Returns the new items of the line, or nil when nothing changed.
local function process_line(items, a, b)
  local last, holders = nil, false
  for index = a, b do
    if has_marker(items[index]) then
      last = index
      if items[index].text:find("{ans", 1, true) then holders = true end
    end
  end
  local changed, line = false, nil
  if holders then
    local parts, offsets, plain, length = {}, {}, true, 0
    for index = a, last do
      local item = items[index]
      local piece
      if item.t == "Str" or item.t == "Code" then piece = item.text elseif item.t == "Space" then piece = " " else plain = false end
      if piece then
        offsets[index] = {length + 1, length + #piece}
        parts[#parts + 1] = piece
        length = length + #piece
      end
    end
    local text = table.concat(parts)
    if not plain then
      if pass == 2 then warn("line `" .. trim(text) .. "`", "it holds formatting, a link or math before its last {ans}", "the line is left as written") end
    elseif pass == 1 then
      register(text, nil)
    else
      local record, problem = fetch(text)
      local ok, edits = false, problem
      if record then ok, edits = pcall(edits_of, record, DEFAULT_FMT) end
      if not ok then
        warn("line `" .. trim(text) .. "`", reason_of(edits), "the line is left as written")
      else
        local per_item = {}
        for _, edit in ipairs(edits) do
          local home
          for index, offset in pairs(offsets) do
            if items[index].t == "Str" and offset[1] <= edit.s and edit.e <= offset[2] then home = index end
          end
          if not home then
            warn("line `" .. trim(text) .. "`", "a {...} marker is split by formatting", "the line is left as written")
            per_item = nil
            break
          end
          per_item[home] = per_item[home] or {}
          table.insert(per_item[home], {s = edit.s - offsets[home][1] + 1, e = edit.e - offsets[home][1] + 1, text = edit.text})
        end
        if per_item then
          line = pandoc.Inlines({})
          for index = a, b do line:insert(items[index]) end
          for index, list in pairs(per_item) do
            line[index - a + 1] = pandoc.Str(splice(items[index].text, list))
          end
          changed = true
        end
      end
    end
  end
  if not line then
    line = pandoc.Inlines({})
    for index = a, b do line:insert(items[index]) end
  end
  local spans = process_inlines(line)
  if spans then line, changed = spans, true end
  if changed then return line end
end

local function process_paragraph(inlines)
  local items = pandoc.Inlines({})
  for _, item in ipairs(inlines) do items:insert(item) end
  local out, changed, first = pandoc.Inlines({}), false, 1
  for index = 1, #items + 1 do
    local item = items[index]
    if index == #items + 1 or item.t == "SoftBreak" or item.t == "LineBreak" then
      if index > first then
        local line = process_line(items, first, index - 1)
        if line then
          changed = true
          for _, piece in ipairs(line) do out:insert(piece) end
        else
          for position = first, index - 1 do out:insert(items[position]) end
        end
      end
      if item then out:insert(item) end
      first = index + 1
    end
  end
  if changed then return out end
end

local function paragraph(block)
  local out = process_paragraph(block.content)
  if out then block.content = out end
  return block, false                                  -- its inlines are done: the document-wide walk must not read them again
end

local calc_div

local function inner_div(div)
  if div.classes:includes("calc") then return calc_div(div), false end
end

calc_div = function(div)
  if not div.classes:includes("calc") then return nil end
  local content = div.content:walk({traverse = "topdown", Para = paragraph, Plain = paragraph, Inlines = process_inlines,
    Div = inner_div})
  if pass == 1 then return div, false end
  local classes = pandoc.List({})
  for _, class in ipairs(div.classes) do if class ~= "calc" then classes:insert(class) end end
  local extra = false
  for _ in pairs(div.attributes) do extra = true end
  if div.identifier == "" and #classes == 0 and not extra then return content, false end
  return pandoc.Div(content, pandoc.Attr(div.identifier, classes, div.attributes)), false
end

return {{Pandoc = function(doc)
  local mode = doc.meta["pdfmd-calc-round"]
  mode = mode and pandoc.utils.stringify(mode):lower() or "even"
  if mode == "away" or mode == "even" then ROUND = mode end
  local digits = doc.meta["pdfmd-calc-digits"]
  if digits then
    local ok, parsed = pcall(parse_fmt, pandoc.utils.stringify(digits))
    if ok then DEFAULT_FMT = parsed end
  end
  local subs = doc.meta["pdfmd-calc-subs"]
  AUTO_SUBS = subs ~= nil and pandoc.utils.stringify(subs):lower() == "true"
  for _, which in ipairs({1, 2}) do
    pass, occurrence = which, 0
    doc = doc:walk({traverse = "topdown", Div = calc_div, Inlines = process_inlines})
  end
  return doc
end}}

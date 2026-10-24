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

-- tokens: {kind = "num"|"name"|"op"|"end", value = ...}
local function tokenize(text)
  local tokens, i, n = {}, 1, #text
  while i <= n do
    local c = text:sub(i, i)
    if c:match("%s") then
      i = i + 1
    elseif c:match("%d") or (c == "." and text:sub(i + 1, i + 1):match("%d")) then
      local s, e = text:find("^%d*%.?%d*", i)
      local exp_s, exp_e = text:find("^[eE][+-]?%d+", e + 1)
      if exp_s then e = exp_e end
      tokens[#tokens + 1] = {kind = "num", value = tonumber(text:sub(s, e)) + 0.0}
      i = e + 1
    elseif c:match("[%a_]") then
      local s, e = text:find("^[%a_][%w_]*", i)
      tokens[#tokens + 1] = {kind = "name", value = text:sub(s, e)}
      i = e + 1
    else
      local three, two = text:sub(i, i + 2), text:sub(i, i + 1)
      if three == "%/%" then
        tokens[#tokens + 1] = {kind = "op", value = "//"}; i = i + 3
      elseif two == "%%" then
        tokens[#tokens + 1] = {kind = "op", value = "%"}; i = i + 2
      elseif two == "//" then
        tokens[#tokens + 1] = {kind = "op", value = "//"}; i = i + 2
      elseif two == "**" then
        tokens[#tokens + 1] = {kind = "op", value = "^"}; i = i + 2
      elseif c == "%" then
        local nextchar = text:match("^%s*(.)", i + 1)            -- an operand after it: the remainder; else a percent sign
        if nextchar and nextchar:match("[%w_%.%(|]") then tokens[#tokens + 1] = {kind = "op", value = "%"} end
        i = i + 1
      elseif c:match("[%+%-%*/%^%(%),|]") then
        tokens[#tokens + 1] = {kind = "op", value = c}; i = i + 1
      else
        fail("'" .. c .. "' is not arithmetic")
      end
    end
  end
  tokens[#tokens + 1] = {kind = "end"}
  return tokens
end

local function evaluate(text)
  text = text:gsub("\u{2212}", "-"):gsub("\u{00D7}", "*"):gsub("\u{00B7}", "*"):gsub("\u{22C5}", "*"):gsub("\u{00F7}", "/")
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
      if constant == nil then fail("'" .. token.value .. "' is not a number or a name pdfmd knows") end
      return constant
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

-- 20 and not 20.0; up to 7 significant digits, no trailing zeros; -0 is 0
local function show(x)
  if x == 0 then return "0" end
  if x == math.floor(x) and math.abs(x) < 1e15 then return string.format("%.0f", x) end
  return (string.format("%.7g", x))
end

local function calculate(code)
  local ok, result = pcall(evaluate, code.text)
  if ok then return show(result) end
  local reason = type(result) == "table" and result.calc or tostring(result)
  io.stderr:write(string.format("WARN  calc: `%s`{=} is not evaluated (%s); the code is kept\n", code.text, reason))
  return nil
end

local function inlines_filter(inlines)
  local out, changed, i = pandoc.Inlines({}), false, 1
  while i <= #inlines do
    local item, following = inlines[i], inlines[i + 1]
    if item.t == "Code" and following and following.t == "Str" and following.text:sub(1, 3) == "{=}" then
      local rest = following.text:sub(4)
      local value = calculate(item)
      if value then
        out:insert(pandoc.Str(value .. rest))
      else
        out:insert(item)
        if rest ~= "" then out:insert(pandoc.Str(rest)) end
      end
      changed = true
      i = i + 2
    else
      out:insert(item)
      i = i + 1
    end
  end
  if changed then return out end
end

return {{Pandoc = function(doc)
  local mode = doc.meta["pdfmd-calc-round"]
  mode = mode and pandoc.utils.stringify(mode):lower() or "even"
  if mode == "away" or mode == "even" then ROUND = mode end
  return doc:walk({Inlines = inlines_filter})
end}}

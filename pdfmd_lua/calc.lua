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
-- Numbers: 12, 0.5, .5, 6.022e23, 1e-3.   Constants: pi, deg (= pi/180, so sin(30*deg) is 0.5), Inf.
-- Functions (angles in radians; the d forms take degrees):
--   sin cos tan cot sec csc   asin acos atan acot (atan(y, x) is the two-argument arctangent)   sinh cosh tanh asinh acosh atanh
--   sind cosd tand asind acosd atand (degrees in / out)   exp ln log (log(x) is natural, log(x, base))   log10 log2 sqrt cbrt abs sign
--   floor ceil trunc round(x) round(x, digits) (half to even like R and Python: round(2.5) is 2; -M pdfmd-calc-round=away: 3)   min max (any number of arguments)
--   hypot(x, y)   factorial(n)
--   qnorm(p) pnorm(z)   qt(p, df) pt(t, df)  (lower tail, as in R; df may be a fraction or Inf; qt(0.975, 18) is 2.100922)
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

-- Statistics (v3.30.10): the normal and Student's t distributions, no libraries. Tested against R and SciPy: qnorm, pnorm about
-- 1e-15; qt about 1e-12 (3e-11 for p near 1e-12); pt about 1e-12 up to 1000 degrees of freedom, 1e-9 above.
local stats = {}

local LANCZOS = {0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
  12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7}

-- ln Gamma(x) for x > 0 (Lanczos, g = 7; relative error about 1e-15)
local function lgamma(x)
  if x < 0.5 then return math.log(math.pi / math.sin(math.pi * x)) - lgamma(1 - x) end
  x = x - 1
  local sum = LANCZOS[1]
  for i = 1, 8 do sum = sum + LANCZOS[i + 1] / (x + i) end
  local t = x + 7.5
  return 0.5 * math.log(2 * math.pi) + (x + 0.5) * math.log(t) - t + math.log(sum)
end

-- the continued fraction of the regularized incomplete beta function (modified Lentz)
local function beta_fraction(a, b, x)
  local tiny = 1e-300
  local qab, qap, qam = a + b, a + 1, a - 1
  local c, d = 1.0, 1 - qab * x / qap
  if math.abs(d) < tiny then d = tiny end
  d = 1 / d
  local h = d
  for m = 1, 1000 do
    local m2 = 2 * m
    local aa = m * (b - m) * x / ((qam + m2) * (a + m2))
    d = 1 + aa * d; if math.abs(d) < tiny then d = tiny end
    c = 1 + aa / c; if math.abs(c) < tiny then c = tiny end
    d = 1 / d; h = h * d * c
    aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
    d = 1 + aa * d; if math.abs(d) < tiny then d = tiny end
    c = 1 + aa / c; if math.abs(c) < tiny then c = tiny end
    d = 1 / d
    local delta = d * c
    h = h * delta
    if math.abs(delta - 1) < 1e-16 then break end
  end
  return h
end

-- I_x(a, b), the regularized incomplete beta function
local function ibeta(x, a, b)
  if x <= 0 then return 0.0 end
  if x >= 1 then return 1.0 end
  local front = math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * math.log(x) + b * math.log(1 - x))
  if x < (a + 1) / (a + b + 2) then return front * beta_fraction(a, b, x) / a end
  return 1 - front * beta_fraction(b, a, 1 - x) / b
end

-- Q(1/2, x), the regularized upper incomplete gamma function, for the normal tail: P(|Z| > z) = Q(1/2, z^2/2)
local function gamma_q_half(x)
  if x <= 0 then return 1.0 end
  local a = 0.5
  local front = math.exp(-x + a * math.log(x) - lgamma(a))
  if x < a + 1 then
    local sum, term, n = 1 / a, 1 / a, a
    for _ = 1, 1000 do
      n = n + 1; term = term * x / n; sum = sum + term
      if math.abs(term) < math.abs(sum) * 1e-17 then break end
    end
    return 1 - front * sum
  end
  local tiny = 1e-300
  local b = x + 1 - a
  local c, d = 1 / tiny, 1 / b
  local h = d
  for i = 1, 1000 do
    local an = -i * (i - a)
    b = b + 2
    d = an * d + b; if math.abs(d) < tiny then d = tiny end
    c = b + an / c; if math.abs(c) < tiny then c = tiny end
    d = 1 / d
    local delta = d * c
    h = h * delta
    if math.abs(delta - 1) < 1e-16 then break end
  end
  return front * h
end

-- the upper tail P(Z > z) for z >= 0
local function normal_tail(z) return 0.5 * gamma_q_half(z * z / 2) end

function stats.pnorm(z)
  if z ~= z then return z end
  if z == math.huge then return 1.0 elseif z == -math.huge then return 0.0 end
  if z >= 0 then return 1 - normal_tail(z) end
  return normal_tail(-z)
end

-- Wichura, AS 241 (PPND16): about 16 figures
function stats.qnorm(p)
  local q = p - 0.5
  local value
  if math.abs(q) <= 0.425 then
    local r = 0.180625 - q * q
    value = q * (((((((2.5090809287301226727e+3 * r + 3.3430575583588128105e+4) * r + 6.7265770927008700853e+4) * r
      + 4.5921953931549871457e+4) * r + 1.3731693765509461125e+4) * r + 1.9715909503065514427e+3) * r
      + 1.3314166789178437745e+2) * r + 3.3871328727963666080) /
      (((((((5.2264952788528545610e+3 * r + 2.8729085735721942674e+4) * r + 3.9307895800092710610e+4) * r
      + 2.1213794301586595867e+4) * r + 5.3941960214247511077e+3) * r + 6.8718700749205790830e+2) * r
      + 4.2313330701600911252e+1) * r + 1.0)
    return value
  end
  local r = q < 0 and p or 1 - p
  r = math.sqrt(-math.log(r))
  if r <= 5 then
    r = r - 1.6
    value = (((((((7.74545014278341407640e-4 * r + 2.27238449892691845833e-2) * r + 2.41780725177450611770e-1) * r
      + 1.27045825245236838258) * r + 3.64784832476320460504) * r + 5.76949722146069140550) * r
      + 4.63033784615654529590) * r + 1.42343711074968357734) /
      (((((((1.05075007164441684324e-9 * r + 5.47593808499534494600e-4) * r + 1.51986665636164571966e-2) * r
      + 1.48103976427480074590e-1) * r + 6.89767334985100004550e-1) * r + 1.67638483018380384940) * r
      + 2.05319162663775882187) * r + 1.0)
  else
    r = r - 5
    value = (((((((2.01033439929228813265e-7 * r + 2.71155556874348757815e-5) * r + 1.24266094738807843860e-3) * r
      + 2.65321895265761230930e-2) * r + 2.96560571828504891230e-1) * r + 1.78482653991729133580) * r
      + 5.46378491116411436990) * r + 6.65790464350110377720) /
      (((((((2.04426310338993978564e-15 * r + 1.42151175831644588870e-7) * r + 1.84631831751005468180e-5) * r
      + 7.86869131145613259100e-4) * r + 1.48753612908506148525e-2) * r + 1.36929880922735805310e-1) * r
      + 5.99832206555887937690e-1) * r + 1.0)
  end
  return q < 0 and -value or value
end

local LARGE_DF = 1000

-- P(T > t) for t >= 0
local function t_tail(t, df)
  if df == math.huge then return normal_tail(t) end
  if df > 1e6 then return normal_tail(t - t * (t * t + 1) / (4 * df)) end     -- the incomplete beta loses figures here
  return 0.5 * ibeta(df / (df + t * t), df / 2, 0.5)
end

function stats.pt(t, df)
  if t ~= t then return t end
  if t == math.huge then return 1.0 elseif t == -math.huge then return 0.0 end
  if t >= 0 then return 1 - t_tail(t, df) end
  return t_tail(-t, df)
end

-- Student's t quantile, lower tail
function stats.qt(p, df)
  if p == 0.5 then return 0.0 end
  local upper = p > 0.5
  local q = upper and 1 - p or p                      -- the tail that is solved for, 0 < q < 0.5
  local value
  if df == math.huge then
    value = -stats.qnorm(q)
  elseif df == 1 then
    value = 1 / math.tan(math.pi * q)
  elseif df == 2 then
    value = (1 - 2 * q) / math.sqrt(2 * q * (1 - q))
  elseif df > LARGE_DF then                           -- Cornish-Fisher (Abramowitz and Stegun 26.7.5)
    local z = -stats.qnorm(q)
    local z2 = z * z
    local g1 = z * (z2 + 1) / 4
    local g2 = z * (5 * z2 * z2 + 16 * z2 + 3) / 96
    local g3 = z * (3 * z2 * z2 * z2 + 19 * z2 * z2 + 17 * z2 - 15) / 384
    local g4 = z * (79 * z2 ^ 4 + 776 * z2 ^ 3 + 1482 * z2 ^ 2 - 1920 * z2 - 945) / 92160
    value = z + g1 / df + g2 / df ^ 2 + g3 / df ^ 3 + g4 / df ^ 4
  else
    local lo, hi = 0.0, 1.0
    while t_tail(hi, df) > q do lo = hi; hi = hi * 2; if hi > 1e300 then break end end
    for _ = 1, 300 do
      local mid = (lo + hi) / 2
      if t_tail(mid, df) > q then lo = mid else hi = mid end
      if hi - lo <= 1e-16 * hi then break end
    end
    value = (lo + hi) / 2
  end
  return upper and value or -value
end


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
  qnorm = function(args)
    local p = argument(args, 1, "qnorm")
    if not (p > 0 and p < 1) then fail("qnorm takes a probability between 0 and 1, not including them") end
    return stats.qnorm(p)
  end,
  pnorm = function(args) return stats.pnorm((argument(args, 1, "pnorm"))) end,
  qt = function(args)
    local p, df = argument(args, 2, "qt")
    if not (p > 0 and p < 1) then fail("qt takes a probability between 0 and 1, not including them") end
    if not (df > 0) then fail("qt takes degrees of freedom above 0 (or Inf)") end
    return stats.qt(p, df)
  end,
  pt = function(args)
    local t, df = argument(args, 2, "pt")
    if not (df > 0) then fail("pt takes degrees of freedom above 0 (or Inf)") end
    return stats.pt(t, df)
  end,
  factorial = function(args)
    local n = argument(args, 1, "factorial")
    if n ~= math.floor(n) or n < 0 or n > 170 then fail("factorial takes a whole number from 0 to 170") end
    local f = 1.0; for i = 2, n do f = f * i end; return f
  end,
}

local CONSTANTS = {pi = math.pi, deg = math.pi / 180, Inf = math.huge}

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
local NOINDENT = false                                  -- set from pdfmd-calc-noindent (3.30.9), see indent_for_div
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
  if item.t == "RawInline" and item.format == "calc" then return item.text, nil, 1, "" end      -- `code`{=calc}
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

-- ---------------------------------------------------------------------------------------------------------------------
-- Blocks of statements (3.30.11). The lines of a ```{=calc} block, of a `::: {.calc .hide}` div and of the constants file
-- are statements like the text of a `{=}` span: `t = 2.101` stores a name and prints nothing, `x = a * b = {ans}` prints.

local function normal(text) return trim((text:gsub("%s+", " "))) end

-- the statements of a block's text: one per line, blank lines and lines that start with # skipped
local function block_lines(text)
  local lines = {}
  for line in (text .. "\n"):gmatch("(.-)\r?\n") do
    line = trim(line)
    if line ~= "" and line:sub(1, 1) ~= "#" then lines[#lines + 1] = line end
  end
  return lines
end

-- pass 1: register each line (returns nothing); pass 2: the paragraphs to print, none for a hidden block
local function statement_block(lines, hidden)
  local out = pandoc.Blocks({})
  for _, line in ipairs(lines) do
    if pass == 1 then
      register(line, nil)
    else
      local record, problem = fetch(line)
      local ok, result
      if record then ok, result = pcall(render, record, DEFAULT_FMT) else ok, result = false, problem end
      if ok then
        if result ~= "" and not hidden then out:insert(pandoc.Para({pandoc.Str(result)})) end
      else
        warn("`" .. line .. "`", reason_of(result), hidden and "the line is ignored" or "the line is kept")
        if not hidden then out:insert(pandoc.Para({pandoc.Code(line)})) end
      end
    end
  end
  if pass == 2 then return out end
end

local function raw_block(block)
  if block.format ~= "calc" then return nil end
  local out = statement_block(block_lines(block.text), false)
  return out
end

-- ```{=} is no block for Pandoc (an empty raw format): the fence becomes a paragraph holding one code span whose line
-- breaks are gone. The lines are read again from the source file(s) Pandoc was given, matched by their text, so
-- ```{=} works as ```{=calc} does. (A document read from standard input has no file to read: write ```{=calc}.)
local FENCES
local fence_cursor = 1

local function source_fences()
  if FENCES then return FENCES end
  FENCES = {}
  local files = PANDOC_STATE and PANDOC_STATE.input_files or {}
  for _, name in ipairs(files) do
    local handle = name ~= "-" and io.open(name, "r") or nil
    if handle then
      local text = handle:read("a")
      handle:close()
      local opener, info, body
      for line in (text .. "\n"):gmatch("(.-)\r?\n") do
        if not opener then
          local marks, rest = line:match("^%s*(`+)(.*)$")
          if not marks then marks, rest = line:match("^%s*(~+)(.*)$") end
          if marks and #marks >= 3 and not (marks:sub(1, 1) == "`" and rest:find("`", 1, true)) then
            opener, info, body = marks, trim(rest), {}
          end
        else
          local closing = line:match("^%s*([`~]+)%s*$")
          if closing and closing:sub(1, 1) == opener:sub(1, 1) and #closing >= #opener then
            if info == "{=}" then FENCES[#FENCES + 1] = {key = normal(table.concat(body, " ")), lines = body} end
            opener = nil
          else
            body[#body + 1] = line
          end
        end
      end
    end
  end
  return FENCES
end

-- a paragraph that is a misread ```{=} fence: (true, blocks) (blocks only in pass 2), or false for any other paragraph
local function fence_block(block)
  if #block.content ~= 1 or block.content[1].t ~= "Code" then return false end
  local code = block.content[1].text
  if code:sub(1, 3) ~= "{=}" then return false end
  local wanted, fences, found = normal(code:sub(4)), source_fences(), nil
  for index = fence_cursor, #fences do
    if fences[index].key == wanted then found = fences[index]; fence_cursor = index + 1; break end
  end
  if not found then
    if pass == 2 then
      warn("a ```{=} block", "its lines could not be found in the source", "write ```{=calc}; the block is kept as text")
    end
    return false
  end
  local lines = block_lines(table.concat(found.lines, "\n"))
  return true, statement_block(lines, false)
end

local function fence_handler(block)
  local handled, out = fence_block(block)
  if handled and pass == 2 then return out end
end

-- the statements of a hidden div's paragraph: one per line of plain text
local function hidden_paragraph(block)
  local handled = fence_block(block)
  if handled then return pass == 2 and pandoc.Blocks({}) or nil end
  local lines, current, plain = {}, {}, true
  for _, item in ipairs(block.content) do
    if item.t == "SoftBreak" or item.t == "LineBreak" then
      lines[#lines + 1] = table.concat(current); current = {}
    elseif item.t == "Str" or item.t == "Code" then current[#current + 1] = item.text
    elseif item.t == "Space" then current[#current + 1] = " "
    else plain = false; current[#current + 1] = "" end
  end
  lines[#lines + 1] = table.concat(current)
  if not plain then
    if pass == 2 then warn("a hidden calc block", "a line holds formatting, a link or math", "that paragraph is ignored") end
  else
    statement_block(block_lines(table.concat(lines, "\n")), true)
  end
  if pass == 2 then return pandoc.Blocks({}) end
end

local function paragraph(block)
  local handled, replacement = fence_block(block)
  if handled then return (pass == 2 and replacement or block), false end
  local out = process_paragraph(block.content)
  if out then block.content = out end
  return block, false                                  -- its inlines are done: the document-wide walk must not read them again
end

local calc_div

local function inner_div(div)
  if div.classes:includes("calc") then return calc_div(div), false end
end

-- Writers pdfmd_lua/indent.lua can set a paragraph indent for (it runs after this filter). Elsewhere the attribute would
-- only show up in the output (Markdown) or print a NOTE (Word), so it is not added.
local INDENTS = {latex = true, beamer = true, typst = true, html = true, html4 = true, html5 = true, epub = true,
  epub2 = true, epub3 = true, revealjs = true, slidy = true, slideous = true, s5 = true, dzslides = true,
  chunkedhtml = true}

-- The attributes of the finished div. A calc div carries no first-line indent (3.30.9, `calc: {noindent: true}`, the
-- default): it becomes `indent=false` for indent.lua, unless the div says something about the indent itself.
local function attributes_of(div, classes)
  local attributes = {}
  for key, value in pairs(div.attributes) do attributes[key] = value end
  if NOINDENT and INDENTS[FORMAT:lower():gsub("[+-].*$", "")] and attributes.indent == nil then
    local own = false
    for _, class in ipairs(classes) do
      if class == "indent" or class == "noindent" then own = true end
    end
    if not own then attributes.indent = "false" end
  end
  return attributes
end

calc_div = function(div)
  if not div.classes:includes("calc") then return nil end
  if div.classes:includes("hide") or div.classes:includes("hidden") then      -- `::: {.calc .hide}`: statements, nothing printed
    div.content:walk({traverse = "topdown", Para = hidden_paragraph, Plain = hidden_paragraph, RawBlock = raw_block})
    if pass == 1 then return div, false end
    return pandoc.Blocks({}), false
  end
  local content = div.content:walk({traverse = "topdown", Para = paragraph, Plain = paragraph, Inlines = process_inlines,
    Div = inner_div, RawBlock = raw_block})
  if pass == 1 then return div, false end
  local classes = pandoc.List({})
  for _, class in ipairs(div.classes) do if class ~= "calc" then classes:insert(class) end end
  local attributes = attributes_of(div, classes)
  local extra = false
  for _ in pairs(attributes) do extra = true end
  if div.identifier == "" and #classes == 0 and not extra then return content, false end
  return pandoc.Div(content, pandoc.Attr(div.identifier, classes, attributes)), false
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
  local noindent = doc.meta["pdfmd-calc-noindent"]
  NOINDENT = noindent ~= nil and pandoc.utils.stringify(noindent):lower() == "true"
  local constants = doc.meta["pdfmd-calc-constants"]
  local constant_lines = constants and block_lines(pandoc.utils.stringify(constants)) or {}
  for _, which in ipairs({1, 2}) do
    pass, occurrence, fence_cursor = which, 0, 1
    statement_block(constant_lines, true)                 -- from `calc: {constants: file.csv}`: first in the document
    doc = doc:walk({traverse = "topdown", Div = calc_div, Para = fence_handler, RawBlock = raw_block,
      Inlines = process_inlines})
  end
  return doc
end}}

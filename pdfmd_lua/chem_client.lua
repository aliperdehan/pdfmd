-- pdfmd: the Lua side of pdfmd_chem (v3.28.10), shared by the LaTeX filter (pdfmd_office/office.lua) and chem.lua.
-- mhchem's \ce and \pu and siunitx's commands are converted by `python3 pdfmd_chem` (beside this file's folder), one
-- call for a batch: ask() sends the commands and formulas, answer() reads one answer back (asking for it alone when it
-- was not in a batch). An answer for a command in text has runs ({text, place}, place "" | "sup" | "sub"), its math
-- and whether only an equation shows it as LaTeX does (an arrow with words over it); for a formula, its math.

local M = {}

-- the commands: pdfmd.py's CHEM_COMMANDS and pdfmd_chem/batch.py's list are the same (tests/test_chem.py)
M.NAMES = {ce = true, cee = true, cf = true, pu = true, num = true, numlist = true, numrange = true,
  numproduct = true, si = true, unit = true, SI = true, qty = true, SIlist = true, qtylist = true, SIrange = true,
  qtyrange = true, ang = true}

-- a formula (or raw LaTeX) with one of the commands in it
function M.has(tex)
  for name in tex:gmatch("\\(%a+)") do
    if M.NAMES[name] then return true end
  end
  return false
end

-- the name of the command a piece of raw LaTeX starts with, when it is one of them
function M.command(raw)
  local name = raw:match("^%s*\\(%a+)")
  return name and M.NAMES[name] and name or nil
end

-- the LaTeX of a metadata value (header-includes): read with the preamble for \sisetup and \DeclareSIUnit
function M.latex_of(value)
  local parts = {}
  local function visit(item)
    if type(item) ~= "table" then return end
    if (item.t == "RawBlock" or item.t == "RawInline") and (item.format == "latex" or item.format == "tex") then
      parts[#parts + 1] = item.text
      return
    end
    for _, child in ipairs(item) do visit(child) end
  end
  visit(value)
  return table.concat(parts, "\n")
end

-- an equation can be shown: not in plain text or Markdown (a formula there is text), nor in an HTML page whose math
-- is plain (WeasyPrint's), unless MathJax or KaTeX typesets it there (v3.28.11, pdfmd_lua/weasyprint.lua)
function M.math_renders()
  if FORMAT:match("^plain") or FORMAT:match("^gfm") or FORMAT:match("^commonmark") or FORMAT:match("^markdown")
      or FORMAT == "asciidoc" or FORMAT == "rst" or FORMAT == "org" then
    return false
  end
  if not (FORMAT:match("^html") or FORMAT:match("^epub")) then return true end
  local method = PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.html_math_method
  method = type(method) == "table" and method.method or method
  local variables = PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.variables or {}
  return method ~= "plain" or variables["pdfmd-katex"] ~= nil or variables["pdfmd-mathjax"] ~= nil
end

-- the runs of an answer: text with its ordinary spaces as spaces, sub- and superscripts
function M.runs_inlines(runs)
  local out = {}
  local function words(text)
    local list = {}
    for piece, space in text:gmatch("([^ ]*)( ?)") do
      if piece ~= "" then list[#list + 1] = pandoc.Str(piece) end
      if space ~= "" then list[#list + 1] = pandoc.Space() end
    end
    return list
  end
  for _, run in ipairs(runs) do
    local text, place = run[1], run[2]
    if place == "sub" then out[#out + 1] = pandoc.Subscript(words(text))
    elseif place == "sup" then out[#out + 1] = pandoc.Superscript(words(text))
    else
      for _, item in ipairs(words(text)) do out[#out + 1] = item end
    end
  end
  return out
end

-- one command in text as inlines: its runs, or an equation where only one shows it and one can be shown; nil when
-- the converter cannot convert it
function M.inlines(answer)
  if not answer then return nil end
  if answer.needs_math and M.math_renders() then return {pandoc.Math("InlineMath", answer.math)} end
  return M.runs_inlines(answer.runs)
end

local Client = {}
Client.__index = Client

-- a client: `dir` the pdfmd_chem folder, `python` the interpreter (python3 without one), `preamble` a function
-- giving the document's preamble text, `store` a file kept between two runs of a filter (or nil)
function M.new(options)
  return setmetatable({dir = options.dir, python = options.python, preamble = options.preamble,
    store = options.store, cache = {}, calls = 0, failed = false}, Client)
end

function Client:key(kind, source) return (kind == "math" and "M" or "T") .. source end

function Client:ask(items)
  if self.failed or #items == 0 then return end
  self.calls = self.calls + 1
  local request = pandoc.json.encode({preamble = self.preamble and self.preamble() or "", items = items})
  local ok, out = pcall(pandoc.pipe, self.python or "python3", {self.dir}, request)
  local decoded, answers = false, nil
  if ok then decoded, answers = pcall(pandoc.json.decode, out, false) end
  if not decoded or type(answers) ~= "table" then
    self.failed = true
    io.stderr:write("[pdfmd] WARN the converter of \\ce and siunitx (pdfmd_chem) could not run; LaTeX draws them\n")
    return
  end
  for index, item in ipairs(items) do
    self.cache[self:key(item.math and "math" or "text", item.math or item.text)] = answers[index] or {error = "none"}
  end
end

-- the converter's answer for one command in text ("text") or one formula ("math"); nil when it cannot convert it
function Client:answer(kind, source)
  local key = self:key(kind, source)
  if self.cache[key] == nil then self:ask({kind == "math" and {math = source} or {text = source}}) end
  local answer = self.cache[key]
  if answer == nil or answer.error then return nil end
  return answer
end

-- a batch: `items` gathered with add() (repeats and known ones left out), sent by flush()
function Client:batch()
  local client, items, seen = self, {}, {}
  return {
    add = function(kind, source)
      local key = client:key(kind, source)
      if seen[key] or client.cache[key] ~= nil then return end
      seen[key] = true
      items[#items + 1] = kind == "math" and {math = source} or {text = source}
    end,
    flush = function() client:ask(items) end,
  }
end

-- the answers a run before this one kept (the collect run's, for the render run), and keeping them
function Client:load()
  local file = self.store and io.open(self.store, "r")
  if not file then return end
  local ok, saved = pcall(pandoc.json.decode, file:read("a"), false)
  file:close()
  if ok and type(saved) == "table" then
    for key, value in pairs(saved) do self.cache[key] = value end
  end
end

function Client:save()
  if not self.store or next(self.cache) == nil then return end
  local file = io.open(self.store, "w")
  if file then file:write(pandoc.json.encode(self.cache)); file:close() end
end

return M

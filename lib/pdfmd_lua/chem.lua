-- pdfmd: mhchem's \ce and \pu and siunitx's commands for outputs the LaTeX filter does not run for (v3.28.10): an
-- HTML or EPUB file, Markdown (gfm), text (txt, ascii), a .typ file, a PowerPoint deck. Their writers drop raw LaTeX:
-- `Water \ce{H2O} and \qty{25}{\mL}` was "Water and", and `$\ce{CO2}$` stayed TeX. Each command in text becomes text
-- with sub- and superscripts (an arrow with words over it an equation, where the output can show one); a formula with
-- them in it gets them converted. pdfmd_chem does the converting, in one call (pdfmd_lua/chem_client.lua).
--
-- pdfmd adds it only when the document has such a command, after the document's own filters, and sets its metadata:
-- `pdfmd-chem-python` (the Python to run) and `pdfmd-chem-preamble` (the LaTeX preamble files, for \sisetup and
-- \DeclareSIUnit). Both are removed once read, so that no output writes them out.

local here = (debug.getinfo(1, "S").source or ""):match("^@(.*)$") or ""
local folder = (here:gsub("[/\\][^/\\]*$", ""))
local loaded, chem = pcall(dofile, folder .. "/chem_client.lua")
if not loaded then
  io.stderr:write("[pdfmd] WARN pdfmd_lua/chem_client.lua could not be loaded (" .. tostring(chem) .. ")\n")
  return {}
end

local python, preamble_file, header = nil, nil, ""

local function Meta(meta)
  if meta["pdfmd-chem-python"] then python = pandoc.utils.stringify(meta["pdfmd-chem-python"]) end
  if meta["pdfmd-chem-preamble"] then preamble_file = pandoc.utils.stringify(meta["pdfmd-chem-preamble"]) end
  if meta["header-includes"] ~= nil then header = chem.latex_of(meta["header-includes"]) end
  meta["pdfmd-chem-python"], meta["pdfmd-chem-preamble"] = nil, nil
  return meta
end

local function preamble()
  local parts, separator = {}, package.config:sub(1, 1) == "\\" and ";" or ":"
  for path in ((preamble_file or "") .. separator):gmatch("([^" .. separator .. "]+)" .. separator) do
    local file = io.open(path, "r")
    if file then parts[#parts + 1] = file:read("a"); file:close() end
  end
  parts[#parts + 1] = header
  return table.concat(parts, "\n")
end

local function is_tex(element) return element.format == "latex" or element.format == "tex" end

-- a command or formula the converter refused: one WARN naming it and the reason, once (v3.30.25; the output used to
-- lose it without a word)
local warned = {}
local function lost(client, kind, source, outcome)
  local answer = client.cache[client:key(kind, source)]
  if type(answer) ~= "table" or not answer.error or warned[kind .. source] then return end
  warned[kind .. source] = true
  io.stderr:write("[pdfmd] WARN " .. source:gsub("%s+", " ") .. " cannot be converted (" .. tostring(answer.error)
    .. "); " .. outcome .. "\n")
end

local function Pandoc(doc)
  local client = chem.new({dir = (folder:gsub("[/\\][^/\\]*$", "")) .. "/pdfmd_chem", python = python,
    preamble = preamble})
  local batch = client:batch()
  -- in text and Markdown a formula that is one command is its text (no equation there: an arrow's words follow it)
  local as_text = not chem.math_renders()
  doc:walk({
    Math = function(el)
      if not chem.has(el.text) then return end
      batch.add("math", el.text)
      if as_text and chem.command(el.text) then batch.add("text", el.text) end
    end,
    RawInline = function(el) if is_tex(el) and chem.command(el.text) then batch.add("text", el.text) end end,
    RawBlock = function(el) if is_tex(el) and chem.command(el.text) then batch.add("text", el.text) end end,
  })
  batch.flush()
  return doc:walk({
    Math = function(el)
      if not chem.has(el.text) then return nil end
      if as_text and chem.command(el.text) then
        local inlines = chem.inlines(client:answer("text", el.text))
        if inlines then return inlines end
      end
      local answer = client:answer("math", el.text)
      if not answer then lost(client, "math", el.text, "the formula stays TeX") end
      return answer and pandoc.Math(el.mathtype, answer.math) or nil
    end,
    RawInline = function(el)
      if not (is_tex(el) and chem.command(el.text)) then return nil end
      local inlines = chem.inlines(client:answer("text", el.text))
      if not inlines then lost(client, "text", el.text, "it is left out") end
      return inlines
    end,
    RawBlock = function(el)
      if not (is_tex(el) and chem.command(el.text)) then return nil end
      local inlines = chem.inlines(client:answer("text", el.text))
      if not inlines then lost(client, "text", el.text, "it is left out") end
      return inlines and pandoc.Para(inlines) or nil
    end,
  })
end

return {{Meta = Meta, Pandoc = Pandoc}}

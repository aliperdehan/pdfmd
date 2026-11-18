-- pdfmd P1a: a page marker in a Para/Plain refers to that block's last source.
-- Runs before crossref and citeproc. Notes and every cell/list paragraph have their own scope.
local config
local function message(text) io.stderr:write("WARN  pagecite: " .. text .. "\n") end
local function clean(text)
  return text:gsub("\194\160", " "):gsub("%-%-", "–")
end
local function marker(text)
  local lower = text:lower()
  for _, term in ipairs(config.terms) do
    if lower:sub(1, #term) == term:lower() then
      local rest = lower:sub(#term + 1)
      if rest:find("[0-9]") or rest:find("%f[%a][ivxlcdm]+%f[%A]") then return true end
    end
  end
  return false
end
local function crossref(key)
  for _, prefix in ipairs({"fig:", "tbl:", "eq:", "sec:", "lst:"}) do
    if key:sub(1, #prefix) == prefix then return true end
  end
  return false
end

local process
process = function(inlines, state, linked)
  local out = pandoc.Inlines({})
  local i = 1
  while i <= #inlines do
    local el = inlines[i]
    if el.t == "Cite" then
      local key, count, seen = nil, 0, {}
      for _, citation in ipairs(el.citations) do
        if not crossref(citation.id) then
          key = citation.id
          if not seen[key] then count = count + 1; seen[key] = true end
        end
      end
      if key then state.key, state.multi = key, count > 1 end
      out:insert(el)
      i = i + 1
    elseif not linked and (el.t == "Str" or el.t == "Space" or el.t == "SoftBreak") then
      -- Pandoc may join punctuation and whole markers in one Str, or split at any space.
      local pieces, j = {}, i
      while j <= #inlines do
        local item = inlines[j]
        if item.t == "Str" then pieces[#pieces + 1] = item.text
        elseif item.t == "Space" or item.t == "SoftBreak" then pieces[#pieces + 1] = " "
        else break end
        j = j + 1
      end
      local text = table.concat(pieces)
      local cursor, changed, pending = 1, false, ""
      local function emit(words)
        if words ~= "" then out:extend(pandoc.Inlines({pandoc.Str(words)})) end
      end
      while cursor <= #text do
        local first, last, words = text:find("%[([^%]]*)%]", cursor)
        if not first then pending = pending .. text:sub(cursor); break end
        pending = pending .. text:sub(cursor, first - 1)
        if marker(clean(words)) then
          local typed = clean(words)
          if not state.key then
            message("no citation before [" .. typed .. "]")
            pending = pending .. text:sub(first, last)
          else
            changed = true
            if state.multi then message("[" .. typed .. "] follows several sources, using " .. state.key) end
            if config.mode == "drop" then
              pending = pending:gsub("[ \t\n]+$", "")
            else
              emit(pending); pending = ""
              if config.mode == "style" then
                local suffix = pandoc.read(typed, "markdown").blocks[1].content
                local citation = pandoc.Citation(state.key, "NormalCitation")
                citation.suffix = suffix
                out:insert(pandoc.Cite({pandoc.Str("[@" .. state.key .. ", " .. typed .. "]")}, {citation}))
              else
                local words = config.opening .. typed .. config.closing
                if config.opening == "[" then
                  -- A project’s older Para/Plain filter must not mistake square citation brackets
                  -- for a second unprocessed marker. The span stays literal in every writer.
                  out:insert(pandoc.Span({pandoc.Str(words)}, pandoc.Attr("", {"pagecite"})))
                else emit(words) end
              end
            end
          end
        else pending = pending .. text:sub(first, last) end
        cursor = last + 1
      end
      if changed then emit(pending)
      else
        -- Keep untouched reader output byte-for-byte, including SoftBreaks and its word boundaries.
        for index = i, j - 1 do out:insert(inlines[index]) end
      end
      i = j
    else
      -- Inline containers share the surrounding block's source. A Note's blocks were walked separately;
      -- code, math and raw inlines are opaque. Links may carry citations, but never page markers.
      if el.content and el.t ~= "Note" and el.t ~= "Image" and
          not (el.t == "Span" and el.classes:includes("pagecite")) then
        el.content = process(el.content, state, linked or el.t == "Link")
      end
      out:insert(el)
      i = i + 1
    end
  end
  return out
end

local function restore(el)
  el.text = el.text:gsub(config.escaped:gsub("(%W)", "%%%1"), el.t == "Str" and "[" or "\\[")
  return el
end
return {{Pandoc = function(doc)
  local path = doc.meta["pdfmd-pagecite-config"]
  if not path then return doc end
  local file = assert(io.open(pandoc.utils.stringify(path), "rb"))
  config = pandoc.json.decode(file:read("*a"))["pdfmd-pagecite"]
  file:close()
  doc.meta["pdfmd-pagecite-config"] = nil
  doc = doc:walk({Para = function(el) el.content = process(el.content, {}); return el end,
                 Plain = function(el) el.content = process(el.content, {}); return el end})
  -- Restore only after all marker recognition, so an escaped marker can never be reconsidered.
  return doc:walk({Str = restore, Code = restore, CodeBlock = restore, RawInline = restore, RawBlock = restore})
end}}

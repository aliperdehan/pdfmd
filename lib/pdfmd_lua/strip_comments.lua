-- Code blocks and code spans are parsed nodes, never RawBlock/RawInline: their examples remain text.
-- Keep the marker families read by pdfmd's discovery, pagebreak.lua and markup.lua.
local function marker(body)
  local word = body:lower():match("^%s*(.-)%s*$")
  return word:match("^pdfmd%W") or word == "pdfmd" or word == "toc" or word == "appendix"
    or word == "pagebreak" or word == "page-break" or word == "newpage" or word == "new-page"
end

local function strip(raw)
  if raw.format ~= "html" then return nil end
  local text = raw.text:gsub("<!%-%-(.-)%-%->", function(body)
    return marker(body) and "<!--" .. body .. "-->" or ""
  end)
  if text == raw.text then return nil end
  if text:match("^%s*$") then return {} end
  raw.text = text
  return raw
end

return {{RawBlock = strip, RawInline = strip}}

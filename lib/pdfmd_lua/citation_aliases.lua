local function decode(hex)
  return (hex:gsub("..", function(byte) return string.char(tonumber(byte, 16)) end))
end

function Pandoc(doc)
  local encoded = pandoc.utils.stringify(doc.meta["pdfmd-citation-aliases"])
  doc.meta["pdfmd-citation-aliases"] = nil

  -- Include uncited entries in the key check without changing the bibliography that citeproc prints.
  local nocite = doc.meta.nocite
  doc.meta.nocite = pandoc.MetaInlines{pandoc.Cite({pandoc.Str("@*")}, {pandoc.Citation("*", "NormalCitation")})}
  local keys = {}
  for _, ref in ipairs(pandoc.utils.references(doc)) do
    keys[pandoc.utils.stringify(ref.id)] = true
  end
  doc.meta.nocite = nocite

  local aliases = {}
  for short_hex, target_hex in encoded:gmatch("(%x+):(%x+)") do
    local short, target = decode(short_hex), decode(target_hex)
    if keys[short] then
      io.stderr:write("WARN  citation-aliases: '" .. short .. "' is a bibliography key; keeping it\n")
    elseif not keys[target] then
      io.stderr:write("WARN  citation-aliases: '" .. short .. "' targets missing key '" .. target .. "'; keeping the citation as written\n")
    else
      aliases[short] = target
    end
  end
  return doc:walk({
    Cite = function(cite)
      for _, citation in ipairs(cite.citations) do
        citation.id = aliases[citation.id] or citation.id
      end
      return cite
    end,
    Span = function(span)
      local keys = span.attributes["pdfmd-keys"]
      if span.classes:includes("fullcite") and keys then
        span.attributes["pdfmd-keys"] = keys:gsub("%S+", aliases)
        return span
      end
    end,
  })
end

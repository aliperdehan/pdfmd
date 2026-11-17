-- Last content pass, before writer-specific flattening: hidden answers never enter the output.
local function remove(element)
  if element.classes:includes("pdfmd-hidden-content") then return {} end
end
return {{Pandoc = function(doc)
  doc = doc:walk({Div = remove, Span = remove})
  if FORMAT:match("^typst") then
    local hidden = {}
    for _, id in ipairs(doc.meta["pdfmd-hidden-labels"] or {}) do hidden[pandoc.utils.stringify(id)] = true end
    doc = doc:walk({Link = function(el)
      if hidden[el.target:sub(2)] then return el.content end
    end})
  end
  doc.meta["pdfmd-hidden-labels"] = nil
  return doc
end}}

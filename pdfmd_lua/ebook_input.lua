-- pdfmd: an ebook read as Markdown (v3.29.2). Calibre's EPUB carries scaffolding that means nothing in Markdown: an empty
-- anchor for every file it split the book into (`[]{#index_split_001.html}`), page-break divs, a class on every span
-- (`.calibre1`). This filter drops what is empty and not the target of a link, and the classes of the converter; the words,
-- headings, lists, tables, pictures and links are not touched.
local targets = {}

local function noisy_class(class)
  return class:match("^calibre") or class:match("^mbp_") or class:match("^pagebreak") or class:match("^pdf_page")
end

local function clean_attr(element)
  local kept = {}
  for _, class in ipairs(element.classes) do
    if not noisy_class(class) then kept[#kept + 1] = class end
  end
  element.classes = kept
  return element
end

local function unused(element)
  return element.identifier == "" or not targets[element.identifier]
end

local function bare(element)
  return element.identifier == "" and #element.classes == 0 and #element.attributes == 0
end

return {
  {Link = function(link)
    local id = link.target:match("^#(.+)$")
    if id then
      targets[id] = true
      targets[id:match("([^#]+)$")] = true            -- Pandoc 3.1 writes a link as #ch002.xhtml#target
    end
  end},
  {
    Span = function(span)
      if #span.content == 0 and unused(span) then return {} end
      clean_attr(span)
      if bare(span) then return span.content end
      return span
    end,
    Div = function(div)
      if #div.content == 0 and unused(div) then return {} end
      clean_attr(div)
      if bare(div) then return div.content end
      return div
    end,
    Image = function(image)
      return clean_attr(image)
    end,
  },
}

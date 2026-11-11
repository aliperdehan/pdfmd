-- pdfmd: for the live view of `pdfmd --serve` (entry 3do). Pandoc's `sourcepos` wraps every word of a paragraph in a span of its
-- own and every block that has no attributes in a div, and splits "{=}" into three words, so that each element has a position. The
-- filters that read a document's own syntax look at the document as the reader gives it (calc: code followed at once by "{=}",
-- the paragraphs inside its div), and a wrapper between them hides the pair.
-- This filter runs FIRST and puts the document back the way the reader gives it: the word wrappers go, neighbouring words are
-- one again, and so are the wrappers inside another block. The wrappers of the blocks of the document itself stay: they carry the
-- positions the source mirror of the live view reads (a block that has its own attributes keeps its position there).

-- Pandoc marks its wrappers with `wrapper="1"`; an older one (3.1.3 is the oldest pdfmd is tested with) does not, and its wrapper is
-- known by what it is: no identifier, no class and nothing but positions as its attributes (the wrapper of a list item has two of
-- them there, the item's and its paragraph's). Something the author wrote that carries nothing but a position, `[word]{}`, loses
-- nothing when it is taken for one.
local function wrapper(el)
  if el.attributes["wrapper"] == "1" then return true end
  if el.identifier ~= "" or #el.classes > 0 or el.attributes["data-pos"] == nil then return false end
  for name in pairs(el.attributes) do
    if name ~= "data-pos" then return false end
  end
  return true
end

local function strip_inline(el)
  if wrapper(el) then return el.content end
end

local function merge_words(inlines)
  local out, last = pandoc.Inlines({}), nil
  for _, item in ipairs(inlines) do
    if item.t == "Str" and last and last.t == "Str" then
      last = pandoc.Str(last.text .. item.text)
      out[#out] = last
    else
      out:insert(item)
      last = item
    end
  end
  return out
end

local function strip_block(el)
  if wrapper(el) then return el.content end
end

local function inside(block)
  return pandoc.walk_block(block, {Div = strip_block})
end

return {
  {Span = strip_inline},
  {Inlines = merge_words},
  {Pandoc = function(doc)
    local blocks = pandoc.Blocks({})
    for _, block in ipairs(doc.blocks) do
      if block.t == "Div" and wrapper(block) then
        block.content = pandoc.Blocks(block.content:map(inside))
        blocks:insert(block)
      else
        blocks:insert(inside(block))
      end
    end
    return pandoc.Pandoc(blocks, doc.meta)
  end},
}

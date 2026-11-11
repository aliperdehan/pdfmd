-- pdfmd: a picture alone in its paragraph is a figure with its caption, for a Pandoc whose gfm reader does not make one.
--
-- The pdfmd and obsidian flavours read a file without front matter as `gfm+implicit_figures`. A newer Pandoc's CommonMark readers
-- apply the extension; an older one (3.1.3, the oldest pdfmd is tested with) accepts the name and does nothing, so the picture
-- stayed an inline image and its caption only an alt text. This filter does what the reader would have done, in the same shape:
-- the paragraph that holds one image with a caption and nothing else becomes a Figure, the image's identifier goes to the
-- figure, the caption is the image's text. Where the reader made the figures itself no such paragraph is left, and the filter
-- changes nothing; a picture with no caption, or with anything beside it in the paragraph, is not a figure for either.

-- Only where the reader was asked for figures (`--from gfm`, `flavour: gfm` and the like ask for none).
local asked = false
for _, extension in ipairs(PANDOC_READER_OPTIONS.extensions) do
  if extension == "implicit_figures" then asked = true end
end

function Para(para)
  if not asked then return nil end
  if #para.content ~= 1 or para.content[1].t ~= "Image" then return nil end
  local image = para.content[1]
  if #image.caption == 0 then return nil end
  local identifier = image.identifier
  image.identifier = ""
  return pandoc.Figure({pandoc.Plain({image})}, {long = {pandoc.Plain(image.caption)}}, pandoc.Attr(identifier))
end

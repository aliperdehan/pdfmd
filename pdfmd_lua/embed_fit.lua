-- pdfmd: keeps a sized picture embed (`![[img|900]]`, `data-pdfmd-fit="text-width"`) within the text width (v3.32.25, entry 3ee).
-- Pandoc's LaTeX writer takes `width=900pt` as it stands, so a picture wider than the text runs into the margin; here the width
-- becomes `\ifdim 900pt>\linewidth \linewidth\else 900pt\fi` in a LaTeX build. HTML gets `max-width: 100%`; Word scales to the page itself.

local function unescape(path)
  return (path:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))
end

local function tex_path(path)
  return (path:gsub("([%%#])", "\\%1"))
end

function Image(image)
  if image.attributes["data-pdfmd-fit"] ~= "text-width" then return nil end
  image.attributes["data-pdfmd-fit"] = nil
  local width, height = image.attributes["width"], image.attributes["height"]
  if FORMAT:match("^html") or FORMAT == "epub" or FORMAT:match("^epub") then
    local style = image.attributes["style"]
    image.attributes["style"] = (style and (style .. ";") or "") .. "max-width: 100%"
    return image
  end
  if (FORMAT == "latex" or FORMAT == "beamer") and width and width:match("pt$") then
    local options = "width=\\ifdim " .. width .. ">\\linewidth \\linewidth\\else " .. width .. "\\fi"
    options = options .. (height and (",height=" .. height) or ",height=\\textheight")
    options = options .. ",keepaspectratio"
    return pandoc.RawInline("latex", "\\includegraphics[" .. options .. "]{" .. tex_path(unescape(image.src)) .. "}")
  end
  return image
end

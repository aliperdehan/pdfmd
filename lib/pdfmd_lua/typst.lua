-- pdfmd: what Typst needs that Pandoc's Typst writer does not give it (v3.27.11). Runs last before the writer.
--
-- Links to anchors that are not in the document. LaTeX and HTML only warn about a link to an id nothing carries; Typst
-- stops the build ("label <x> does not exist in the document"). A pasted transcript that quotes another document's
-- `(see 13.5)` links is enough. Each such link becomes its text, and one WARN says which. Pandoc's Typst writer gives a
-- label to a heading, a div, a span, a figure and a table with an id (Pandoc 3.1.3 and 3.12 alike); a code block, an
-- image, inline code and a link keep theirs only in the AST, so a link to one of those is made text as well.
--
-- A label on two elements stops Typst too ("label <x> occurs multiple times", v3.28.2: a lab report through pdfmd's
-- LaTeX filter, where a drawn figure environment and its own label both carried it): the first keeps it, one WARN.
--
-- Pictures, with a Pandoc before 3.2 building a PDF: it runs Typst in its own working folder (a discovered metadata
-- file's, not always the document's) without fetching the pictures first, so a relative path is looked for there. Each
-- is made the absolute path of the file found on the resource path (pdfmd gives Typst --root=/ with such a Pandoc).
--
-- A landscape page (v3.30.42). The template has no variable for it: pdfmd sets `pdfmd-page-flipped` (for `papersize:
-- a4,landscape`, `geometry: landscape`, `classoption: landscape`) and `#set page(flipped: true)` goes into
-- `header-includes`, ahead of the template's own page rule, which leaves the flip alone. An --include-in-header replaces
-- it, as it replaces the document's own header-includes.
--
-- The document's own indent (v3.33.42). `indent: true` in the front matter gives LaTeX a first-line indent (Pandoc's
-- LaTeX template drops its parskip); Pandoc's Typst template has no such variable, so Typst printed no indent at all.
-- `#set par(first-line-indent: 1.5em)` goes into `header-includes` the same way (1.5em, what `indent=true` means for an
-- indent div, indent.lua). Typst, like LaTeX, leaves the first paragraph after a heading unindented. An indent div
-- inside the document still sets its own stretch.
--
-- The space between paragraphs (v3.33.58). With `indent: true` LaTeX also drops the space between paragraphs (the parskip
-- package is not loaded): the next paragraph starts one line below. Typst kept its own 1.2em; it now gets its line spacing
-- too. Typst measures a paragraph's spacing as it measures its leading (edge to edge), so spacing = leading is that one
-- line, and the leading is the one the line spacing below sets. `pdfmd-options.paragraph-spacing` (pdfmd passes it as
-- `pdfmd-paragraph-spacing`) is the room added to that, as LaTeX's \parskip is added to the line pitch: `#set par(spacing:
-- <leading> + 6pt)`. Without either, Typst's own room is kept (v3.33.73): its default spacing less its default leading,
-- 1.2em - 0.65em, added to the leading, so a paragraph break stays 0.55em more than a line at any linestretch (Typst's
-- own 1.2em edge to edge was less than a line from a linestretch of about 1.6). `par.spacing` is Typst 0.12's, the
-- oldest pdfmd builds with (v3.33.62).
--
-- The line spacing (v3.33.73). LaTeX puts lines linestretch x \baselineskip apart, the class's for the size (size10.clo,
-- size11.clo, size12.clo: 12pt, 13.6pt, 14.5pt; setspace's \setstretch), whatever the font. Pandoc's Typst template sets
-- `leading: linestretch * 0.65em`, and Typst's line box runs from the cap height to the baseline (font metrics), so a
-- line was leading + cap height apart: 23.48 pt at linestretch 2, 12 pt Times, where LaTeX has 28.89, and about 1.31em
-- at linestretch 1 where LaTeX has 1.2. The box is made the same for every font (`top-edge: 0.7em`, `bottom-edge:
-- "baseline"`) and the leading is LaTeX's pitch less that box, in em, so a larger or smaller text keeps the ratio. A TeX
-- point is 1/72.27 in, Typst's 1/72 in, so the pitch is scaled by 72/72.27 to be the same length on the page. The rules
-- go at the top of the body, not into header-includes: the template's own `set par(leading: ...)` sits inside `conf`,
-- around the body, and would override a header rule, while a raw `#set par(leading: ...)` later in the document still
-- overrides this one. pdfmd also supplies these lengths to its copy of the default template, inside `conf`, for the
-- title block, abstract and outline (v3.33.162). Only for a
-- standalone document (a template): a fragment is someone else's to space.
--
-- The reference list's entry spacing (v3.33.59). Pandoc's template turns a CSL `entry-spacing="N"` into `#show <refs>: set
-- par(spacing: Nem)`, but Typst measures that spacing edge to edge, from one line's baseline to the next line's cap height,
-- where the line spacing inside an entry is the leading plus that height. So entry-spacing 0 printed each entry's first line
-- on top of the previous entry's last line (pitch = cap height, 7.95 pt at 12 pt Times), and 1 put entries closer than the
-- lines of one entry when linestretch is above about 1.5. LaTeX sets `\itemsep` to N x `\baselineskip`: N lines added to
-- the line pitch. A `#show:` rule at the top of the `refs` div gives Typst the same: spacing = leading + N x (leading +
-- line height). Only for a whole N >= 0, where Pandoc's template writes a spacing (it writes none for 2.5, nor without the
-- attribute, and the entries then keep the paragraph spacing, as before). The template's own rule already needs Typst 0.12.

--
-- Author names in another script's font (v3.33.65). pdfmd's font filter (pdfmd_unicode, run before this one) sets a run the
-- main font lacks (李雷, 山田太郎, 김민준) as `#text(font: ("X",), lang: "zh")[...]`, in the metadata too. Pandoc's template
-- makes the PDF's Author with `content-to-string(author.name)`, which reads a text, a sequence or a `body`, and `#text(..)[..]`
-- is styled content, none of them: the name was dropped from the Author (`, Alice Able,  & `), and an author list of one
-- such name stopped the build ("expected string or array, found none"). In an author's name each such run becomes
-- `#box[...]<pdfmd-author-font-N>` (a box has a `body`) with `#show <pdfmd-author-font-N>: set text(...)` in the
-- header-includes, one label for each font setting: the same font in the title block, the name in the Author. An
-- --include-in-header replaces the header-includes and with them the rule: the name is then set in Typst's own fallback
-- font, still in the Author.

if not FORMAT:match("^typst") then return {} end

local LABELLED = {Header = true, Div = true, Span = true, Figure = true, Table = true}

local function decoded(text)
  return (text:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))
end

local function plain_missing_links(doc)
  local labels, repeated = {}, {}
  local function collect(element)
    local identifier = element.identifier
    if not identifier or identifier == "" then return nil end
    if labels[identifier] then
      repeated[#repeated + 1] = identifier
      element.identifier = ""
      return element
    end
    labels[identifier] = true
  end
  local collector = {traverse = "topdown"}            -- in the order of the document: the first one keeps its label
  for name in pairs(LABELLED) do collector[name] = collect end
  doc = doc:walk(collector)
  if #repeated > 0 then
    local shown = {}
    for index = 1, math.min(#repeated, 5) do shown[index] = repeated[index] end
    io.stderr:write(string.format("WARN  typst: %d label%s on more than one element (%s%s): only the first keeps it, "
      .. "Typst stops on a label used twice\n", #repeated, #repeated == 1 and "" or "s", table.concat(shown, ", "),
      #repeated > 5 and string.format(" and %d more", #repeated - 5) or ""))
  end

  local missing, order = {}, {}
  doc = doc:walk({Link = function(link)
    local target = link.target
    if target:sub(1, 1) ~= "#" or #target < 2 or labels[target:sub(2)] or labels[decoded(target:sub(2))] then
      return nil
    end
    if not missing[target] then
      missing[target] = 0
      order[#order + 1] = target
    end
    missing[target] = missing[target] + 1
    return link.content
  end})

  if #order > 0 then
    local count = 0
    for _, target in ipairs(order) do count = count + missing[target] end
    local shown = {}
    for index = 1, math.min(#order, 5) do shown[index] = order[index] end
    io.stderr:write(string.format("WARN  typst: %d link%s to anchors that are not in the document (%s%s) %s plain text: "
      .. "Typst stops on a link to a missing label\n", count, count == 1 and "" or "s", table.concat(shown, ", "),
      #order > 5 and string.format(" and %d more", #order - 5) or "", count == 1 and "was made" or "were made"))
  end
  return doc
end

local function readable(path)
  local handle = io.open(path, "rb")
  if handle then handle:close() return true end
  return false
end

local function absolute_pictures(doc)
  local output = (PANDOC_STATE.output_file or ""):lower()
  if not (PANDOC_VERSION < {3, 2}) or not output:match("%.pdf$") then return doc end
  local here = pandoc.system.get_working_directory()
  local folders = PANDOC_STATE.resource_path or {"."}
  return doc:walk({Image = function(image)
    local src = image.src
    if src == "" or src:match("^%a[%w+.-]*:") or pandoc.path.is_absolute(src) then return nil end
    for _, folder in ipairs(folders) do
      for _, name in ipairs({src, decoded(src)}) do
        local candidate = pandoc.path.join({folder, name})
        if not pandoc.path.is_absolute(candidate) then candidate = pandoc.path.join({here, candidate}) end
        if readable(candidate) then
          image.src = pandoc.path.normalize(candidate)
          return image
        end
      end
    end
  end})
end

local variables = PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.variables or {}

local function add_header(meta, text)
  local rule = pandoc.MetaBlocks({pandoc.RawBlock("typst", text)})
  local includes = meta["header-includes"]
  if includes == nil then
    meta["header-includes"] = pandoc.MetaList({rule})
  elseif pandoc.utils.type(includes) == "List" then
    includes:insert(rule)
    meta["header-includes"] = includes
  else
    meta["header-includes"] = pandoc.MetaList({includes, rule})
  end
end

local INDENT_DEFAULT = "1.5em"   -- indent.lua's DEFAULT: what `indent=true` means for a div
-- Typst's own default leading and paragraph spacing, 0.65em and 1.2em (format facts: `par.leading`, `par.spacing`); the
-- room a paragraph break adds when nothing sets it is their difference (see the top)
local TYPST_LEADING_EM = 0.65
local TYPST_SPACING_EM = 1.2
-- LaTeX's \baselineskip for the class's \normalsize (format facts: size10.clo \@xiipt, size11.clo 13.6, size12.clo 14.5,
-- in TeX points; the KOMA and memoir classes use the same three), by the size Pandoc gives the class
local BASELINESKIP = {[10] = 12, [11] = 13.6, [12] = 14.5}
-- for another size (the standard classes have none): TeX's usual 1.2 x the size (a convention, not a measurement)
local BASELINESKIP_RATIO = 1.2
local TEX_POINT = 72 / 72.27     -- a TeX point in Typst's (PostScript) points (a format fact)
local TYPST_FONTSIZE = 11        -- Pandoc's Typst template's `fontsize: 11pt` when the document sets none
-- the line box's top edge, the same for every font: about a cap height (0.66 to 0.72em in the usual fonts), so the
-- room around a heading, a table row or a block moves by a fraction of a point (a choice; the pitch does not depend on it)
local TOP_EDGE_EM = 0.7

-- `indent: true` (a YAML boolean, or the words true/yes/on): Pandoc's LaTeX template indents; the Typst one does not
local function indent_on(value)
  if value == nil then return false end
  if pandoc.utils.type(value) == "boolean" then return value end
  local word = pandoc.utils.stringify(value):lower()
  return word == "true" or word == "yes" or word == "on"
end

-- the template's linestretch: a -V variable first, then the metadata, else 1
local function linestretch(meta)
  local value = variables["linestretch"]
  if value == nil and meta.linestretch ~= nil then value = pandoc.utils.stringify(meta.linestretch) end
  return tonumber(value ~= nil and tostring(value) or "") or 1
end

-- the template's font size in points (a -V variable first, then the metadata, else the template's), nil for another unit
local function fontsize(meta)
  local value = variables["fontsize"]
  if value == nil and meta.fontsize ~= nil then value = pandoc.utils.stringify(meta.fontsize) end
  if value == nil then return TYPST_FONTSIZE end
  return tonumber(tostring(value):match("^%s*(%d+%.?%d*)%s*pt%s*$") or "")
end

-- a number of em as Typst writes it: four decimals at most, no trailing zeros
local function em(value)
  return (string.format("%.4f", value):gsub("0+$", ""):gsub("%.$", "")) .. "em"
end

-- the leading that puts lines LaTeX's linestretch x \baselineskip apart with a TOP_EDGE_EM line box (see the top)
local function leading(meta)
  local size = fontsize(meta)
  local skip = size and BASELINESKIP[size]
  local ratio = skip and skip / size or BASELINESKIP_RATIO
  return linestretch(meta) * ratio * TEX_POINT - TOP_EDGE_EM
end

-- the space between paragraphs: the leading for `indent: true`, plus paragraph-spacing when set, else plus Typst's own
local function spacing(meta, lead)
  local extra = meta["pdfmd-paragraph-spacing"] ~= nil and pandoc.utils.stringify(meta["pdfmd-paragraph-spacing"]) or nil
  if extra == "0pt" or (extra == nil and indent_on(meta.indent)) then return lead end
  return lead .. " + " .. (extra or em(TYPST_SPACING_EM - TYPST_LEADING_EM))
end

-- the line box, the leading and the paragraph spacing, for the top of a standalone document's body (see the top)
local function line_rules(meta)
  if not (PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.template ~= nil) then return nil end
  local lead = em(leading(meta))
  return string.format('#set text(top-edge: %s, bottom-edge: "baseline")\n#set par(leading: %s, spacing: %s)',
    em(TOP_EDGE_EM), lead, spacing(meta, lead))
end

local function page_rules(meta)
  local changed = false
  if variables["pdfmd-page-flipped"] ~= nil then
    add_header(meta, "#set page(flipped: true)")
    changed = true
  end
  if indent_on(meta.indent) then
    add_header(meta, "#set par(first-line-indent: " .. INDENT_DEFAULT .. ")")
    changed = true
  end
  if changed then return meta end
  return nil
end

local AUTHOR_LABEL = "pdfmd-author-font-"

-- the settings of a font filter's `#text(...)[` opener, or nil
local function opener(inline)
  if inline.t ~= "RawInline" or inline.format ~= "typst" then return nil end
  return inline.text:match("^#text%((.*)%)%[$")
end

-- `inlines` with each `#text(OPTIONS)[` ... `]` made `#box[` ... `]<label>`, or nil when there is none
local function labelled_runs(inlines, labels, rules)
  local out, changed, index = pandoc.List(), false, 1
  while index <= #inlines do
    local options, close = opener(inlines[index]), nil
    if options then
      local depth = 0
      for later = index + 1, #inlines do
        local item = inlines[later]
        if opener(item) then
          depth = depth + 1
        elseif item.t == "RawInline" and item.format == "typst" and item.text == "]" then
          if depth == 0 then close = later; break end
          depth = depth - 1
        end
      end
    end
    if close then
      local label = labels[options]
      if label == nil then
        label = AUTHOR_LABEL .. (#rules + 1)
        labels[options] = label
        rules[#rules + 1] = "#show <" .. label .. ">: set text(" .. options .. ")"
      end
      out:insert(pandoc.RawInline("typst", "#box["))
      for inner = index + 1, close - 1 do out:insert(inlines[inner]) end
      out:insert(pandoc.RawInline("typst", "]<" .. label .. ">"))
      index, changed = close + 1, true
    else
      out:insert(inlines[index])
      index = index + 1
    end
  end
  return changed and out or nil
end

-- the authors' names with their font runs labelled (see the top); true when one was
local function author_fonts(meta)
  local authors = meta.author
  if authors == nil then return false end
  local labels, rules = {}, {}
  local function relabel(value)
    if pandoc.utils.type(value) ~= "Inlines" then return value end
    return pandoc.Plain(value):walk({Inlines = function(inlines) return labelled_runs(inlines, labels, rules) end}).content
  end
  if pandoc.utils.type(authors) == "List" then
    for index, author in ipairs(authors) do
      if pandoc.utils.type(author) == "table" then
        if author.name ~= nil then author.name = relabel(author.name) end
        authors[index] = author
      else
        authors[index] = relabel(author)
      end
    end
  elseif pandoc.utils.type(authors) == "table" then
    if authors.name ~= nil then authors.name = relabel(authors.name) end
  else
    authors = relabel(authors)
  end
  if #rules == 0 then return false end
  meta.author = authors
  for _, rule in ipairs(rules) do add_header(meta, rule) end
  return true
end

local function meta_rules(meta)
  local labelled = author_fonts(meta)
  local paged = page_rules(meta) ~= nil
  if labelled or paged then return meta end
  return nil
end

-- The height of one line of text: Typst's line box runs from `text.top-edge` to `text.bottom-edge` (TOP_EDGE_EM and the
-- baseline in a standalone document, v3.33.73; Typst's own cap height otherwise), so any glyph measures the same; `X` is
-- only something to measure (a format fact)
local LINE_HEIGHT = "measure[X].height"

-- the `refs` div: its entries N lines apart (CSL entry-spacing), as LaTeX's \itemsep; nil leaves it to Pandoc's template
local function entry_spacing(div)
  if div.identifier ~= "refs" then return nil end
  local lines = tonumber(div.attributes["entry-spacing"] or "")
  if lines == nil or lines < 0 or lines ~= math.floor(lines) then return nil end
  local value = "par.leading"
  if lines > 0 then value = string.format("par.leading + %d * (par.leading + %s)", lines, LINE_HEIGHT) end
  div.content:insert(1, pandoc.RawBlock("typst", "#show: body => context { set par(spacing: " .. value .. "); body }"))
  return div
end

-- the document with its line rules at the top of the body
local function line_spacing(doc)
  local rules = line_rules(doc.meta)
  if rules then
    local lead = em(leading(doc.meta))
    doc.meta["pdfmd-typst-top-edge"] = pandoc.MetaString(em(TOP_EDGE_EM))
    doc.meta["pdfmd-typst-leading"] = pandoc.MetaString(lead)
    doc.meta["pdfmd-typst-spacing"] = pandoc.MetaString(spacing(doc.meta, lead))
    doc.blocks:insert(1, pandoc.RawBlock("typst", rules))
  end
  return doc
end

return {{Meta = meta_rules, Div = entry_spacing,
         Pandoc = function(doc) return line_spacing(absolute_pictures(plain_missing_links(doc))) end}}

-- pdfmd: Markdown inside raw LaTeX (v3.32.0, entry 3dc).
--
--   \textbf{\md{**bold** and $x^2$ and [@smith2020]}}
--   \caption{\md{Spectrum of *trans*-stilbene (see @fig:ir)}}
--   \begin{md}
--   Several paragraphs, a list, a table, a citation [@smith2020].
--   \end{md}
--
-- `\md{...}` (one line or several) and `\begin{md}...\end{md}` hold Markdown. Pandoc reads the macro as raw TeX and hands the
-- whole of it over unread; this filter reads the argument as Markdown (`pandoc.read`), so what it holds is part of the one
-- document: citations are resolved by --citeproc and `@fig:x` by pandoc-crossref, because this filter runs before both.
--
-- Where it works:
--   * a raw inline (`\textbf{\md{x}}`, `\md{x}` in a paragraph, a heading, a table cell): split into [raw TeX, the parsed
--     inlines, raw TeX]; every writer gets the parsed text, those with raw TeX keep the TeX around it;
--   * a raw block (a whole `tabular`, `figure`, `center` that Pandoc read as one block): the same pieces as one Plain block,
--     for the TeX writers only (the other writers drop the raw block, as they always did);
--   * `\begin{md}...\end{md}`: real blocks, for every writer.
--
-- Rules of the argument: braces must balance; a backslash escapes the next character (`\{`, `\}` are not counted); `%` and `#`
-- are Markdown, not a TeX comment or parameter. A `\md` followed by a letter (`\mdseries`) is another command.

local FORMAT_BASE = FORMAT:match("^[^+-]+") or FORMAT
-- the writers that keep a raw TeX block: the TeX ones, and the two that write the whole AST (pdfmd asks for json to see
-- which citations a document has)
local TEX_WRITERS = {latex = true, beamer = true, context = true, json = true, native = true}

local function is_tex(format)
  return format == "tex" or format == "latex"
end

local function complain(text)
  io.stderr:write("WARN  md: " .. text .. "\n")
end

-- the text after `\begin{md}` up to `\end{md}`: its content and the position after the end tag, or nil
local ENV_BEGIN = "\\begin{md}"
local ENV_END = "\\end{md}"

-- the argument of a `\md{` whose opening brace is at `open`: the text between the braces and the position after the closing
-- one, or nil when the braces never balance
local function braced(text, open)
  local depth = 0
  local index = open
  local length = #text
  while index <= length do
    local char = text:sub(index, index)
    if char == "\\" then
      index = index + 1                                   -- the escaped character is not a brace
    elseif char == "{" then
      depth = depth + 1
    elseif char == "}" then
      depth = depth - 1
      if depth == 0 then return text:sub(open + 1, index - 1), index + 1 end
    end
    index = index + 1
  end
  return nil
end

-- the pieces of a raw text: {kind = "raw" | "arg" | "env", text = ...}; one raw piece when there is no macro in it
local function split(text)
  local pieces = {}
  local raw_from = 1
  local index = 1
  local length = #text
  local found = false
  while index <= length do
    local char = text:sub(index, index)
    if char == "\\" then
      local kind, body, after
      if text:sub(index, index + #ENV_BEGIN - 1) == ENV_BEGIN then
        local stop = text:find(ENV_END, index + #ENV_BEGIN, true)
        if stop then
          body = text:sub(index + #ENV_BEGIN, stop - 1):gsub("^[ \t]*\r?\n", "")
          after = stop + #ENV_END
          kind = "env"
        else
          complain("\\begin{md} has no \\end{md}; left as it was")
        end
      elseif text:sub(index, index + 2) == "\\md" and not text:sub(index + 3, index + 3):match("%a") then
        local brace = text:match("^[ \t]*()%{", index + 3)
        if brace then
          local inner, next_at = braced(text, brace)
          if inner then
            body, after, kind = inner, next_at, "arg"
          else
            complain("\\md{ has no closing brace (a brace in the Markdown is written \\{ or \\}); left as it was")
          end
        end
      end
      if kind then
        found = true
        if index > raw_from then pieces[#pieces + 1] = {kind = "raw", text = text:sub(raw_from, index - 1)} end
        pieces[#pieces + 1] = {kind = kind, text = body}
        index = after
        raw_from = after
      else
        index = index + 2                                 -- `\\`, `\%`, `\md`-less commands: nothing to look at
      end
    else
      index = index + 1
    end
  end
  if not found then return nil end
  if raw_from <= length then pieces[#pieces + 1] = {kind = "raw", text = text:sub(raw_from)} end
  return pieces
end

local function read_blocks(markdown)
  local document = pandoc.read(markdown, "markdown")
  return document.blocks
end

local function read_inlines(markdown)
  return pandoc.utils.blocks_to_inlines(read_blocks(markdown))
end

-- inline context: every piece becomes inlines
local function inline_result(format, pieces)
  local out = pandoc.Inlines{}
  for _, piece in ipairs(pieces) do
    if piece.kind == "raw" then
      out:insert(pandoc.RawInline(format, piece.text))
    else
      out:extend(read_inlines(piece.text))
    end
  end
  return out
end

-- block context: a Plain of the inline pieces between the environments, and the environments' own blocks
local function block_result(format, pieces)
  local out = pandoc.Blocks{}
  local pending = pandoc.Inlines{}
  local tex = TEX_WRITERS[FORMAT_BASE]
  local function flush()
    if #pending > 0 then out:insert(pandoc.Plain(pending)) end
    pending = pandoc.Inlines{}
  end
  for _, piece in ipairs(pieces) do
    if piece.kind == "env" then
      flush()
      out:extend(read_blocks(piece.text))
    elseif tex then
      if piece.kind == "raw" then
        pending:insert(pandoc.RawInline(format, piece.text))
      else
        pending:extend(read_inlines(piece.text))
      end
    end
  end
  flush()
  return out
end

local WARNED_STR = false

return {
  {
    -- Pandoc reads a macro whose braces do not balance as plain text, so it never gets here as raw TeX: say so once
    Str = function(element)
      if not WARNED_STR and element.text:find("^\\md{") then
        WARNED_STR = true
        complain("a `\\md{` was left as text: its braces do not balance (write a brace of the Markdown as \\{ or \\})")
      end
      return nil
    end,
    RawInline = function(element)
      if not is_tex(element.format) then return nil end
      local pieces = split(element.text)
      if not pieces then return nil end
      return inline_result(element.format, pieces)
    end,
    RawBlock = function(element)
      if not is_tex(element.format) then return nil end
      local pieces = split(element.text)
      if not pieces then return nil end
      local has_env = false
      for _, piece in ipairs(pieces) do
        if piece.kind == "env" then has_env = true end
      end
      if not has_env and not TEX_WRITERS[FORMAT_BASE] then return nil end
      return block_result(element.format, pieces)
    end,
  },
}

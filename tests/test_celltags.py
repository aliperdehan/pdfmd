"""v3.32.31: cell tags of pipe tables and merged cells (entry 3fa, lib/pdfmd_tables/celltags.py + pdfmd_lua/cellalign.lua).

The pre-pass is tested as plain text in and out; the spans through real builds of pdfmd (LaTeX, HTML, Typst, Word, Markdown)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "lib"))

import pdfmd  # noqa: E402
from pdfmd_tables.celltags import DEFAULT_KINDS, find_tags, normalise, parse_attribute_line, parse_tokens  # noqa: E402

HEAD = "| h | i | j |\n|---|---|---|\n"


def cell(text: str, kinds=DEFAULT_KINDS):
    """The canonical text of a one-cell body row `| text |` in a one-column table."""
    out = normalise("| h |\n|---|\n| " + text + " |\n", kinds).text.splitlines()[2]
    return out.strip("| ").strip()


class Tokens(unittest.TestCase):
    def spec(self, content: str, arrows: bool = True):
        found = parse_tokens(content, arrows)
        return None if found is None else (found.h, found.v, tuple(found.merge))

    def test_letters_words_and_their_order(self):
        self.assertEqual(self.spec("tl"), ("l", "t", ()))
        self.assertEqual(self.spec("LT"), ("l", "t", ()))
        self.assertEqual(self.spec("top, left"), ("l", "t", ()))
        self.assertEqual(self.spec("bottom right"), ("r", "b", ()))
        self.assertEqual(self.spec("r"), ("r", "", ()))
        self.assertEqual(self.spec("b"), ("", "b", ()))

    def test_a_lone_c_is_horizontal_and_takes_the_free_axis_with_another_letter(self):
        self.assertEqual(self.spec("c"), ("c", "", ()))
        self.assertEqual(self.spec("m"), ("", "m", ()))
        for word in ("mc", "cm", "cc", "CM", "c,m", "centre middle", "center, middle"):
            self.assertEqual(self.spec(word), ("c", "m", ()), word)
        self.assertEqual(self.spec("lc"), ("l", "m", ()))
        self.assertEqual(self.spec("ct"), ("c", "t", ()))

    def test_merge_words_and_arrows_with_any_separators(self):
        for word in ("merge-up", "merge_up", "merge.up", "mergeup", "MergeUp", "^^"):
            self.assertEqual(self.spec(word), ("", "", ("up",)), word)
        self.assertEqual(self.spec("<<,t"), ("", "t", ("left",)))
        self.assertEqual(self.spec("^^tc"), ("c", "t", ("up",)))
        self.assertEqual(self.spec("vv >>"), ("", "", ("down", "right")))
        self.assertEqual(self.spec("merge-left, top, centre"), ("c", "t", ("left",)))

    def test_conflicts_are_reported_and_the_last_one_wins(self):
        found = parse_tokens("tb", True)
        self.assertEqual(found.v, "b")
        self.assertTrue(found.problems)
        self.assertTrue(parse_tokens("lr", True).problems)
        self.assertTrue(parse_tokens("lcc", True).problems)

    def test_anything_else_is_not_a_tag(self):
        for content in ("foo", "b c d", "mc12", "x", "", "http://a.b"):
            self.assertIsNone(self.spec(content), content)
        self.assertIsNone(self.spec("<<", arrows=False))


class Spellings(unittest.TestCase):
    def test_the_recommended_ampersand_form_takes_anything(self):
        self.assertEqual(cell("&mc& 12"), "<pc hc vm> 12")
        self.assertEqual(cell("12 &c&"), "<pc hc> 12")
        self.assertEqual(cell("a &c& b"), "<pc hc> a b")
        self.assertEqual(cell("&merge-left,top& x"), "<pc vt> x")   # nothing to the left: reported, the arrow is dropped, the rest stays

    def test_angle_form_for_letters_and_words_and_the_old_c(self):
        self.assertEqual(cell("<c> total"), "<pc hc> total")
        self.assertEqual(cell("<c>mid"), "<pc hc> mid")
        self.assertEqual(cell("<R> x"), "<pc hr> x")
        self.assertEqual(cell("<mc> x"), "<pc hc vm> x")
        self.assertEqual(cell("<bottom,right> x"), "<pc hr vb> x")
        self.assertEqual(cell("<C>"), "<pc hc>")

    def test_symbolic_arrows_are_never_read_inside_angle_brackets(self):
        self.assertEqual(cell("<<<> x"), "<<<> x")
        self.assertEqual(cell("<^^> x"), "<^^> x")

    def test_html_that_looks_like_a_tag_stays_html(self):
        for text in ("a<br>b", "<tr>", "<tt>x</tt>", "<b>bold</b> x", "<B>bold</B>", "<center>x</center>", "<i>it</i>", "<br/>"):
            self.assertEqual(cell(text), text, text)
        self.assertEqual(cell("<b> x"), "<pc vb> x")               # no closing tag: bottom
        self.assertEqual(cell("<rb> x"), "<pc hr vb> x")           # bottom right, written so that it is not <br>
        self.assertEqual(cell("<b,r> x"), "<pc hr vb> x")

    def test_ampersand_and_brace_tags_must_stand_apart(self):
        for text in ("AT&T and R&D", "Tom & Jerry &c& done", "a&c&b", "Q&A &x& z"):
            self.assertNotIn("<pc", cell(text) if "&c&" not in text else "", text)
        self.assertEqual(cell("Tom & Jerry &c&"), "<pc hc> Tom & Jerry")
        self.assertEqual(cell("{c} x", ("brace",)), "<pc hc> x")
        self.assertEqual(cell("K_{c} and \\textbf{b}", ("angle", "amp", "brace")), "K_{c} and \\textbf{b}")
        self.assertEqual(cell("[x]{.cls}", ("brace",)), "[x]{.cls}")

    def test_the_other_brackets_are_off_unless_asked_for(self):
        self.assertEqual(cell("{c} x"), "{c} x")
        self.assertEqual(cell("«c» x"), "«c» x")
        self.assertEqual(cell("«mc» x", ("guillemet",)), "<pc hc vm> x")

    def test_code_math_and_escapes_are_left_alone(self):
        for text in ("`&c&` x", "$a &c& b$ x", "\\&c& x", "\\<c> x", "$K<c>$"):
            self.assertNotIn("<pc", cell(text), text)

    def test_two_tags_in_one_cell_are_combined(self):
        self.assertEqual(cell("&c& x <t>"), "<pc hc vt> x")
        out = normalise("| h |\n|---|\n| &l& &r& x |\n")
        self.assertTrue(out.notes)
        self.assertIn("<pc hr> x", out.text)

    def test_only_pipe_tables_outside_code_are_read(self):
        text = "text &c& <c>\n\n```\n| a |\n|---|\n| &c& |\n```\n"
        self.assertEqual(normalise(text).text, text)
        front = "---\ntitle: T\nnote: '| a |'\n---\n\n| a |\n|---|\n| &c& |\n"
        self.assertIn("<pc hc>", normalise(front).text)

    def test_rows_without_outer_bars_are_rewritten_with_them(self):
        out = normalise("a | b\n--|--\n&c& 1 | 2\n").text
        self.assertEqual(out.splitlines()[2], "| <pc hc> 1 | 2|")


class Merging(unittest.TestCase):
    def table(self, *rows: str) -> list[str]:
        result = normalise(HEAD + "\n".join(rows) + "\n")
        self.notes = result.notes
        return [line.replace(" ", "") for line in result.text.splitlines()[2:]]

    def test_a_cell_to_the_left_and_above(self):
        out = self.table("| a | << | c |", "| d | e | f |")
        self.assertEqual(out, ["|<pcc2>a|<pcxl>|c|", "|d|e|f|"])
        out = self.table("| a | b | c |", "| ^^ | e | f |")
        self.assertEqual(out, ["|<pcr2>a|b|c|", "|<pcxu>|e|f|"])

    def test_the_arrow_points_at_the_owner_so_the_text_can_sit_on_either_side(self):
        self.assertEqual(self.table("| >> | b | c |"), ["|<pcc2>b|<pcxl>|c|"])
        self.assertEqual(self.table("| a | b | c |", "| vv | e | f |", "| x | y | z |"),
                         ["|a|b|c|", "|<pcr2>x|e|f|", "|<pcxu>|y|z|"])

    def test_a_two_by_two_region_and_a_chain(self):
        out = self.table("| a | << | << |", "| ^^ | << | << |")
        self.assertEqual(out, ["|<pcc3r2>a|<pcxl>|<pcxl>|", "|<pcxu>|<pcxl>|<pcxl>|"])

    def test_an_arrow_inside_a_tag_and_with_letters(self):
        self.assertEqual(self.table("| a | &<<,m& | c |", "| x | y | z |"), ["|<pcc2vm>a|<pcxl>|c|", "|x|y|z|"])
        out = normalise(HEAD + "| &^^,tc& | b | c |\n").text        # the arrow reaches the header cell: it spans two rows
        self.assertIn("| <pc r2 hc vt> h | i | j |", out)

    def test_header_cells_can_span_and_reach_into_the_body(self):
        out = normalise("| Name | Score | << |\n|--|--|--|\n| ^^ | A | B |\n").text
        self.assertIn("| <pc c2> Score | <pc xl> |", out)
        out = normalise("| Name | S |\n|--|--|\n| ^^ | A |\n").text
        self.assertIn("| <pc r2> Name | S |", out)

    def test_covered_text_is_never_dropped(self):
        out = self.table("| a | extra &<<& | c |")
        self.assertEqual(out, ["|<pcc2>a<br>extra|<pcxl>|c|"])
        self.assertTrue(any("nothing is dropped" in note.message for note in self.notes))
        self.assertEqual(self.table("| a | extra << | c |"), ["|a|extra<<|c|"])      # a bare arrow must be the whole cell

    def test_a_region_that_is_not_a_rectangle_is_not_merged(self):
        out = self.table("| a | << | c |", "| ^^ | e | f |")
        self.assertTrue(self.notes)
        self.assertNotIn("<pc", " ".join(out))
        self.assertIn("rectangle", self.notes[0].message)

    def test_an_arrow_that_points_outside_the_table_is_reported_and_dropped(self):
        self.assertEqual(self.table("| << | b | c |"), ["||b|c|"])
        self.assertTrue(self.notes)

    def test_an_empty_cell_is_never_merged_by_itself(self):
        self.assertEqual(self.table("| a | | c |"), ["|a||c|"])

    def test_a_short_row_is_padded_when_a_span_reaches_past_its_end(self):
        out = self.table("| a | b | c |", "| d | vv |", "| x | y | z |")
        self.assertEqual(out, ["|a|b|c|", "|d|<pcr2>y|", "|x|<pcxu>|z|"])
        self.assertEqual(self.notes, [])

    def test_a_bare_arrow_is_a_cell_of_its_own_and_a_word_in_prose_is_not_an_arrow(self):
        self.assertEqual(self.table("| a | vv | c |", "| d | y | f |")[0], "|a|<pcr2>y|c|")
        self.assertEqual(self.table("| a | vv b | c |"), ["|a|vvb|c|"])
        self.assertEqual(self.table("| a | ^^ and << | c |"), ["|a|^^and<<|c|"])

    def test_the_tag_stays_short_so_that_a_small_table_keeps_its_natural_width(self):
        out = normalise(HEAD + "| &cc& x | << | c |\n").text.splitlines()[2]
        self.assertLess(len(out), 72)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Build(unittest.TestCase):
    TABLE = ("| Name | Scores | << |\n|:-----|-------:|---:|\n| vv | A | B |\n| x | 1 | 2 |\n| Total | &c& 12 | << |\n| ^^ | y | z |\n")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, body: str, to: str = "tex", options: str = "") -> tuple[subprocess.CompletedProcess, str]:
        front = f"pdfmd-options: {{{options}}}\n" if options else ""
        (self.root / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        if to == "docx" and out.exists():
            with zipfile.ZipFile(out) as archive:
                return done, archive.read("word/document.xml").decode("utf-8")
        return done, (out.read_text(encoding="utf-8") if out.exists() else "")

    def test_latex_gets_multirow_and_multicolumn_and_no_tag(self):
        done, tex = self.build(self.TABLE)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\multirow{2}{*}{x}", tex)
        self.assertIn("\\multirow{2}{*}{Total}", tex)
        self.assertIn("\\multicolumn{2}{c@{}}{%\n12}", tex)
        self.assertNotIn("<pc", tex)
        self.assertNotIn("&<<&", tex)

    def test_a_small_table_with_tags_keeps_its_natural_width(self):
        done, tex = self.build(self.TABLE)
        self.assertNotIn("real{", tex)
        self.assertIn("\\begin{longtable}[]{@{}lrr@{}}", tex)

    def test_html_typst_and_word_get_the_spans(self):
        done, html = self.build(self.TABLE, "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('<th colspan="2"', html)
        self.assertIn('<td rowspan="2"', html)
        self.assertNotIn("<pc", html)
        done, typst = self.build(self.TABLE, "typ")
        self.assertIn("table.cell(rowspan: 2)[x]", typst)
        self.assertIn("colspan: 2", typst)
        done, word = self.build(self.TABLE, "docx")
        self.assertIn('<w:gridSpan w:val="2"', word)
        self.assertIn('<w:vMerge w:val="restart"', word)

    def test_a_span_down_from_the_header_moves_the_rows_into_the_header(self):
        done, html = self.build("| Name | Score | << |\n|--|--|--|\n| ^^ | A | B |\n| x | 1 | 2 |\n", "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        head = html.split("</thead>")[0]
        self.assertIn('<th rowspan="2"', head)
        self.assertIn("<th>A</th>", head.replace(' style="text-align: left;"', "").replace(' style="text-align: right;"', ""))
        self.assertIn("<td", html.split("</thead>")[1])

    def test_markdown_gets_the_tags_back_in_the_safe_form_and_they_read_again(self):
        done, md = self.build(self.TABLE, "commonmark_x")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("&<<&", md)
        self.assertIn("&^^&", md)
        self.assertNotIn("<pc", md)
        again = normalise(md)
        self.assertEqual(again.notes, [])
        self.assertGreaterEqual(again.cells, 4)

    def test_a_note_for_a_region_that_cannot_be_merged_and_the_build_goes_on(self):
        done, tex = self.build("| a | << | c |\n|--|--|--|\n| ^^ | e | f |\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("WARN  cell-tags", done.stdout)
        self.assertIn("rectangle", done.stdout)
        self.assertNotIn("multirow", tex)

    def test_off_leaves_every_tag_as_text(self):
        done, tex = self.build(self.TABLE, options="cell-align: off")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("multirow", tex)

    def test_the_bracket_setting_chooses_the_spellings(self):
        done, tex = self.build("| a | b |\n|--|--|\n| {c} x | &c& y |\n", options="table-tag-brackets: [brace]")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\multicolumn{1}{c}{x}", tex)
        self.assertNotIn("\\multicolumn{1}{c}{y}", tex)
        done, _ = self.build("| a |\n|--|\n| x |\n", options="table-tag-brackets: [round]")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("table-tag-brackets", done.stdout + done.stderr)


TABULARRAY = bool(shutil.which("kpsewhich") and subprocess.run(["kpsewhich", "tabularray.sty"], capture_output=True, text=True).stdout.strip())
VERTICAL = ("| Description | Top | Middle | Bottom |\n|:--|:--|:--|:--|\n"
            "| a long long long long long long long long long text that wraps over lines | &t& top | &m& middle | &b& bottom |\n"
            "| x | &mc& centred | y | z |\n\nTable: A caption {#tbl:v}\n")


class Vertical(unittest.TestCase):
    """Vertical alignment (v3.32.32): LaTeX draws it with tabularray's longtblr, HTML with a style."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, body: str, to: str = "tex") -> tuple[subprocess.CompletedProcess, str]:
        (self.root / "d.md").write_text(f"---\ntitle: T\n---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        return done, (out.read_text(encoding="utf-8") if out.exists() else "")

    def test_the_pre_pass_counts_the_cells_with_a_vertical_alignment(self):
        result = normalise(HEAD + "| &t& a | &lc& b | &c& c |\n")
        self.assertEqual((result.cells, result.tblr), (3, 2))

    @unittest.skipUnless(shutil.which("pandoc") and TABULARRAY, "needs Pandoc and LaTeX's tabularray")
    def test_latex_gets_a_longtblr_with_the_tabularray_words_for_top_middle_bottom(self):
        done, tex = self.build(VERTICAL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("\\begin{longtblr}[caption={A caption},label={tbl:v}]", tex)
        self.assertIn("\\usepackage{tabularray}", tex)
        for key in ("cell{2}{2}={}{valign=h}", "cell{2}{3}={}{valign=m}", "cell{2}{4}={}{valign=f}", "cell{3}{2}={}{halign=c,valign=m}"):
            self.assertIn(key, tex)
        self.assertIn("cells={valign=h}", tex)           # a baseline cell beside a middle one would misalign
        self.assertIn("rowhead=1", tex)
        self.assertNotIn("<pc", tex)
        self.assertNotIn("\\begin{longtable}", tex)

    @unittest.skipUnless(shutil.which("pandoc") and TABULARRAY, "needs Pandoc and LaTeX's tabularray")
    def test_a_table_without_a_caption_prints_no_caption_and_a_table_without_tags_stays_a_longtable(self):
        done, tex = self.build("| a | b |\n|--|--|\n| &m& x | y |\n\n| c | d |\n|--|--|\n| &c& p | q |\n")
        self.assertIn("caption={},entry=none,label=none", tex)
        self.assertIn("\\begin{longtable}", tex)                       # the second table has no vertical letter
        self.assertIn("\\multicolumn{1}{c}{p}", tex)

    @unittest.skipUnless(shutil.which("pandoc") and TABULARRAY, "needs Pandoc and LaTeX's tabularray")
    def test_spans_and_vertical_letters_together(self):
        done, tex = self.build("| G | S | << |\n|--|--|--|\n| ^^ | A | B |\n| tall &m& | 1 | 2 |\n| ^^ | 3 | 4 |\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("cell{1}{2}={c=2}{}", tex)
        self.assertIn("cell{1}{1}={r=2}{}", tex)
        self.assertIn("cell{3}{1}={r=2}{valign=m}", tex)
        self.assertIn("rowhead=2", tex)
        self.assertEqual(tex.count("\\\\"), 4)                          # the header row and three body rows

    @unittest.skipUnless(shutil.which("pandoc") and TABULARRAY and shutil.which("lualatex"), "needs Pandoc and a LaTeX with tabularray")
    def test_the_pdf_builds(self):
        (self.root / "d.md").write_text("---\ntitle: T\n---\n\n" + VERTICAL, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-o", "o.pdf", "--no-stamp", "--no-backup", "--no-auto",
                               "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.root / "o.pdf").stat().st_size > 1000)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_html_gets_a_vertical_align_style(self):
        done, html = self.build(VERTICAL, "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('<td style="text-align: left; vertical-align: top;">top</td>', html)
        self.assertIn('vertical-align: middle;">middle</td>', html)
        self.assertIn('vertical-align: bottom;">bottom</td>', html)
        self.assertNotIn("data-valign", html)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_without_tabularray_the_vertical_letters_are_ignored_in_latex_and_the_build_says_so(self):
        source = self.root / "w.md"
        source.write_text(VERTICAL, encoding="utf-8")
        with mock.patch.object(pdfmd, "tabularray_available", return_value=False), mock.patch.object(pdfmd, "TABLAY_NOTED", set()):
            arguments = pdfmd.cellalign_args(source, [])
            self.assertEqual(pdfmd.tblr_header_args(source, []), [])
        self.assertEqual(arguments[:2], ["-M", "pdfmd-tblr=off"])
        filter_path = arguments[-1]
        canonical = "| a | b |\n|--|--|\n| <pc vm> x | y |\n"
        done = subprocess.run(["pandoc", "-f", "markdown", "-t", "latex", "-M", "pdfmd-tblr=off", "--lua-filter", filter_path],
                              input=canonical, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("\\begin{longtable}", done.stdout)
        self.assertNotIn("longtblr", done.stdout)
        self.assertNotIn("<pc", done.stdout)


SIZED = ("| Name | Description | Qty |\n|:--|:--|--:|\n| apples | a long description that goes on and on and on | 3 |\n"
         "| pears | short | 12 |\n\n{widths=\"3cm * 15%\" row2.height=1.8cm col2.align=l,m valign=m}\n\nTable: Sized {#tbl:sized}\n")


class AttributeLine(unittest.TestCase):
    """Step 3 (v3.32.33): a `{...}` line under a table sets widths, heights and alignments for the table, a column or a row."""

    def words(self, line: str, columns: int = 3):
        return parse_attribute_line(line, columns)

    def test_widths_take_lengths_percentages_stars_and_auto(self):
        words, notes = self.words('widths="3cm, 30% * auto"', 4)
        self.assertEqual(words, ["c1w=3cm", "c2w=30%", "c3w=*", "c4w=auto"])
        self.assertEqual(notes, [])
        self.assertEqual(self.words("col2.width=12mm width=80%")[0], ["c2w=12mm", "w=80%"])

    def test_heights_belong_to_rows_or_the_table(self):
        self.assertEqual(self.words("row3.height=1.5cm height=1cm")[0], ["r3ht=1.5cm", "ht=1cm"])
        words, notes = self.words("col2.height=1cm")
        self.assertEqual(words, [])
        self.assertTrue(notes)

    def test_alignment_words_and_the_tiers_of_scope(self):
        self.assertEqual(self.words("col2.align=r,m row1.align=c align=left valign=middle")[0],
                         ["c2h=r", "c2v=m", "r1h=c", "h=l", "v=m"])
        self.assertEqual(self.words("valign=bottom")[0], ["v=b"])

    def test_what_is_wrong_is_reported_and_left_out(self):
        words, notes = self.words("width=big col9.width=2cm bogus=1 widths=1cm,2cm,3cm,4cm")
        self.assertEqual(words, ["c1w=1cm", "c2w=2cm", "c3w=3cm"])
        text = " ".join(notes)
        for part in ("big", "col9.width", "bogus", "4 widths"):
            self.assertIn(part, text)

    def test_the_line_under_a_table_becomes_a_carrier_in_its_first_header_cell_and_the_caption_stays_attached(self):
        out = normalise("| a | b |\n|--|--|\n| 1 | 2 |\n\n{col2.width=3cm}\n\nTable: Cap {#tbl:x}\n").text
        self.assertEqual(out, "| <pt c2w=3cm> a | b |\n|--|--|\n| 1 | 2 |\n\nTable: Cap {#tbl:x}\n")
        again = normalise("| a | b |\n|--|--|\n| 1 | 2 |\n\nTable: Cap {#tbl:x}\n\n{col2.width=3cm}\n").text
        self.assertEqual(again, out)                                   # under the caption too

    def test_a_braced_line_with_no_setting_is_not_an_attribute_line(self):
        for text in ("| a |\n|--|\n| 1 |\n\n{#tbl:x .unnumbered}\n", "| a |\n|--|\n| 1 |\n\nplain text {width=3cm}\n",
                     "| a |\n|--|\n| 1 |\n\n\n{width=3cm}\n"):
            self.assertEqual(normalise(text).text, text)

    def test_the_carrier_goes_before_the_cell_s_own_tag_and_a_table_without_one_is_untouched(self):
        out = normalise("| &c& a | b |\n|--|--|\n| 1 | 2 |\n{valign=m}\n").text
        self.assertEqual(out.splitlines()[0], "| <pt v=m> <pc hc> a | b |")
        self.assertEqual(normalise("| a | b |\n|--|--|\n| 1 | 2 |\n").text, "| a | b |\n|--|--|\n| 1 | 2 |\n")

    def test_a_note_names_the_line_of_the_attribute_line(self):
        result = normalise("text\n\n| a | b |\n|--|--|\n| 1 | 2 |\n\n{bogus=1}\n")
        self.assertEqual([note.line for note in result.notes], [7])


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Sizes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def build(self, body: str, to: str = "tex", options: str = "") -> tuple[subprocess.CompletedProcess, str]:
        front = f"pdfmd-options: {{{options}}}\n" if options else ""
        (self.root / "d.md").write_text(f"---\ntitle: T\n{front}---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(self.root / "cache")})
        return done, (out.read_text(encoding="utf-8") if out.exists() else "")

    @unittest.skipUnless(TABULARRAY, "needs LaTeX's tabularray")
    def test_latex_gets_widths_heights_and_the_tiers(self):
        done, tex = self.build(SIZED)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("colspec={@{}Q[l,wd=3cm]X[1,l]Q[r,wd=0.1500\\linewidth]@{}}", tex)
        self.assertIn("width=\\linewidth", tex)
        self.assertIn("row{2}={ht=1.8cm}", tex)
        self.assertIn("cell{2}{2}={}{halign=l,valign=m}", tex)          # the column's alignment words, the table's valign
        self.assertIn("\\begin{longtblr}[caption={Sized},label={tbl:sized}]", tex)
        self.assertNotIn("<pt", tex)
        self.assertNotIn("{widths=", tex)

    @unittest.skipUnless(TABULARRAY, "needs LaTeX's tabularray")
    def test_a_table_width_alone_and_a_height_alone(self):
        done, tex = self.build("| a | b |\n|--|--|\n| 1 | 2 |\n\n{width=80% height=1cm}\n")
        self.assertIn("width=0.8000\\linewidth", tex)
        self.assertIn("row{1}={ht=1cm}", tex)
        self.assertIn("row{2}={ht=1cm}", tex)

    def test_html_gets_percent_widths_vertical_align_and_heights(self):
        done, html = self.build("| a | b | c |\n|:--|:--|--:|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n\n{widths=\"20% 60% *\" row2.height=1cm valign=bottom}\n", "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('<col style="width: 20%" />', html)
        self.assertIn('<col style="width: 60%" />', html)
        self.assertIn("vertical-align: bottom;", html)
        self.assertIn("height: 1cm;", html)
        self.assertNotIn("<pt", html)

    def test_markdown_gets_the_attribute_line_back_and_it_reads_again(self):
        done, md = self.build("| a | b |\n|:--|:--|\n| 1 | 2 |\n\n{widths=\"2cm *\" row2.height=1cm col2.align=r valign=m}\n", "commonmark_x")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        line = [text for text in md.splitlines() if text.startswith("{")][0]
        self.assertEqual(line, "{col1.width=2cm col2.width=* row2.height=1cm col2.align=r valign=m}")
        again = normalise(md)
        self.assertEqual(again.notes, [])
        self.assertIn("<pt", again.text)

    @unittest.skipUnless(TABULARRAY, "needs LaTeX's tabularray")
    def test_the_options_are_the_lowest_tier(self):
        done, tex = self.build("| a | b |\n|:--|--|\n| x | y |\n", options="table-valign: middle, table-align: right")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("cell{2}{1}={}{valign=m}", tex)                    # the separator row's `:--` beats the option
        self.assertIn("cell{2}{2}={}{halign=r,valign=m}", tex)
        done, tex = self.build("| a | b |\n|:--|--|\n| x | y |\n\n{valign=top align=c}\n", options="table-valign: middle, table-align: right")
        self.assertIn("cell{2}{1}={}{valign=h}", tex)                    # the table's own words beat the option
        self.assertIn("cell{2}{2}={}{halign=c,valign=h}", tex)

    def test_a_word_that_is_not_a_choice_stops_the_build(self):
        for option in ("table-align: sideways", "table-valign: up"):
            done, _ = self.build("| a |\n|--|\n| x |\n", options=option)
            self.assertNotEqual(done.returncode, 0, option)
            self.assertIn(option.split(":")[0], done.stdout + done.stderr)

    def test_an_attribute_line_problem_is_a_warning_and_the_build_goes_on(self):
        done, _ = self.build("| a | b |\n|--|--|\n| 1 | 2 |\n\n{col9.width=2cm}\n", "html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("WARN  cell-tags", done.stdout)
        self.assertIn("col9.width", done.stdout)


if __name__ == "__main__":
    unittest.main()

"""v3.32.9: the rules of priority (pdfmd_ranking, entry 3eu): what a `priority:` value and a file-name suffix mean, the ladder of
classes and its customisation, and the choice among several documents. Pure code: nothing here runs pdfmd."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfmd_ranking import Candidate, MISSING, Ranking, RankingError, choose, compare  # noqa: E402

DEFAULT = Ranking.from_layers()


def rank(value, ranking=DEFAULT):
    found = ranking.read(value)
    assert found.kind == "rank", (value, found)
    return found.rank


def higher(first, second, ranking=DEFAULT):
    return compare(rank(first, ranking), rank(second, ranking)) > 0


def pick(files, ranking=DEFAULT, by=None):
    """files: {name: (value, mtime)} or {name: value}; the Choice."""
    candidates = []
    for index, (name, entry) in enumerate(files.items()):
        value, mtime = entry if isinstance(entry, tuple) else (entry, index + 1)
        candidates.append(Candidate(Path(name), value, "priority", mtime * 10**9))
    return choose(candidates, ranking, by)


class Reading(unittest.TestCase):
    def test_the_ladder_from_never_to_final(self):
        for low, high in [("draft", None), (None, "new"), ("new", 1), (1, 2), (2, 10), (10, "final")]:
            low_rank = DEFAULT.unset if low is None else rank(low)
            high_rank = DEFAULT.unset if high is None else rank(high)
            self.assertGreater(compare(high_rank, low_rank), 0, (low, high))

    def test_zero_is_draft_and_negative_is_never(self):
        self.assertEqual(compare(rank(0), rank("draft")), 0)
        self.assertEqual(rank(0).cls, "draft")
        self.assertEqual(compare(rank("0.0"), rank("draft")), 0)
        self.assertEqual(DEFAULT.read(-1).kind, "excluded")
        self.assertEqual(DEFAULT.read("-0.5").kind, "excluded")

    def test_nothing_none_null_nil_nill_and_blank_all_mean_unset(self):
        for value in (None, "", "  ", "none", "null", "Nil", "NILL", "~"):
            self.assertEqual(DEFAULT.read(value).rank, DEFAULT.unset, repr(value))

    def test_never_and_its_synonyms(self):
        for value in ("never", "Ignore", "skip", "EXCLUDE!", -3):
            self.assertEqual(DEFAULT.read(value).kind, "excluded", value)

    def test_degrees_of_lastness(self):
        order = ["final", "final final", "FINAL FINAL FINAL!!!", "final67", "final100"]
        for low, high in zip(order, order[1:]):
            self.assertTrue(higher(high, low), (low, high))
        self.assertEqual(compare(rank("final"), rank("LAST")), 0)
        self.assertEqual(compare(rank("finalfinal"), rank("final final")), 0)
        self.assertEqual(compare(rank("final2"), rank("final final")), 0)
        self.assertEqual(rank("FINAL FINAL!!!").label, "final x2")

    def test_the_word_final_beats_every_number_and_every_other_class(self):
        for value in (1, 1000, "v9", "rewritten", "draft"):
            self.assertTrue(higher("final", value), value)

    def test_version_numbers_in_words(self):
        self.assertTrue(higher("v3", "v2"))
        self.assertTrue(higher("rev10", "rev9"))
        self.assertTrue(higher("version 2", "version 1"))

    def test_what_is_not_a_priority_is_invalid_with_a_reason(self):
        for value in ("banana", True, False, "nan", float("inf")):
            self.assertEqual(DEFAULT.read(value).kind, "invalid", value)
        self.assertTrue(DEFAULT.read("banana").why)

    def test_floats_and_numeric_strings(self):
        self.assertTrue(higher(0.8, 0.5))
        self.assertTrue(higher("2", 1.5))
        self.assertEqual(compare(rank("2"), rank(2)), 0)


class Names(unittest.TestCase):
    def parts(self, stem):
        return DEFAULT.name_parts(stem)

    def test_a_suffix_of_known_words_names_a_version_of_the_base(self):
        for stem, suffix in [("report.final", "final"), ("report_draft", "draft"), ("report rewritten", "rewritten"),
                             ("Report-FINAL", "final"), ("report_v3", "v3"), ("report.final.final2", "final final2"),
                             ("report_final_draft", "final draft")]:
            found = self.parts(stem)
            self.assertEqual((found.key, found.suffix), ("report", suffix), stem)

    def test_a_bare_name_and_names_that_only_look_alike_have_no_suffix(self):
        for stem in ("report", "lab2", "report_summary", "final", "draft_notes"):
            self.assertIsNone(self.parts(stem).suffix, stem)
        self.assertNotEqual(self.parts("lab2").key, self.parts("lab").key)

    def test_the_base_is_compared_without_case_or_separators(self):
        self.assertEqual(self.parts("My Report_final").key, self.parts("my-report").key)

    def test_a_name_that_is_a_never_word_is_excluded_not_ranked(self):
        self.assertEqual(self.parts("report_ignore").value.kind, "excluded")


class Customising(unittest.TestCase):
    def fruit(self, **extra):
        return Ranking.from_layers([("test", {
            "ladder": ["never", "draft", "unset", "revised", "numbers", "fruit", "final"],
            "classes": {"fruit": ["cherry", "banana"]}, **extra})])

    def test_banana_beats_cherry_and_fruit_beats_numbers_but_not_final(self):
        ranking = self.fruit()
        self.assertTrue(higher("banana", "cherry", ranking))
        self.assertTrue(higher("cherry", 999, ranking))
        self.assertTrue(higher("final", "banana", ranking))
        self.assertTrue(higher("BANANA!", "cherry", ranking))

    def test_a_nested_list_is_one_level(self):
        ranking = Ranking.from_layers([("t", {"ladder": ["never", "draft", "unset", "revised", "numbers", "fruit", "final"],
                                              "classes": {"fruit": ["apple", ["banana", "cherry"]]}})])
        self.assertTrue(higher("banana", "apple", ranking))
        self.assertEqual(compare(rank("banana", ranking), rank("cherry", ranking)), 0)

    def test_ordered_false_puts_every_word_on_one_level(self):
        ranking = Ranking.from_layers([("t", {"classes": {"fruit": {"words": ["apple", "pear"], "ordered": False, "above": "numbers"}}})])
        self.assertEqual(compare(rank("apple", ranking), rank("pear", ranking)), 0)

    def test_above_and_below_place_a_class_without_restating_the_ladder(self):
        ranking = Ranking.from_layers([("t", {"classes": {"fruit": {"words": ["cherry", "banana"], "above": "numbers"}}})])
        self.assertTrue(higher("cherry", 5, ranking))
        self.assertTrue(higher("final", "banana", ranking))
        below = Ranking.from_layers([("t", {"classes": {"veg": {"words": ["kale"], "below": "unset"}}})])
        self.assertLess(rank("kale", below).level, below.level["unset"])
        self.assertGreater(rank("kale", below).level, below.level["draft"])

    def test_two_classes_with_the_same_place_share_a_level_and_do_not_beat_each_other(self):
        ranking = Ranking.from_layers([("t", {"classes": {"fruit": {"words": ["apple"], "above": "numbers"},
                                                           "veg": {"words": ["kale"], "above": "numbers"}}})])
        self.assertEqual(compare(rank("apple", ranking), rank("kale", ranking)), 0)

    def test_a_nearer_layer_replaces_a_class_by_name_and_the_farther_ladder_stays(self):
        near = ("near", {"classes": {"final": {"words": ["done"], "degrees": True}}})
        far = ("far", {"classes": {"fruit": {"words": ["banana"], "above": "numbers"}}})
        ranking = Ranking.from_layers([near, far])
        self.assertTrue(higher("done", "banana", ranking))
        self.assertEqual(ranking.read("final").kind, "invalid")           # the class was replaced: its old words are gone

    def test_a_nearer_ladder_replaces_a_farther_one(self):
        flipped = Ranking.from_layers([("near", {"ladder": ["never", "final", "draft", "unset", "revised", "numbers"]})])
        self.assertTrue(higher(1, "final", flipped))

    def test_names_off_is_read_though_yaml_calls_it_false(self):
        self.assertEqual(Ranking.from_layers([("t", {"names": False})]).names, "off")
        self.assertEqual(Ranking.from_layers([("t", {"names": "Folder"})]).names, "folder")

    def test_by_as_words_separated_by_commas(self):
        self.assertEqual(Ranking.from_layers([("t", {"by": "priority, oldest"})]).by, ("priority", "oldest"))

    def test_settings_names_and_by(self):
        ranking = Ranking.from_layers([("t", {"names": "folder", "by": ["priority"]})])
        self.assertEqual((ranking.names, ranking.by), ("folder", ("priority",)))
        self.assertEqual((DEFAULT.names, DEFAULT.by), ("family", ("priority", "newest")))

    def test_yaml_values_that_are_not_text_are_put_back_or_refused(self):
        ranking = Ranking.from_layers([("t", {"classes": {"unset": [None, "nada"]}})])        # YAML read `null` as None
        self.assertEqual(ranking.read("null").rank, ranking.unset)
        with self.assertRaisesRegex(RankingError, "boolean"):
            Ranking.from_layers([("t", {"classes": {"x": {"words": [True], "above": "numbers"}}})])

    def test_mistakes_are_errors_that_name_the_layer(self):
        bad = [
            ({"names": "everywhere"}, "names"),
            ({"by": ["luck"]}, "luck"),
            ({"ladder": ["never", "nonsense", "unset", "numbers"]}, "nonsense"),
            ({"ladder": ["never", "never", "unset", "numbers"]}, "twice"),
            ({"ladder": ["never", "draft"]}, "unset"),
            ({"classes": {"numbers": ["x"]}}, "reserved"),
            ({"classes": {"fruit": {"words": ["x"], "above": "numbers", "below": "unset"}}}, "not both"),
            ({"classes": {"fruit": {"words": ["x"], "above": "nowhere"}}}, "nowhere"),
            ({"classes": {"fruit": {"words": ["final"], "above": "numbers"}}}, "two classes"),
            ({"classes": {"fruit": {"wrods": ["x"]}}}, "wrods"),
            ({"classes": {"fruit": []}}, "list of words"),
        ]
        for mapping, word in bad:
            with self.assertRaises(RankingError, msg=str(mapping)) as caught:
                Ranking.from_layers([("my-layer", mapping)])
            self.assertIn(word, str(caught.exception))
        with self.assertRaisesRegex(RankingError, "my-layer"):
            Ranking.from_layers([("my-layer", {"names": "x"})])

    def test_a_class_nowhere_on_the_ladder_is_warned_about_and_its_words_ignored(self):
        ranking = Ranking.from_layers([("t", {"classes": {"fruit": ["banana"]}})])
        self.assertIn("fruit", " ".join(ranking.warnings))
        self.assertEqual(ranking.read("banana").kind, "invalid")

    def test_an_unknown_key_is_a_warning_not_an_error(self):
        ranking = Ranking.from_layers([("t", {"colour": "red"})])
        self.assertIn("colour", " ".join(ranking.warnings))


class Choosing(unittest.TestCase):
    def test_the_final_version_of_a_family_wins_and_the_rest_say_why(self):
        choice = pick({"report.md": MISSING, "report.final.md": MISSING, "report_draft.md": MISSING})
        self.assertEqual(choice.winner, Path("report.final.md"))
        self.assertEqual(dict(choice.skipped), {Path("report.md"): "name: bare name", Path("report_draft.md"): "name: draft"})
        self.assertEqual(choice.warnings, [])

    def test_a_draft_loses_to_its_bare_name_and_a_rewrite_beats_it(self):
        self.assertEqual(pick({"report_draft.md": MISSING, "report.md": MISSING}).winner, Path("report.md"))
        self.assertEqual(pick({"report.md": MISSING, "report.rewritten.md": MISSING}).winner, Path("report.rewritten.md"))
        self.assertEqual(pick({"report.md": MISSING, "report.rewrite.md": MISSING, "report.final.md": MISSING}).winner,
                         Path("report.final.md"))

    def test_a_degree_of_lastness_in_the_name(self):
        files = {"r.final.md": MISSING, "r.final.final.md": MISSING, "r.final3.md": MISSING, "r.FINAL67.md": MISSING}
        self.assertEqual(pick(files).winner, Path("r.FINAL67.md"))

    def test_a_name_with_no_bare_sibling_has_no_effect(self):
        choice = pick({"report_draft.md": (MISSING, 5), "other.md": (MISSING, 1)})
        self.assertEqual(choice.winner, Path("report_draft.md"))             # equal priority: the newest
        self.assertEqual(len(choice.warnings), 1)

    def test_numbers_and_words_rank_documents(self):
        self.assertEqual(pick({"a.md": 1, "b.md": 3, "c.md": 2}).winner, Path("b.md"))
        self.assertEqual(pick({"a.md": "draft", "b.md": MISSING}).winner, Path("b.md"))
        self.assertEqual(pick({"a.md": "draft"}).winner, Path("a.md"))                     # a draft alone still builds
        self.assertEqual(pick({"a.md": 2, "b.md": "final", "c.md": 99}).winner, Path("b.md"))
        self.assertEqual(pick({"a.md": "final", "b.md": "FINAL FINAL"}).winner, Path("b.md"))

    def test_never_leaves_the_list_and_says_so(self):
        choice = pick({"a.md": "never", "b.md": MISSING})
        self.assertEqual((choice.winner, choice.skipped), (Path("b.md"), [(Path("a.md"), "priority: never")]))
        self.assertIn("never", pick({"a.md": "never", "b.md": "ignore"}).error)

    def test_an_explicit_priority_in_a_family_switches_the_names_off(self):
        # report.final is not consulted: report says priority 2, report.final says nothing
        choice = pick({"report.md": 2, "report.final.md": MISSING})
        self.assertEqual(choice.winner, Path("report.md"))
        self.assertEqual(pick({"report.md": "draft", "report.final.md": MISSING}).winner, Path("report.final.md"))

    def test_a_name_never_beats_an_unrelated_document_by_default(self):
        choice = pick({"report.md": (MISSING, 1), "report.final.md": (MISSING, 2), "appendix.md": (MISSING, 9)})
        self.assertEqual(choice.winner, Path("appendix.md"))                 # a tie of two families: the newest, with a warning
        self.assertEqual(len(choice.warnings), 1)

    def test_names_folder_lets_a_final_name_take_over_everything(self):
        ranking = Ranking.from_layers([("t", {"names": "folder"})])
        files = {"report.final.md": (MISSING, 1), "appendix.md": (MISSING, 9)}
        self.assertEqual(pick(files, ranking).winner, Path("report.final.md"))
        self.assertEqual(pick(files, Ranking.from_layers([("t", {"names": "off"})])).winner, Path("appendix.md"))

    def test_names_off_ignores_families(self):
        ranking = Ranking.from_layers([("t", {"names": "off"})])
        self.assertEqual(pick({"report.md": (MISSING, 5), "report.final.md": (MISSING, 1)}, ranking).winner, Path("report.md"))

    def test_equal_priority_builds_the_newest_with_a_warning_naming_everything(self):
        choice = pick({"a.md": (2, 1), "b.md": (2, 3), "c.md": (2, 2)})
        self.assertEqual(choice.winner, Path("b.md"))
        self.assertEqual(choice.settled_by, "newest")
        [warning] = choice.warnings
        for text in ("3 Markdown files tie", "a.md, b.md, c.md", "using b.md", "newest"):
            self.assertIn(text, warning)

    def test_strict_mode_makes_a_tie_an_error_that_says_what_raised_each(self):
        ranking = Ranking.from_layers([("t", {"by": ["priority"]})])
        choice = pick({"a.md": 2, "b.md": 2}, ranking)
        self.assertIsNone(choice.winner)
        for text in ("tie for first place", "a.md: priority: 2", "b.md: priority: 2"):
            self.assertIn(text, choice.error)
        self.assertIn("no priority set", pick({"a.md": MISSING, "b.md": MISSING}, ranking).error)

    def test_the_same_modification_time_is_an_error_even_when_the_newest_decides(self):
        choice = pick({"a.md": (2, 5), "b.md": (2, 5)})
        self.assertIsNone(choice.winner)
        self.assertIn("same moment", choice.error)

    def test_oldest_and_name_criteria(self):
        self.assertEqual(pick({"a.md": (MISSING, 1), "b.md": (MISSING, 2)}, by=["priority", "oldest"]).winner, Path("a.md"))
        self.assertEqual(pick({"v2.md": (MISSING, 5), "v10.md": (MISSING, 5)}, by=["priority", "name"]).winner, Path("v10.md"))
        self.assertEqual(pick({"a.md": (MISSING, 5), "b.md": (MISSING, 5)}, by=["priority", "newest", "name"]).winner, Path("b.md"))

    def test_a_chain_without_priority_looks_at_time_alone_but_never_still_hides(self):
        files = {"a.md": (9, 1), "b.md": ("draft", 3), "c.md": ("never", 5)}
        choice = pick(files, by=["newest"])
        self.assertEqual(choice.winner, Path("b.md"))
        self.assertEqual(choice.warnings, [])

    def test_an_invalid_value_warns_and_counts_as_unset(self):
        choice = pick({"a.md": "banana", "b.md": 1})
        self.assertEqual(choice.winner, Path("b.md"))
        self.assertIn("banana", choice.warnings[0])

    def test_custom_fruit_ranks_documents(self):
        ranking = Ranking.from_layers([("t", {"classes": {"fruit": {"words": ["cherry", "banana"], "above": "numbers"}}})])
        self.assertEqual(pick({"a.md": 7, "b.md": "cherry", "c.md": "banana", "d.md": "final"}, ranking).winner, Path("d.md"))
        self.assertEqual(pick({"a.md": 7, "b.md": "cherry", "c.md": "banana"}, ranking).winner, Path("c.md"))

    def test_the_family_tie_inside_names_follows_by(self):
        choice = pick({"r.md": (MISSING, 1), "r.rewrite.md": (MISSING, 2), "r.revised.md": (MISSING, 3)})
        self.assertEqual(choice.winner, Path("r.revised.md"))
        self.assertTrue(choice.warnings)

    def test_one_candidate_is_the_winner_without_a_word(self):
        choice = pick({"a.md": MISSING})
        self.assertEqual((choice.winner, choice.skipped, choice.warnings), (Path("a.md"), [], []))


if __name__ == "__main__":
    unittest.main()

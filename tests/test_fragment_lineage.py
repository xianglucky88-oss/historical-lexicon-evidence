import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from historical_lexicon_evidence import process
from historical_lexicon_evidence.fragment_lineage import fragment_ref, resolve_fragments

ROOT = Path(__file__).resolve().parent.parent


def lineage(citations):
    return process("citation-lineage", {"records": [{"id": "x", "citations": citations}]})[0]


def dating(record):
    return process("earliest-sense-dates", {"records": [record]})[0]


def review(record):
    return process("sense-review", {"records": [record]})[0]


def fragment(name, relation, copied_from=None, **extra):
    item = {"fragment": name, "relation": relation}
    if copied_from is not None:
        item["copied_from"] = copied_from
    item.update(extra)
    return item


NEW = [{"editor": "a", "version": "v3", "sense": "new"},
       {"editor": "b", "version": "v3", "sense": "new"}]
OLD = [{"editor": "a", "version": "v3", "sense": "old"},
       {"editor": "b", "version": "v3", "sense": "old"}]


class FragmentLineageTests(unittest.TestCase):
    def test_one_quotation_shows_two_starting_editions(self):
        citations = [
            {"citation": "first", "edition": "初版", "fragments": [fragment("old", "new")]},
            {"citation": "revised", "edition": "修订本", "fragments": [
                fragment("old", "verbatim", "first/old"),
                fragment("added", "new"),
            ]},
        ]
        detail = lineage(citations)["citations"]
        self.assertEqual(detail["revised"]["fragments"]["old"]["starting_edition"], "初版")
        self.assertEqual(detail["revised"]["fragments"]["old"]["path"], ["revised/old", "first/old"])
        self.assertEqual(detail["revised"]["fragments"]["added"]["starting_edition"], "修订本")
        self.assertEqual(detail["revised"]["fragments"]["added"]["path"], ["revised/added"])
        # The citation holds wording from two editions, so it claims neither.
        self.assertIsNone(detail["revised"]["origin"])

    def test_anthology_keeps_paths_but_adds_no_case(self):
        citations = [
            {"citation": "first", "edition": "初版", "fragments": [fragment("old", "new")]},
            {"citation": "revised", "edition": "修订本", "fragments": [
                fragment("old", "verbatim", "first/old"),
                fragment("added", "new"),
            ]},
            {"citation": "anth1", "edition": "选本甲", "reprinted_from": "revised", "fragments": [
                fragment("old", "verbatim", "revised/old"),
                fragment("added", "verbatim", "revised/added"),
            ]},
            {"citation": "anth2", "edition": "选本乙", "reprinted_from": "revised", "fragments": [
                fragment("old", "verbatim", "anth1/old"),
                fragment("added", "verbatim", "anth1/added"),
            ]},
        ]
        fact = lineage(citations)
        self.assertEqual(fact["independent_origins"], ["first/old", "revised/added"])
        # Every anthology still shows its own copying path.
        self.assertEqual(fact["citations"]["anth2"]["fragments"]["old"]["path"],
                         ["anth2/old", "anth1/old", "revised/old", "first/old"])
        self.assertEqual(fact["citations"]["anth2"]["fragments"]["added"]["path"],
                         ["anth2/added", "anth1/added", "revised/added"])

    def test_undated_chain_and_unconfirmed_relation_stay_pending(self):
        resolved = resolve_fragments({
            "a": {"edition": "e", "fragments": [fragment("f", "verbatim", "gone/f")]},
            "b": {"edition": "e", "fragments": [fragment("f", "unconfirmed")]},
        })
        self.assertEqual(resolved["a/f"]["status"], "pending")
        self.assertEqual(resolved["a/f"]["reason"], "origin_unlocated")
        self.assertEqual(resolved["a/f"]["path"], ["a/f", "gone/f"])
        self.assertEqual(resolved["b/f"]["status"], "pending")
        self.assertEqual(resolved["b/f"]["reason"], "relation_unconfirmed")

    def test_cycle_is_rejected(self):
        citations = [
            {"citation": "a", "edition": "e", "fragments": [fragment("f", "verbatim", "b/f")]},
            {"citation": "b", "edition": "e", "fragments": [fragment("f", "verbatim", "a/f")]},
        ]
        with self.assertRaisesRegex(ValueError, "cyclic"):
            lineage(citations)

    def test_new_fragment_requires_edition(self):
        with self.assertRaisesRegex(ValueError, "edition"):
            lineage([{"citation": "a", "fragments": [fragment("f", "new")]}])

    def test_relation_shape_is_validated(self):
        with self.assertRaisesRegex(ValueError, "copied_from"):
            lineage([{"citation": "a", "edition": "e", "fragments": [fragment("f", "verbatim")]}])
        with self.assertRaisesRegex(ValueError, "copied_from"):
            lineage([{"citation": "a", "edition": "e", "fragments": [fragment("f", "new", "b/f")]}])
        with self.assertRaisesRegex(ValueError, "citation/fragment"):
            lineage([{"citation": "a", "edition": "e", "fragments": [fragment("f", "verbatim", "nope")]}])
        with self.assertRaisesRegex(ValueError, "unexpected relation"):
            lineage([{"citation": "a", "edition": "e", "fragments": [fragment("f", "similar")]}])

    def test_duplicate_fragment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate fragment"):
            lineage([{"citation": "a", "edition": "e",
                      "fragments": [fragment("f", "new"), fragment("f", "new")]}])


class FragmentDatingTests(unittest.TestCase):
    def base(self, first_votes, added_votes, first_dates, added_dates):
        return {
            "id": "record",
            "definition_version": "v3",
            "sense": "new",
            "citations": [
                {"citation": "first", "edition": "初版",
                 "fragments": [fragment("old", "new", votes=first_votes, dates=first_dates)]},
                {"citation": "revised", "edition": "修订本",
                 "fragments": [
                     fragment("old", "verbatim", "first/old", votes=OLD,
                              dates=[{"kind": "edition", "year_min": 1800, "year_max": 1800}]),
                     fragment("added", "new", votes=added_votes, dates=added_dates),
                 ]},
            ],
        }

    def test_added_wording_ignores_the_first_edition_date(self):
        fact = dating(self.base(
            OLD, NEW,
            [{"kind": "written", "year_min": 1750, "year_max": 1750}],
            [{"kind": "written", "year_min": 1798, "year_max": 1799},
             {"kind": "edition", "year_min": 1800, "year_max": 1800}],
        ))
        first = fact["citations"]["first"]["fragments"]["old"]
        self.assertEqual((first["status"], first["reason"]), ("pending", "old_sense"))
        added = fact["citations"]["revised"]["fragments"]["added"]
        self.assertEqual(added["status"], "dated")
        self.assertEqual(added["adopted"], "written")
        self.assertEqual(added["range"], [1798, 1799])
        self.assertEqual(fact["earliest_range"], [1798, 1799])
        self.assertEqual(fact["earliest_candidates"], ["revised/added"])

    def test_edition_date_is_reported_but_never_adopted(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [{"citation": "a", "edition": "刻本",
                           "fragments": [fragment("f", "new", votes=NEW, dates=[
                               {"kind": "edition", "year_min": 1700, "year_max": 1700}])]}],
        })
        detail = fact["citations"]["a"]["fragments"]["f"]
        self.assertEqual(detail["status"], "undated")
        self.assertEqual(detail["reason"], "edition_only")
        self.assertEqual(detail["adopted"], None)
        self.assertEqual(fact["earliest_range"], None)

    def test_first_publication_is_used_when_no_writing_evidence(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [{"citation": "a", "edition": "刻本",
                           "fragments": [fragment("f", "new", votes=NEW, dates=[
                               {"kind": "published", "year_min": 1785, "year_max": 1785},
                               {"kind": "edition", "year_min": 1840, "year_max": 1840}])]}],
        })
        detail = fact["citations"]["a"]["fragments"]["f"]
        self.assertEqual(detail["adopted"], "published")
        self.assertEqual(detail["range"], [1785, 1785])
        self.assertEqual(detail["evidence"]["edition"], [1840, 1840])

    def test_old_sense_votes_and_stale_votes_are_pending(self):
        fact = dating(self.base(
            OLD, [{"editor": "a", "version": "v2", "sense": "new"}],
            [{"kind": "written", "year_min": 1750, "year_max": 1750}],
            [{"kind": "written", "year_min": 1700, "year_max": 1700}],
        ))
        self.assertEqual(fact["citations"]["first"]["fragments"]["old"]["reason"], "old_sense")
        added = fact["citations"]["revised"]["fragments"]["added"]
        self.assertEqual((added["status"], added["reason"]), ("pending", "stale_review"))
        self.assertEqual(fact["earliest_range"], None)
        self.assertEqual(fact["earliest_candidates"], [])

    def test_disputed_review_is_pending(self):
        fact = dating(self.base(
            OLD,
            [{"editor": "a", "version": "v3", "sense": "new"},
             {"editor": "b", "version": "v3", "sense": "old"}],
            [{"kind": "written", "year_min": 1750, "year_max": 1750}],
            [{"kind": "written", "year_min": 1700, "year_max": 1700}],
        ))
        added = fact["citations"]["revised"]["fragments"]["added"]
        self.assertEqual((added["status"], added["reason"]), ("pending", "review_unresolved"))

    def test_single_current_conclusion_is_accepted(self):
        fact = dating(self.base(
            OLD, [{"editor": "a", "version": "v3", "sense": "new"}],
            [{"kind": "written", "year_min": 1750, "year_max": 1750}],
            [{"kind": "written", "year_min": 1798, "year_max": 1798}],
        ))
        added = fact["citations"]["revised"]["fragments"]["added"]
        self.assertEqual(added["status"], "dated")
        self.assertEqual(added["range"], [1798, 1798])

    def test_date_for_other_wording_is_not_applied(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [{"citation": "a", "edition": "刻本",
                           "fragments": [fragment("f", "new", votes=NEW, dates=[
                               {"kind": "written", "year_min": 1700, "year_max": 1700,
                                "applies_to": "a/other"}])]}],
        })
        detail = fact["citations"]["a"]["fragments"]["f"]
        self.assertEqual((detail["status"], detail["reason"]), ("pending", "date_mismatch"))
        self.assertEqual(fact["earliest_range"], None)

    def test_date_naming_this_wording_is_applied(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [{"citation": "a", "edition": "刻本",
                           "fragments": [fragment("f", "new", votes=NEW, dates=[
                               {"kind": "written", "year_min": 1700, "year_max": 1700,
                                "applies_to": "a/f"}])]}],
        })
        self.assertEqual(fact["citations"]["a"]["fragments"]["f"]["range"], [1700, 1700])

    def test_boundary_touching_case_remains_a_candidate(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [
                {"citation": "a", "edition": "e", "fragments": [
                    fragment("f", "new", votes=NEW, dates=[
                        {"kind": "written", "year_min": 1798, "year_max": 1799}])]},
                {"citation": "b", "edition": "e", "fragments": [
                    fragment("f", "new", votes=NEW, dates=[
                        {"kind": "written", "year_min": 1799, "year_max": 1799}])]},
            ],
        })
        self.assertEqual(fact["earliest_range"], [1798, 1799])
        self.assertEqual(fact["earliest_candidates"], ["a/f", "b/f"])

    def test_anthology_date_does_not_compete_with_the_source(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [
                {"citation": "first", "edition": "初版", "fragments": [
                    fragment("f", "new", votes=NEW, dates=[
                        {"kind": "written", "year_min": 1798, "year_max": 1799}])]},
                {"citation": "anth", "edition": "选本", "reprinted_from": "first", "fragments": [
                    fragment("f", "verbatim", "first/f", dates=[
                        {"kind": "written", "year_min": 1700, "year_max": 1700}])]},
            ],
        })
        duplicate = fact["citations"]["anth"]["fragments"]["f"]
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(duplicate["path"], ["anth/f", "first/f"])
        self.assertEqual(fact["earliest_range"], [1798, 1799])
        self.assertEqual(fact["earliest_candidates"], ["first/f"])

    def test_review_filed_on_a_selection_still_decides_the_shared_case(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [
                {"citation": "first", "edition": "初版", "fragments": [
                    fragment("f", "new", dates=[
                        {"kind": "written", "year_min": 1798, "year_max": 1799}])]},
                {"citation": "anth", "edition": "选本", "fragments": [
                    fragment("f", "verbatim", "first/f", votes=NEW)]},
            ],
        })
        first = fact["citations"]["first"]["fragments"]["f"]
        self.assertEqual(first["status"], "dated")
        self.assertEqual(fact["earliest_candidates"], ["first/f"])

    def test_conflicting_votes_across_witnesses_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting vote"):
            dating({
                "id": "record", "definition_version": "v3", "sense": "new",
                "citations": [
                    {"citation": "first", "edition": "初版", "fragments": [
                        fragment("f", "new", votes=NEW)]},
                    {"citation": "anth", "edition": "选本", "fragments": [
                        fragment("f", "verbatim", "first/f",
                                 votes=[{"editor": "a", "version": "v3", "sense": "old"}])]},
                ],
            })

    def test_undated_fragment_is_reported_and_kept_out_of_the_range(self):
        fact = dating({
            "id": "record", "definition_version": "v3", "sense": "new",
            "citations": [
                {"citation": "dated", "edition": "初版", "fragments": [
                    fragment("f", "new", votes=NEW, dates=[
                        {"kind": "written", "year_min": 1798, "year_max": 1799}])]},
                {"citation": "printed", "edition": "重印", "fragments": [
                    fragment("f", "new", votes=NEW, dates=[
                        {"kind": "edition", "year_min": 1700, "year_max": 1700}])]},
            ],
        })
        printed = fact["citations"]["printed"]["fragments"]["f"]
        self.assertEqual((printed["status"], printed["reason"]), ("undated", "edition_only"))
        self.assertEqual(printed["adopted"], None)
        self.assertNotIn("range", printed)
        self.assertEqual(fact["earliest_candidates"], ["dated/f"])
        self.assertIn({"fragment": "printed/f", "reason": "edition_only"}, fact["undated"])
        self.assertNotIn({"fragment": "printed/f", "reason": "edition_only"}, fact["pending"])

    def test_every_citation_must_declare_fragments(self):
        with self.assertRaisesRegex(ValueError, "declare fragments"):
            dating({"id": "record", "definition_version": "v3", "sense": "new",
                    "citations": [
                        {"citation": "a", "edition": "e", "fragments": [fragment("f", "new", votes=NEW)]},
                        {"citation": "b", "dates": []}]})

    def test_citation_level_votes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "votes must be attached to fragments"):
            dating({"id": "record", "definition_version": "v3", "sense": "new",
                    "citations": [{"citation": "a", "edition": "e",
                                   "votes": NEW,
                                   "fragments": [fragment("f", "new")]}]})

    def test_split_record_requires_version_and_sense(self):
        for missing in ("definition_version", "sense"):
            record = {"id": "record", "definition_version": "v3", "sense": "new",
                      "citations": [{"citation": "a", "edition": "e", "fragments": [fragment("f", "new")]}]}
            del record[missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, missing):
                dating(record)

    def test_duplicate_date_kind_on_a_fragment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate written date evidence"):
            dating({"id": "record", "definition_version": "v3", "sense": "new",
                    "citations": [{"citation": "a", "edition": "e", "fragments": [
                        fragment("f", "new", votes=NEW, dates=[
                            {"kind": "written", "year_min": 1700, "year_max": 1700},
                            {"kind": "written", "year_min": 1701, "year_max": 1701}])]}]})

    def test_unknown_date_kind_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected kind"):
            dating({"id": "record", "definition_version": "v3", "sense": "new",
                    "citations": [{"citation": "a", "edition": "e", "fragments": [
                        fragment("f", "new", votes=NEW, dates=[
                            {"kind": "reprint", "year_min": 1700, "year_max": 1700}])]}]})


class FragmentReviewTests(unittest.TestCase):
    def test_review_is_reported_per_fragment(self):
        fact = review({
            "id": "record", "definition_version": "v3",
            "citations": [{"citation": "a", "fragments": [
                fragment("old", "new", votes=OLD),
                fragment("added", "new",
                         votes=[{"editor": "a", "version": "v3", "sense": "new"},
                                {"editor": "b", "version": "v2", "sense": "new"}]),
            ]}],
        })
        fragments = fact["citations"]["a"]["fragments"]
        self.assertEqual(fragments["old"]["status"], "agreed")
        self.assertEqual(fragments["added"]["needs_recheck"], ["b"])
        self.assertEqual(fragments["added"]["status"], "pending")

    def test_citation_without_fragments_keeps_old_shape(self):
        fact = review({"id": "record", "definition_version": "v2",
                       "citations": [{"citation": "a", "votes": [
                           {"editor": "a", "version": "v2", "sense": "x"},
                           {"editor": "b", "version": "v2", "sense": "x"}]}]})
        self.assertEqual(fact["citations"]["a"],
                         {"status": "agreed", "votes": {"a": "x", "b": "x"}, "needs_recheck": []})


class ExampleAndStorageTests(unittest.TestCase):
    def test_fragment_example_round_trips_through_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "fragments.sqlite"
            for pipeline in ("citation-lineage", "earliest-sense-dates", "sense-review"):
                cmd = [sys.executable, "-m", "historical_lexicon_evidence", pipeline,
                       str(ROOT / "examples" / f"{pipeline}.json"), "--sqlite", str(dest)]
                first = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
                second = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
                self.assertEqual(first.stdout, second.stdout)
                output = json.loads(first.stdout)
                self.assertEqual(len(output["facts"]), 2)
            with sqlite3.connect(dest) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone(), (3,))

    def test_fragment_ref_is_canonical(self):
        self.assertEqual(fragment_ref("revised", "added"), "revised/added")


if __name__ == "__main__":
    unittest.main()

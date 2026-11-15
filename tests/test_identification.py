from copy import deepcopy
from pathlib import Path
import json
import unittest

from margin_bounds import identification as ident
from margin_bounds.domain import validate


ROOT = Path(__file__).resolve().parents[1]
FIRST = {"release": "first", "unit": "persons", "universe": "eligible-households"}
SUPPLEMENT = {"release": "supplement", "unit": "persons", "universe": "eligible-households"}


def fixture():
    return json.loads((ROOT / "fixtures" / "data.json").read_text())


def query(population, outcome):
    return {"population": population, "outcome": outcome}


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        validate(self.data)

    def test_two_margins_narrow_the_intersection_without_independence(self):
        narrow = ident.identify(self.data, query(
            [{"axis": "age", "level": "young"}],
            [{"axis": "subsidy", "level": "yes"}]), FIRST)
        self.assertEqual(narrow["status"], "possible")
        # 独立相乘会得到 0.6*0.4=0.24 的点估计；区间必须覆盖更多可能。
        self.assertLessEqual(narrow["numerator"]["low"], 24)
        self.assertGreaterEqual(narrow["numerator"]["high"], 24)
        self.assertFalse(narrow["share"]["unique"])

    def test_added_cross_table_narrows_existing_question(self):
        before = ident.identify(self.data, query(
            [{"axis": "residence", "level": "rural"}],
            [{"axis": "subsidy", "level": "yes"}]), FIRST)
        after = ident.identify(self.data, query(
            [{"axis": "residence", "level": "rural"}],
            [{"axis": "subsidy", "level": "yes"}]), SUPPLEMENT)
        self.assertEqual(before["status"], "possible")
        self.assertEqual(after["status"], "unique")
        self.assertGreater(before["numerator"]["high"] - before["numerator"]["low"],
                           after["numerator"]["high"] - after["numerator"]["low"])

    def test_identified_ratio_for_low_income_subsidy(self):
        result = ident.identify(self.data, query(
            [{"axis": "income", "level": "low"}],
            [{"axis": "subsidy", "level": "yes"}]), FIRST)
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["numerator"]["low"], 30)
        self.assertEqual(result["denominator"]["low"], 50)
        self.assertAlmostEqual(result["share"]["low"], 0.6)

    def test_rural_low_income_subsidy_stays_interval_before_supplement(self):
        question = query(
            [{"axis": "residence", "level": "rural"}, {"axis": "income", "level": "low"}],
            [{"axis": "subsidy", "level": "yes"}])
        before = ident.identify(self.data, question, FIRST)
        after = ident.identify(self.data, question, SUPPLEMENT)
        self.assertEqual(before["status"], "possible")
        self.assertLess(before["numerator"]["low"], before["numerator"]["high"])
        self.assertEqual(after["status"], "possible")
        self.assertLess(after["numerator"]["high"] - after["numerator"]["low"],
                        before["numerator"]["high"] - before["numerator"]["low"])

    def test_evidence_lists_used_and_excluded_tables(self):
        result = ident.identify(self.data, query(
            [{"axis": "income", "level": "low"}],
            [{"axis": "subsidy", "level": "yes"}]), FIRST)
        used = {item["table"] for item in result["evidence"]["used"]}
        excluded = {item["table"] for item in result["evidence"]["excluded"]}
        self.assertIn("income_subsidy-persons", used)
        self.assertIn("income_residence-persons", excluded)
        self.assertIn("age_residence-weighted", excluded)
        self.assertIn("visit-count", excluded)
        for item in result["evidence"]["excluded"]:
            self.assertTrue(item["reasons"])

    def test_visits_table_never_joins_household_constraints(self):
        result = ident.identify(self.data, query(
            [], [{"axis": "subsidy", "level": "yes"}]), SUPPLEMENT)
        self.assertNotIn("visit-count", {item["table"] for item in result["evidence"]["used"]})

    def test_weighted_selection_uses_only_weighted_tables(self):
        result = ident.identify(self.data, query(
            [{"axis": "residence", "level": "rural"}],
            [{"axis": "subsidy", "level": "yes"}]), {"release": "supplement", "unit": "weighted"})
        units = {item["unit"] for item in result["evidence"]["used"]}
        self.assertEqual(units, {"weighted"})
        self.assertFalse(result["share"]["unique"])
        self.assertGreater(result["share"]["high"] - result["share"]["low"], 0)

    def test_weighted_tolerance_widens_interval(self):
        result = ident.identify(self.data, query(
            [{"axis": "residence", "level": "rural"}],
            [{"axis": "subsidy", "level": "yes"}]), {"release": "supplement", "unit": "weighted"})
        self.assertGreater(result["numerator"]["high"], result["numerator"]["low"])

    def test_missing_table_for_dimension_is_unsupported(self):
        data = deepcopy(self.data)
        data["releases"] = [release for release in data["releases"]
                            if "age" not in release["dimensions"]]
        tables = {release["table"] for release in data["releases"]}
        data["margins"] = [row for row in data["margins"] if row["table"] in tables]
        validate(data)
        result = ident.identify(data, query(
            [], [{"axis": "age", "level": "young"}]), FIRST)
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["numerator"])
        self.assertTrue(any("age" in note for note in result["notes"]))

    def test_unknown_axis_raises(self):
        with self.assertRaises(ValueError):
            ident.identify(self.data, query([], [{"axis": "nonsense", "level": "x"}]), FIRST)

    def test_duplicate_dimension_across_population_and_outcome_rejected(self):
        with self.assertRaises(ValueError):
            ident.identify(self.data, query(
                [{"axis": "income", "level": "low"}],
                [{"axis": "income", "level": "other"}]), FIRST)


class ZeroAndPeriodTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_impossible_zero_is_enforced(self):
        question = query(
            [{"axis": "age", "level": "young"}, {"axis": "residence", "level": "rural"},
             {"axis": "income", "level": "other"}],
            [{"axis": "subsidy", "level": "yes"}])
        result = ident.identify(self.data, question, SUPPLEMENT)
        self.assertEqual(result["numerator"]["low"], 0)
        self.assertEqual(result["numerator"]["high"], 0)
        rule = next(rule for rule in result["evidence"]["rules"]
                    if rule["rule"] == "young-rural-other-yes")
        self.assertTrue(rule["applied"])

    def test_zero_with_empty_semantics_does_not_force_zero(self):
        data = deepcopy(self.data)
        data["structural_zeros"][0]["zero"] = "empty"
        validate(data)
        question = query(
            [{"axis": "age", "level": "young"}, {"axis": "residence", "level": "rural"},
             {"axis": "income", "level": "other"}],
            [{"axis": "subsidy", "level": "yes"}])
        relaxed = ident.identify(data, question, SUPPLEMENT)
        strict = ident.identify(self.data, question, SUPPLEMENT)
        self.assertEqual(strict["numerator"]["high"], 0)
        self.assertGreater(relaxed["numerator"]["high"], 0)
        rule = next(rule for rule in relaxed["evidence"]["rules"]
                    if rule["rule"] == "young-rural-other-yes")
        self.assertFalse(rule["applied"])

    def test_unknown_zero_semantics_rejected(self):
        data = deepcopy(self.data)
        data["structural_zeros"][0]["zero"] = "maybe"
        with self.assertRaises(ValueError):
            validate(data)

    def test_different_aggregate_period_is_excluded(self):
        data = deepcopy(self.data)
        for release in data["releases"]:
            if release["table"] == "income_subsidy-persons":
                release["start"], release["stop"] = 31, 60
        result = ident.identify(data, query(
            [{"axis": "income", "level": "low"}],
            [{"axis": "subsidy", "level": "yes"}]), FIRST)
        excluded = {item["table"]: item["reasons"] for item in result["evidence"]["excluded"]}
        self.assertIn("income_subsidy-persons", excluded)
        self.assertIn("汇总期间", excluded["income_subsidy-persons"][0])
        # 失去这张表后 subsidy 不再被覆盖，而不是偷偷用另一期间的数据。
        self.assertEqual(result["status"], "unsupported")

    def test_annual_tables_do_not_mix_with_aggregate(self):
        data = deepcopy(self.data)
        data["releases"].append({"table": "annual-x", "release": "supplement", "unit": "persons",
                                 "start": 10, "stop": 12, "universe": "eligible-households",
                                 "counting": "distinct-household", "dimensions": ["age", "residence"],
                                 "tolerance": 0, "period": "annual"})
        for age in ["young", "older"]:
            for residence in ["urban", "rural"]:
                data["margins"].append({"cell": "annual-" + age + "-" + residence,
                                        "table": "annual-x",
                                        "coordinates": {"age": age, "residence": residence},
                                        "value": 20})
        validate(data)
        result = ident.identify(data, query(
            [{"axis": "residence", "level": "rural"}],
            [{"axis": "subsidy", "level": "yes"}]), SUPPLEMENT)
        excluded = {item["table"]: item["reasons"] for item in result["evidence"]["excluded"]}
        self.assertIn("annual-x", excluded)
        self.assertIn("期间口径", excluded["annual-x"][0])


class ConflictTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_inconsistent_margin_reports_pair_to_check(self):
        data = deepcopy(self.data)
        for margin in data["margins"]:
            if margin["cell"] == "residence_subsidy-persons-rural-yes":
                margin["value"] = 200
        result = ident.identify(data, query(
            [], [{"axis": "subsidy", "level": "yes"}]), SUPPLEMENT)
        self.assertEqual(result["status"], "conflict")
        self.assertIsNone(result["numerator"])
        pairs = {tuple(sorted(entry["tables"])) for entry in result["conflicts"]}
        self.assertIn(("age_residence-persons", "residence_subsidy-persons"), pairs)
        detail = next(entry for entry in result["conflicts"]
                      if "residence_subsidy-persons" in entry["tables"]
                      and "age_residence-persons" in entry["tables"])
        self.assertTrue(detail["details"][0]["sources"])
        self.assertIn("residence", detail["details"][0]["coordinates"])

    def test_conflict_notes_do_not_pick_a_side(self):
        data = deepcopy(self.data)
        for margin in data["margins"]:
            if margin["cell"] == "income_residence-persons-low-rural":
                margin["value"] = 5
        result = ident.identify(data, query(
            [{"axis": "income", "level": "low"}],
            [{"axis": "subsidy", "level": "yes"}]), SUPPLEMENT)
        self.assertEqual(result["status"], "conflict")
        joined = " ".join(result["notes"])
        self.assertIn("核对", joined)
        self.assertIsNone(result["share"])


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_supplement_shrinks_and_flags_which_question(self):
        questions = [
            {"label": "农村补贴比例",
             "population": [{"axis": "residence", "level": "rural"}],
             "outcome": [{"axis": "subsidy", "level": "yes"}]},
            {"label": "低收入补贴比例",
             "population": [{"axis": "income", "level": "low"}],
             "outcome": [{"axis": "subsidy", "level": "yes"}]},
        ]
        comparison = ident.compare(
            questions,
            {"data": self.data, "selection": FIRST},
            {"data": self.data, "selection": SUPPLEMENT})
        self.assertEqual(len(comparison["rows"]), 2)
        self.assertEqual(comparison["rows"][0]["change"], "范围缩小")
        self.assertEqual(comparison["rows"][1]["change"], "无变化")
        self.assertGreaterEqual(len(comparison["rows"][0]["current"]["tables"]),
                                len(comparison["rows"][0]["baseline"]["tables"]))

    def test_comparison_rejects_unknown_axis(self):
        with self.assertRaises(ValueError):
            ident.compare([{"population": [], "outcome": [{"axis": "x", "level": "y"}]}],
                          {"data": self.data, "selection": FIRST},
                          {"data": self.data, "selection": SUPPLEMENT})


class SelectionTests(unittest.TestCase):
    def test_first_round_never_uses_supplement_tables(self):
        data = fixture()
        result = ident.identify(data, query(
            [], [{"axis": "residence", "level": "rural"}]), FIRST)
        for item in result["evidence"]["used"]:
            self.assertEqual(item["release"], "first")

    def test_blank_selection_rejected(self):
        data = fixture()
        with self.assertRaises(ValueError):
            ident.identify(data, query([], [{"axis": "subsidy", "level": "yes"}]),
                           {"release": "later", "unit": "persons"})


class ValidationTests(unittest.TestCase):
    def test_non_integer_person_margin_rejected(self):
        data = fixture()
        data["margins"][0]["value"] = 20.5
        with self.assertRaises(ValueError):
            validate(data)

    def test_negative_tolerance_rejected(self):
        data = fixture()
        data["releases"][0]["tolerance"] = -1
        with self.assertRaises(ValueError):
            validate(data)

    def test_mapped_level_must_exist(self):
        data = fixture()
        data["releases"][0]["level_map"] = {"age": {"young": "unlisted"}}
        with self.assertRaises(ValueError):
            validate(data)


if __name__ == "__main__":
    unittest.main()

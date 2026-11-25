import unittest

from jiadian import agent, rules


def fridge():
    return "冰箱不制冷,2021年买的,新机价 3800,门封看起来有点松"


class TestDetect(unittest.TestCase):
    def test_fridge(self):
        f, hits = rules.detect(fridge())
        self.assertEqual(f["key"], "fridge")
        self.assertIn("不制冷", hits)

    def test_ac(self):
        f, _ = rules.detect("空调不制冷还漏水")
        self.assertEqual(f["key"], "ac")

    def test_unknown(self):
        f, hits = rules.detect("家里的东西坏了")
        self.assertIsNone(f)
        self.assertEqual(hits, [])

    def test_causes_selfcheck_first(self):
        f, hits = rules.detect(fridge())
        causes = rules.causes_for(f, hits)
        self.assertEqual(causes[0]["level"], "可自查")


class TestWarranty(unittest.TestCase):
    def test_buy_year(self):
        self.assertEqual(rules.purchase_year("2021年买的"), 2021)

    def test_last_year(self):
        self.assertEqual(rules.purchase_year("去年买的", 2026), 2025)

    def test_unknown(self):
        self.assertIsNone(rules.purchase_year("不记得了"))

    def test_in_warranty(self):
        w = rules.warranty(2025, 2026)
        self.assertTrue(w["items"][0]["active"])
        self.assertEqual(w["age"], 1)

    def test_expired_main_parts(self):
        w = rules.warranty(2019, 2026)
        self.assertFalse(w["items"][1]["active"])

    def test_compressor_still_active(self):
        w = rules.warranty(2018, 2026)
        self.assertTrue(w["items"][2]["active"])

    def test_no_year(self):
        self.assertIsNone(rules.warranty(None)["age"])


class TestEstimateAndDecision(unittest.TestCase):
    def test_new_price(self):
        self.assertEqual(rules.new_price("新机价 3800", None), 3800.0)

    def test_residual(self):
        self.assertEqual(rules.residual(3800, 2), round(3800 * 0.3025))

    def test_residual_floor(self):
        self.assertGreaterEqual(rules.residual(1000, 20), 50)

    def test_decision_repair(self):
        d = rules.decision({"low": 100, "high": 300}, 900, 3000)
        self.assertEqual(d["verdict"], "修")

    def test_decision_replace(self):
        d = rules.decision({"low": 500, "high": 1200}, 3000, 3000)
        self.assertEqual(d["verdict"], "倾向换新")

    def test_decision_over_residual(self):
        d = rules.decision({"low": 300, "high": 900}, 191, 3800)
        self.assertEqual(d["verdict"], "换新")

    def test_decision_no_price(self):
        self.assertEqual(rules.decision({"low": 1, "high": 2}, None, None)["verdict"], "先补新机价")


class TestTalkAndChecklist(unittest.TestCase):
    def test_talk_asks_fees(self):
        f, hits = rules.detect(fridge())
        talk = rules.talk_script(f, rules.causes_for(f, hits))
        self.assertIn("上门费", talk)
        self.assertIn("配件费", talk)

    def test_checklist(self):
        checks = rules.checklist(fridge())
        ok = [c["item"] for c in checks if c["ok"]]
        self.assertIn("故障现象", ok)
        self.assertIn("购机年份/发票", ok)

    def test_checklist_empty(self):
        checks = rules.checklist("")
        self.assertTrue(all(not c["ok"] for c in checks))


class TestAgent(unittest.TestCase):
    def test_offline_structure(self):
        r = agent.diagnose(fridge(), force_mock=True)
        self.assertEqual(r["mode"], "offline")
        for k in ("summary", "risks", "questions", "talk", "decision"):
            self.assertTrue(r[k])

    def test_verdict_expired(self):
        r = agent.diagnose(fridge(), force_mock=True)
        self.assertIn("换新", r["verdict"])

    def test_in_warranty_verdict(self):
        r = agent.diagnose("空调不制冷,2025年买的", force_mock=True)
        self.assertIn("保修", r["verdict"])

    def test_strip_money(self):
        self.assertNotIn("900", agent.strip_money("最多 900 元"))

    def test_gas_safety(self):
        r = agent.diagnose("燃气热水器打不着火,闻到燃气味", force_mock=True)
        self.assertTrue(any("燃气" in x for x in r["risks"]))

    def test_unknown_text(self):
        r = agent.diagnose("东西坏了", force_mock=True)
        self.assertTrue(r["notes"])
        self.assertTrue(r["causes"])


if __name__ == "__main__":
    unittest.main()


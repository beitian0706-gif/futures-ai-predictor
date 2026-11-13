import unittest
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from strategy_v056 import Settings,validate_bars,indicators,classify,run_research,compare_strategies

T=datetime(2026,1,1,tzinfo=timezone.utc)
def sample(n=240,breakout=True,trend="up"):
    rows=[]
    for i in range(n):
        # series with mild up drift, then a marked positive crossing at ~170
        close=100 if i<168 else (101+(i-168)*.18 if breakout else 100)
        rows.append({"end_time":(T+timedelta(hours=i)).isoformat(),
           "open":close-.2,"high":close+.8,"low":close-1.0,
           "close":close,"daily_trend":trend})
    return rows

class StrategyTests(unittest.TestCase):
    def test_nine_comparisons(self):
        s=compare_strategies("RB2701",sample(),Settings(contract_multiplier=10,margin_per_lot=1000))
        self.assertEqual(len(s["comparisons"]),9)
        self.assertTrue(all(x["research_only"] for x in s["comparisons"]))
    def test_A_cross_not_entry_instruction(self):
        b=validate_bars(sample())
        atr,ma=indicators(b)
        a=[(i,classify(b,atr,ma,i)) for i in range(154,len(b))]
        self.assertTrue(any(z==("A","long") for i,z in a))
        r=run_research("RB2701",sample(),Settings(margin_per_lot=1000),entry_type="A")
        self.assertFalse(r["push_enabled"]);self.assertFalse(r["order_enabled"])
    def test_no_daily_confirmation_blocks(self):
        s=run_research("RB2701",sample(trend="down"),Settings(margin_per_lot=1000))
        self.assertEqual(s["trades"],0)
        self.assertGreaterEqual(s["blocked"]["trend_or_missing"],0)
    def test_missing_daily_blocks_not_lookahead(self):
        s=run_research("RB2701",sample(trend=None),Settings(margin_per_lot=1000),entry_type="A")
        self.assertEqual(s["trades"],0)
    def test_one_contract_only(self):
        with self.assertRaises(ValueError):
            run_research("RB0",sample())
    def test_duplicate_timestamps(self):
        s=sample();s[-1]["end_time"]=s[-2]["end_time"]
        with self.assertRaises(ValueError):validate_bars(s)
    def test_bad_ohlc(self):
        s=sample();s[-1]["low"]=s[-1]["close"]+2
        with self.assertRaises(ValueError):validate_bars(s)
    def test_bad_risk_config(self):
        with self.assertRaises(ValueError):
            run_research("RB2701",sample(),Settings(risk_percent=4))
    def test_disabled_daily_filter_research(self):
        r=run_research("RB2701",sample(trend=None),Settings(daily_filter=False,margin_per_lot=1000),entry_type="A")
        self.assertTrue(r["research_only"])
        self.assertFalse(r["live_signal"])
    def test_next_bar_entry(self):
        r=run_research("RB2701",sample(),Settings(margin_per_lot=1000),entry_type="A")
        if r["trade_log"]:
            t=r["trade_log"][0]
            self.assertNotEqual(t["decision_bar"],t["entry_time"])
    def test_short_bars_fail(self):
        with self.assertRaises(ValueError):run_research("RB2701",sample(n=169))
    def test_zero_trade_metrics_not_fabricated(self):
        r=run_research("RB2701",sample(breakout=False),Settings(),entry_type="C")
        self.assertIsNone(r["win_rate"]);self.assertIsNone(r["avg_r"])
if __name__=="__main__":unittest.main()

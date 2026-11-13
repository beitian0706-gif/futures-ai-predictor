import unittest
from datetime import datetime, timedelta, timezone

from opportunity_engine import evaluate_opportunity, normalize_daily
from ma144_60m import Market60mError

TZ=timezone(timedelta(hours=8))
BASE=datetime(2026,11,1,0,0,tzinfo=TZ)

def make_bars(closes, start=BASE, step=timedelta(hours=1)):
    return [
        {"datetime":start+i*step,"open":float(p),"high":float(p)+1,
         "low":float(p)-1,"close":float(p),"volume":100}
        for i,p in enumerate(closes)
    ]

class OpportunityEngineTests(unittest.TestCase):
    def test_up_cross_candidate_not_alert(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*145+[100.5,100.6])
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2))
        self.assertEqual(r["status"],"candidate")
        self.assertEqual(r["historical_cross"],"up")
        self.assertEqual(r["daily_trend"],"long")
        self.assertFalse(r["entry_alert_enabled"])
        self.assertFalse(r["entry_conditions_met"])
    def test_down_cross_candidate(self):
        daily=make_bars([140-i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*145+[99.5,99.4])
        r=evaluate_opportunity("JM2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2))
        self.assertEqual(r["status"],"candidate")
        self.assertEqual(r["historical_cross"],"down")
    def test_conflict_stays_watch(self):
        daily=make_bars([140-i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*145+[100.5,100.6])
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2))
        self.assertEqual(r["status"],"watch")
    def test_unconfirmed_last_bar_ignored(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*146+[105])
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2))
        self.assertEqual(r["historical_cross"],"none")
        self.assertEqual(r["usable_hourly_bars"],146)
    def test_stale_blocks_candidate(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*145+[100.5,100.6])
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(days=5))
        self.assertEqual(r["status"],"watch")
    def test_insufficient(self):
        r=evaluate_opportunity("RB2701",[],[])
        self.assertEqual(r["status"],"watch")
    def test_reject_continuous(self):
        with self.assertRaises(Market60mError):
            evaluate_opportunity("RB0",[],[])
    def test_invalid_bar(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*145+[100.5,100.6])
        hourly[-5]["high"]=0
        with self.assertRaises(Market60mError):
            evaluate_opportunity("RB2701",daily,hourly)
    def test_pullback_strategy_independent_of_cross(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*144+[100.1,100.2,100.3])
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2))
        self.assertEqual(r["historical_cross"],"none")
        self.assertEqual(r["strategy"],"B-回踩确认")
        self.assertEqual(r["status"],"candidate")
    def test_structure_breakout_not_necessarily_cross(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*125+[100.2]*19+[100.3,100.6,100.7])
        for b in hourly:
            b["high"]=b["close"]+0.01
            b["low"]=b["close"]-0.01
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2))
        self.assertEqual(r["historical_cross"],"none")
        self.assertEqual(r["strategy"],"C-结构突破")
        self.assertEqual(r["status"],"candidate")
    def test_not_ready_even_if_flags_true(self):
        daily=make_bars([80+i for i in range(61)],step=timedelta(days=1))
        hourly=make_bars([100]*145+[100.5,100.6])
        r=evaluate_opportunity("RB2701",daily,hourly,
                now=hourly[-2]["datetime"]+timedelta(hours=2),
                main_contract_verified=True, closed_bar_verified=True,
                data_fresh_verified=True)
        self.assertFalse(r["entry_conditions_met"])
        self.assertEqual(r["status"],"candidate")

if __name__=="__main__":
    unittest.main()

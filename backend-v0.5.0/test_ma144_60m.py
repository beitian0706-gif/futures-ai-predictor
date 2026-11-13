import unittest
from datetime import datetime, timezone, timedelta
from ma144_60m import evaluate_bars, Market60mError
TZ=timezone(timedelta(hours=8))
BASE=datetime(2026,11,5,9,0,tzinfo=TZ)
def bars(closes):
    return [{"datetime":BASE+timedelta(hours=i), "close":float(c),
             "open":float(c), "high":float(c)+1, "low":float(c)-1, "volume":100}
            for i,c in enumerate(closes)]
class Tests(unittest.TestCase):
    def test_up(self):
        r=evaluate_bars("RB2701",bars([100]*145+[103,103]),now=BASE+timedelta(hours=200))
        self.assertEqual(r["signal"],"up")
        self.assertFalse(r["push_enabled"])
    def test_down(self):
        r=evaluate_bars("JM2701",bars([100]*145+[98,98]),now=BASE+timedelta(hours=200))
        self.assertEqual(r["signal"],"down")
    def test_unsafe_last_bar_ignored(self):
        r=evaluate_bars("RU2701",bars([100]*146+[110]),now=BASE+timedelta(hours=200))
        self.assertEqual(r["signal"],"none")
    def test_short_history(self):
        r=evaluate_bars("RB2701",bars([100]*145))
        self.assertEqual(r["status"],"insufficient_data")
    def test_continuous_contract_rejected(self):
        with self.assertRaises(Market60mError):
            evaluate_bars("RB0",bars([100]*150))
    def test_oversized_cross_filtered(self):
        r=evaluate_bars("RB2701",bars([100]*145+[110,110]),now=BASE+timedelta(hours=200))
        self.assertEqual(r["signal"],"filtered")
    def test_no_cross(self):
        r=evaluate_bars("RB2701",bars([100]*150),now=BASE+timedelta(hours=200))
        self.assertEqual(r["signal"],"none")
if __name__=="__main__":
    unittest.main()

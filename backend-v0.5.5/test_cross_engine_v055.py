import os
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from cross_engine_v055 import analyse_cross, save_research, read_status
T=datetime(2026,11,13,14,0,tzinfo=timezone.utc)

def bars(last=101,previous=99,**opt):
    prices=[100]*143+[previous,last]
    return [{"end_time":(T-timedelta(hours=144-i)).isoformat(),
             "close":float(p),"close_verified":opt.get("closed",False)}
            for i,p in enumerate(prices)]

class CrossResearchTests(unittest.TestCase):
    def check(self,bs,**kwargs):
        return analyse_cross("RB2701",bs,observed_at=T,**kwargs)
    def test_up_only_research(self):
        r=self.check(bars(101,99))
        self.assertEqual(r["research_cross"],"up")
        self.assertFalse(r["notification_allowed"])
        self.assertFalse(r["entry_signal"])
    def test_down_only_research(self):
        r=self.check(bars(99,101))
        self.assertEqual(r["research_cross"],"down")
        self.assertFalse(r["notification_sent"])
    def test_flat(self):
        r=self.check(bars(100,100))
        self.assertEqual(r["research_cross"],"none")
    def test_touch_from_below(self):
        r=self.check(bars(100,99))
        self.assertEqual(r["research_cross"],"up")
    def test_not_enough(self):
        self.assertIn("145",self.check(bars()[:144])["blockers"][0])
    def test_duplicate_bar_time(self):
        b=bars();b[-1]["end_time"]=b[-2]["end_time"]
        self.assertIn("重复",str(self.check(b)["blockers"]))
    def test_expired(self):
        r=analyse_cross("RB2701",bars(),observed_at=T+timedelta(minutes=10))
        self.assertTrue(any("一分钟" in x for x in r["blockers"]))
    def test_verified_inputs_still_fail_closed(self):
        r=self.check(bars(closed=True),main_contract_verified=True,
          exchange_calendar_verified=True,provider_close_verified=True,
          timestamp_semantics_verified=True)
        self.assertFalse(r["notification_allowed"])
        self.assertFalse(r["official_close_verified"])
    def test_reject_continuous(self):
        with self.assertRaises(ValueError):
            analyse_cross("RB0",bars(),observed_at=T)
    def test_dedupe(self):
        result=self.check(bars())
        with tempfile.TemporaryDirectory() as folder:
            path=os.path.join(folder,"signals.sqlite3")
            self.assertTrue(save_research(path,result,observed_at=T))
            self.assertFalse(save_research(path,result,observed_at=T))
            out=read_status(path)
            self.assertEqual(len(out["research_events"]),1)
            self.assertFalse(out["notification_enabled"])
    def test_no_db(self):
        with tempfile.TemporaryDirectory() as f:
            self.assertEqual(read_status(os.path.join(f,"none.db"))["research_events"],[])
if __name__=="__main__":unittest.main()

import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from monitor_v052 import (validate_watchlist, classify_observation, observation_id,
                          init_db,record_scan,record_error,read_latest,scan_once)
TZ=timezone(timedelta(hours=8))
NOW=datetime(2026,11,13,15,30,tzinfo=TZ)

def fake_signal(direction="up"):
    return {"source":"AKShare/Sina","latest_usable_timestamp":"2026-11-13T15:00:00+08:00",
            "raw_cross_direction":direction,
            "signal":direction,"last_close":3000,"ma144":2995,
            "cross_distance_pct":0.167}

class MonitorTests(unittest.TestCase):
    def test_watchlist_only_specific(self):
        self.assertEqual(validate_watchlist(["rb2701","RB2701","JM2701"]),["RB2701","JM2701"])
        for bad in (["RB0"],["RB888"],["RB9999"],["RB"],["RB2701",12],["bad"],"RB2701"):
            with self.assertRaises(ValueError):
                validate_watchlist(bad)
    def test_no_trade_or_push_even_when_fresh(self):
        r=classify_observation(fake_signal(),observed_at=NOW)
        self.assertEqual(r["status"],"historical_cross")
        self.assertFalse(r["notification_allowed"])
        self.assertFalse(r["closed_bar_verified"])
        self.assertFalse(r["main_contract_verified"])
    def test_old_observation_is_stale(self):
        r=classify_observation(fake_signal(),observed_at=NOW+timedelta(days=2))
        self.assertEqual(r["status"],"stale")
    def test_future_timestamp_is_invalid(self):
        r=classify_observation(fake_signal(),observed_at=NOW-timedelta(hours=1))
        self.assertEqual(r["status"],"future_timestamp")
    def test_dedupes_by_contract_bar_direction(self):
        with tempfile.TemporaryDirectory() as d:
            db=str(Path(d)/"events.sqlite3")
            c=init_db(db)
            try:
                a=record_scan(c,"RB2701",fake_signal(),observed_at=NOW)
                b=record_scan(c,"RB2701",fake_signal(),observed_at=NOW+timedelta(seconds=10))
                self.assertTrue(a["new_record"])
                self.assertFalse(b["new_record"])
                self.assertEqual(c.execute("SELECT COUNT(*) FROM observations").fetchone()[0],1)
                self.assertEqual(c.execute("SELECT COUNT(*) FROM scans").fetchone()[0],2)
            finally: c.close()
            self.assertEqual(len(read_latest(db)["observations"]),1)
    def test_filtered_cross_still_logged_as_research(self):
        with tempfile.TemporaryDirectory() as d:
            db=str(Path(d)/"a.db")
            c=init_db(db)
            s=fake_signal("down")
            s["signal"]="filtered"
            try:
                r=record_scan(c,"RB2701",s,observed_at=NOW)
                self.assertEqual(r["status"],"filtered")
                self.assertTrue(r["new_record"])
            finally:c.close()
    def test_no_cross_not_logged(self):
        with tempfile.TemporaryDirectory() as d:
            c=init_db(str(Path(d)/"a.db"))
            try:
                r=record_scan(c,"RB2701",fake_signal("none"),observed_at=NOW)
                self.assertFalse(r["new_record"])
                self.assertEqual(c.execute("SELECT COUNT(*) FROM observations").fetchone()[0],0)
            finally:c.close()
    def test_provider_error_is_separate(self):
        with tempfile.TemporaryDirectory() as d:
            c=init_db(str(Path(d)/"a.db"))
            try:
                record_error(c,"RB2701",RuntimeError("token=SECRET"),observed_at=NOW)
                row=c.execute("SELECT status,error FROM scans").fetchone()
                self.assertEqual(row,("provider_error","RuntimeError"))
            finally:c.close()
    def test_empty_db(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read_latest(str(Path(d)/"notexists.db"))["observations"],[])
    def test_id_stable(self):
        x=observation_id("RB2701","2026-11-13T15:00:00+08:00","up")
        self.assertEqual(x,observation_id("RB2701","2026-11-13T15:00:00+08:00","up"))
        self.assertNotEqual(x,observation_id("RB2701","2026-11-13T15:00:00+08:00","down"))
if __name__=="__main__":unittest.main()

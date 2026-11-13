import unittest
from datetime import datetime,timedelta,timezone
from session_audit_v054 import inspect_bar,monitor_audit
SH=timezone(timedelta(hours=8))
T=datetime(2026,11,13,14,20,tzinfo=SH)
C="RB2701"
def check(**kwargs):
    return inspect_bar(contract=C,bar_time=T-timedelta(minutes=60),
      observed_at=T,**kwargs)
class CloseAndRolloverTests(unittest.TestCase):
    def test_unknown_timestamp_rejected(self):
        self.assertEqual(check()["class"],"timestamp_semantics_unknown")
    def test_future_timestamp_rejected(self):
        r=inspect_bar(contract=C,bar_time=T+timedelta(minutes=2),observed_at=T)
        self.assertEqual(r["class"],"invalid_future_timestamp")
    def test_calendar_missing(self):
        self.assertEqual(check(timestamp_semantics="close")["class"],"session_unmapped")
    def test_unclosed(self):
        r=check(timestamp_semantics="open",expected_end=T+timedelta(minutes=5))
        self.assertEqual(r["class"],"forming")
    def test_calendar_unverified(self):
        r=check(timestamp_semantics="close",expected_end=T-timedelta(minutes=60))
        self.assertEqual(r["class"],"calendar_unverified")
    def test_stable_cannot_claim_official_close(self):
        d={"open":10,"high":11,"low":9,"close":10,"volume":12}
        a={**d,"observed_at":T-timedelta(seconds=30)}
        b={**d,"observed_at":T}
        r=check(timestamp_semantics="close",expected_end=T-timedelta(minutes=60),
                exchange_calendar_evidence=True,source_final_evidence=True,
                prior_bar=a,last_bar=b)
        self.assertEqual(r["class"],"candidate_final_not_official")
        self.assertFalse(r["official_close_verified"])
        self.assertFalse(r["alert_eligible"])
    def test_unknown_continuous_alias_rejected(self):
        with self.assertRaises(ValueError):
            inspect_bar(contract="RB0",bar_time=T,observed_at=T)
    def test_roll_change_blocks(self):
        v=monitor_audit(data={"main_candidates":[{"product":"RB","candidate":"RB2705",
          "leaders_agree":True,"candidate_stable":True,"roll_change_detected":True,
          "snapshot_age_minutes":2,"snapshot_timestamp_independently_verified":False,
          "main_contract_verified":False}],"latest_scans":[]},now=T)
        self.assertTrue(v["main_contract_candidates"][0]["roll_change_detected"])
        self.assertFalse(v["main_contract_candidates"][0]["allowed_for_realtime_alert"])
    def test_healthy_snapshot_still_research_only(self):
        v=monitor_audit(data={"main_candidates":[{"product":"RB","candidate":"RB2701",
            "leaders_agree":True,"candidate_stable":True,"snapshot_age_minutes":1}],
            "latest_scans":[{"contract":"RB2701","close_verified":0}]},now=T)
        self.assertFalse(v["notification_enabled"])
        self.assertIn("60分钟K线收盘未独立核验",v["main_contract_candidates"][0]["blockers"])
    def test_no_input_safe(self):
        self.assertEqual(monitor_audit(data={},now=T)["candidate_count"],0)
if __name__=="__main__":unittest.main()

import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from discovery_v053 import (normalized_snapshot,reconcile_candidates,
                            discover_candidates,run_discovery)
from close_gate_v053 import assess_closed_bar,close_policy_summary
TZ=timezone(timedelta(hours=8))
NOW=datetime(2026,11,13,14,30,tzinfo=TZ)

class FakeFrame:
    empty=False
    def __init__(self,rows):self.rows=rows
    def to_dict(self,orient):assert orient=="records";return self.rows
class FakeProvider:
    def futures_zh_realtime(self,symbol):
        assert symbol=="螺纹钢"
        return FakeFrame([{"symbol":"RB2701","volume":500,"position":1000},
                          {"symbol":"RB2705","volume":100,"position":200},
                          {"symbol":"RB0","volume":10000,"position":20000}])
class DiscoveryTests(unittest.TestCase):
    def test_filters_continuous_alias(self):
        rows=normalized_snapshot(FakeProvider().futures_zh_realtime("螺纹钢"),product="RB")
        self.assertEqual({x["contract"] for x in rows},{"RB2701","RB2705"})
    def test_discovery_still_unverified(self):
        v=discover_candidates([{"name":"螺纹钢","product":"RB"}],provider=FakeProvider(),now=NOW)
        self.assertEqual(v[0]["candidate"],"RB2701")
        self.assertFalse(v[0]["main_contract_verified"])
    def test_repeated_candidate_is_stable_not_verified(self):
        v=discover_candidates([{"name":"螺纹钢","product":"RB"}],provider=FakeProvider(),now=NOW)
        p=reconcile_candidates([],v)
        q=reconcile_candidates(p,v)
        self.assertFalse(p[0]["candidate_stable"])
        self.assertTrue(q[0]["candidate_stable"])
        self.assertFalse(q[0]["main_contract_verified"])
        self.assertFalse(q[0]["allowed_for_realtime_alert"])
    def test_roll_observation(self):
        old=[{"product":"RB","candidate":"RB2701","leaders_agree":True,"stable_count":4}]
        new=[{"product":"RB","candidate":"RB2705","leaders_agree":True,"snapshot_fresh":True}]
        x=reconcile_candidates(old,new)[0]
        self.assertTrue(x["roll_change_detected"])
        self.assertFalse(x["candidate_stable"])
    def test_ambiguity_and_bad_data_rejected(self):
        with self.assertRaises(ValueError):
            normalized_snapshot(FakeFrame([{"symbol":"RB2701","volume":-1,"position":30}]),product="RB")
    def test_bad_products_rejected(self):
        with self.assertRaises(ValueError):
            discover_candidates([{"name":"螺纹钢","product":"RB0"}],provider=FakeProvider(),now=NOW)
    def test_close_no_semantics(self):
        x=assess_closed_bar(bar_time=NOW-timedelta(minutes=60),observed_at=NOW)
        self.assertEqual(x["status"],"timestamp_semantics_unknown")
        self.assertFalse(x["notification_allowed"])
    def test_close_vendor_never_confirms(self):
        a={"observed_at":NOW-timedelta(seconds=30),"open":10,"high":11,"low":9,"close":10,"volume":100}
        b={**a,"observed_at":NOW}
        x=assess_closed_bar(bar_time=NOW-timedelta(minutes=60),observed_at=NOW,
            timestamp_semantics="close",exchange_calendar_verified=True,
            prior_snapshot=a,current_snapshot=b)
        self.assertEqual(x["status"],"stable_not_exchange_verified")
        self.assertFalse(x["bar_close_verified"])
    def test_future_time_rejected(self):
        x=assess_closed_bar(bar_time=NOW+timedelta(minutes=1),observed_at=NOW)
        self.assertEqual(x["status"],"future_timestamp")
    def test_no_exchange_calendar(self):
        x=assess_closed_bar(bar_time=NOW-timedelta(minutes=60),observed_at=NOW,
            timestamp_semantics="open")
        self.assertEqual(x["status"],"exchange_calendar_unverified")
    def test_unknown_never_notifies(self):
        self.assertFalse(close_policy_summary()["notification_enabled"])
if __name__=="__main__":unittest.main()

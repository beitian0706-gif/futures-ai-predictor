import unittest
from datetime import datetime,timedelta,timezone
from main_candidates_v052 import select_main_candidates
NOW=datetime(2026,11,13,15,30,tzinfo=timezone(timedelta(hours=8)))
class MainCandidateTests(unittest.TestCase):
 def test_agreement_is_still_unverified(self):
  v=select_main_candidates([{"contract":"RB2701","volume":400,"open_interest":2000},{"contract":"RB2705","volume":100,"open_interest":100}],asof=NOW.isoformat(),now=NOW)
  self.assertEqual(v[0]["candidate"],"RB2701")
  self.assertTrue(v[0]["leaders_agree"])
  self.assertFalse(v[0]["main_contract_verified"])
 def test_disagreement(self):
  v=select_main_candidates([{"contract":"RB2701","volume":400,"open_interest":100},{"contract":"RB2705","volume":100,"open_interest":2000}],asof=NOW.isoformat(),now=NOW)
  self.assertFalse(v[0]["leaders_agree"])
 def test_stale(self):
  v=select_main_candidates([{"contract":"JM2701","volume":500,"open_interest":200}],asof=(NOW-timedelta(days=1)).isoformat(),now=NOW)
  self.assertFalse(v[0]["snapshot_fresh"])
 def test_continuous_rejected(self):
  with self.assertRaises(ValueError):
   select_main_candidates([{"contract":"RB0","volume":400,"open_interest":200}],asof=NOW.isoformat(),now=NOW)
if __name__=="__main__":unittest.main()

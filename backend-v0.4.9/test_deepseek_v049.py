import os
import unittest
from unittest.mock import patch

from deepseek_analysis import generate_report

class MockResponse:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False

class DeepSeekTests(unittest.TestCase):
    def test_missing_key(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "未配置"):
                generate_report("RB2701", {})
    def test_completed_report(self):
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "完成的历史研究报告"}}]}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only"}), patch("urllib.request.urlopen", return_value=MockResponse(None)), patch("json.load", return_value=response):
            self.assertIn("完成", generate_report("RB2701", {"combined_score": -0.21}))
    def test_truncated_report_rejected(self):
        response = {"choices": [{"finish_reason": "length", "message": {"content": "未完成"}}]}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only"}), patch("urllib.request.urlopen", return_value=MockResponse(None)), patch("json.load", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "截断"):
                generate_report("RB2701", {})

if __name__ == "__main__":
    unittest.main()

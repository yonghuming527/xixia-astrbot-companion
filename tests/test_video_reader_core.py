import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_xixia_video_reader.reader_core import (  # noqa: E402
    CN_TZ,
    DailyLedger,
    clean_subtitle,
    extract_supported_url,
    requested_platform,
)


class ReaderCoreTests(unittest.TestCase):
    def test_domains_are_strictly_allowlisted(self):
        self.assertEqual(
            extract_supported_url("看看 https://v.douyin.com/abc/ 好吗"),
            "https://v.douyin.com/abc/",
        )
        self.assertEqual(extract_supported_url("https://example.com/video"), "")
        self.assertEqual(extract_supported_url("https://bilibili.com.evil.test/x"), "")

    def test_subtitle_cleanup(self):
        raw = "WEBVTT\n\n00:00:00 --> 00:00:01\n<c>你好</c>\n你好\n"
        self.assertEqual(clean_subtitle(raw), "你好")

    def test_discovery_requires_an_explicit_action(self):
        self.assertEqual(requested_platform("帮我看看抖音"), "douyin")
        self.assertEqual(requested_platform("去B站逛逛"), "bilibili")
        self.assertEqual(requested_platform("抖音视频是什么"), "")
        self.assertEqual(requested_platform("B站推荐算法"), "")

    def test_daily_limit_and_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            ledger = DailyLedger(path, 9)
            self.assertEqual(ledger.limit, 5)
            for index in range(5):
                ledger.commit({"url": str(index)})
            self.assertEqual(ledger.remaining, 0)
            with self.assertRaisesRegex(RuntimeError, "daily_limit"):
                ledger.commit({"url": "six"})
            ledger.rollover(datetime(2026, 10, 28, 9, tzinfo=CN_TZ))
            self.assertEqual(ledger.count, 0)


if __name__ == "__main__":
    unittest.main()

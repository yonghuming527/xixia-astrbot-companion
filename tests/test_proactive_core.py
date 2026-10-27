import datetime as dt
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_xixia_proactive.main import (  # noqa: E402
    awaits_reply,
    decision_reason,
    is_quiet,
    limit_reply_text,
)


CN_TZ = dt.timezone(dt.timedelta(hours=8))


def at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, 26, hour, minute, tzinfo=CN_TZ)


class ProactiveCoreTests(unittest.TestCase):
    def test_quiet_hours(self):
        self.assertTrue(is_quiet(at(23, 30), "23:30", "08:30"))
        self.assertTrue(is_quiet(at(8, 29), "23:30", "08:30"))
        self.assertFalse(is_quiet(at(8, 30), "23:30", "08:30"))

    def test_reply_state(self):
        self.assertTrue(awaits_reply("你今天怎么样？"))
        self.assertFalse(awaits_reply("小汐记住啦。"))

    def test_decision_reason(self):
        now = at(12)
        state = {
            "last_user_at": now.timestamp() - 7200,
            "last_bot_at": now.timestamp() - 7000,
            "last_proactive_at": 0,
            "topic_open": False,
            "sent_count": 1,
            "daily_limit": 4,
        }
        self.assertEqual(
            decision_reason(
                state,
                now,
                min_idle_seconds=5400,
                min_interval_seconds=5400,
                quiet_start="23:30",
                quiet_end="08:30",
            ),
            "eligible",
        )

    def test_reply_hard_limit(self):
        text = "\n".join(["第一句。", "第二句。", "第三句。", "第四句。", "第五句。"])
        parts = limit_reply_text(text).splitlines()
        self.assertEqual(len(parts), 4)
        self.assertTrue(all(len(part) <= 20 for part in parts))


if __name__ == "__main__":
    unittest.main()

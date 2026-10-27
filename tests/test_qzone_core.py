import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_xixia_qzone.core import (  # noqa: E402
    normalize_content,
    parse_natural_publish_request,
)


class QzoneContentTests(unittest.TestCase):
    def test_normalize_content(self):
        self.assertEqual(normalize_content("  夏夜好亮  "), "夏夜好亮")
        with self.assertRaises(ValueError):
            normalize_content("   ")
        with self.assertRaises(ValueError):
            normalize_content("1234", 3)

    def test_explicit_requests(self):
        self.assertEqual(
            parse_natural_publish_request("发一个你自己想发的动态"),
            ("generate", ""),
        )
        self.assertEqual(
            parse_natural_publish_request("发动态：今晚的风很轻。"),
            ("direct", "今晚的风很轻。"),
        )

    def test_question_and_cancellation_do_not_publish(self):
        self.assertIsNone(parse_natural_publish_request("你会发动态吗？"))
        self.assertIsNone(parse_natural_publish_request("不要发动态"))
        self.assertIsNone(parse_natural_publish_request("/动态 测试"))


if __name__ == "__main__":
    unittest.main()

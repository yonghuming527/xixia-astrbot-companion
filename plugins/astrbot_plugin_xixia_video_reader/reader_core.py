import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


CN_TZ = timezone(timedelta(hours=8))
URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
ALLOWED_HOSTS = {
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
    "b23.tv",
    "douyin.com",
    "www.douyin.com",
    "v.douyin.com",
}
DISCOVERY_MARKERS = (
    "看看",
    "帮我看",
    "看一个",
    "看条",
    "找一个",
    "找个",
    "找条",
    "推荐一个",
    "推荐个",
    "推荐条",
    "浏览",
    "逛逛",
    "逛一逛",
    "发一个",
    "发个",
    "发条",
    "来一个",
    "来个",
    "来条",
)


def extract_supported_url(text: str) -> str:
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip("，。！？、；：,.!?;:)")
        host = (urlparse(url).hostname or "").lower()
        if host in ALLOWED_HOSTS:
            return url
    return ""


def requested_platform(text: str) -> str:
    value = text or ""
    if not any(marker in value for marker in DISCOVERY_MARKERS):
        return ""
    if "抖音" in value or "Dou音" in value:
        return "douyin"
    if "哔哩哔哩" in value or "B站" in value or "b站" in value:
        return "bilibili"
    return ""


def clean_subtitle(text: str, limit: int = 6000) -> str:
    lines = []
    seen = set()
    for raw in text.replace("\ufeff", "").splitlines():
        line = raw.strip()
        if (
            not line
            or line == "WEBVTT"
            or "-->" in line
            or line.isdigit()
            or line.startswith(("NOTE", "Kind:", "Language:"))
        ):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)[:limit]


class DailyLedger:
    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = max(0, min(int(limit), 5))
        self.data = self._load()
        self.rollover()

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def rollover(self, now: datetime | None = None) -> None:
        today = (now or datetime.now(CN_TZ)).date().isoformat()
        if self.data.get("date") != today:
            self.data = {"date": today, "count": 0, "items": []}
            self.save()

    @property
    def count(self) -> int:
        return int(self.data.get("count", 0))

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.count)

    def commit(self, item: dict) -> None:
        self.rollover()
        if self.count >= self.limit:
            raise RuntimeError("daily_limit")
        self.data["count"] = self.count + 1
        self.data.setdefault("items", []).append(item)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp.replace(self.path)

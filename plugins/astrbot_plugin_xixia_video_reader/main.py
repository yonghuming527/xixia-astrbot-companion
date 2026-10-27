import asyncio
import html
import json
import random
import re
import shutil
import sys
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .reader_core import (
    DailyLedger,
    clean_subtitle,
    extract_supported_url,
    requested_platform,
)


PLUGIN_NAME = "astrbot_plugin_xixia_video_reader"
SONG_REQUEST_RE = re.compile(
    r"^\s*我要听歌(?:(?:\s+|[：:，,])(?P<song>.*))?\s*$"
)


class XixiaVideoReader(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.context = context
        self.config = config
        self.target_umo = str(
            config.get("target_umo", "")
        )
        self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = DailyLedger(
            self.data_dir / "state.json", int(config.get("daily_limit", 5))
        )
        self.lock = asyncio.Lock()
        logger.info("汐夏只读视频理解已启动：两平台合计每日最多 %s 条", self.ledger.limit)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=1200)
    async def download_song_video(self, event: AstrMessageEvent):
        if not self.config.get("song_download_enabled", True):
            return
        if event.unified_msg_origin != self.target_umo:
            return
        match = SONG_REQUEST_RE.fullmatch(event.get_message_str() or "")
        if not match:
            return

        event.should_call_llm(False)
        event.stop_event()
        song_name = str(match.group("song") or "").strip().strip("《》“”\"'")
        if not song_name:
            yield event.plain_result("要听哪首歌呀？请发：我要听歌 歌名")
            return
        if len(song_name) > 80 or extract_supported_url(song_name):
            yield event.plain_result("歌名格式不对，请只写歌曲名称。")
            return

        async with self.lock:
            try:
                item, saved_path = await self._download_song_video(song_name)
                yield event.plain_result(
                    f"找到《{song_name}》的对应视频啦，已准备歌曲素材。\n"
                    f"来源：{item['url']}\n"
                    "这次听歌下载不占今天的视频浏览额度。"
                )
                logger.info("听歌素材已保存：%s", saved_path)
            except Exception as exc:
                logger.exception("听歌视频下载失败")
                yield event.plain_result(f"这首歌暂时没准备好：{self._friendly_error(exc)}")

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=1100)
    async def read_video(self, event: AstrMessageEvent):
        if not self.config.get("enabled", True):
            return
        if event.unified_msg_origin != self.target_umo:
            return
        message = event.get_message_str()
        url = extract_supported_url(message)
        platform = requested_platform(message) if not url else ""
        if not url and not platform:
            return

        event.should_call_llm(False)
        event.stop_event()
        async with self.lock:
            self.ledger.rollover()
            if self.ledger.remaining <= 0:
                yield event.plain_result("今天五条看完啦，明天再一起看～")
                return
            try:
                if platform == "douyin":
                    url = "https://www.douyin.com/?recommend=1"
                elif platform == "bilibili":
                    url = await asyncio.to_thread(self._discover_bilibili_url)
                result, item = await self._understand(url, event.unified_msg_origin)
                self.ledger.commit(item)
                yield event.plain_result(
                    f"{result}\n原视频：{item['url']}\n今天还可看 {self.ledger.remaining} 条。"
                )
            except Exception as exc:
                logger.exception("只读视频理解失败")
                yield event.plain_result(f"这条暂时没看成：{self._friendly_error(exc)}")

    async def _understand(self, url: str, umo: str) -> tuple[str, dict]:
        work_dir = self.data_dir / "temp" / uuid.uuid4().hex
        work_dir.mkdir(parents=True, exist_ok=False)
        try:
            info, video_path = await asyncio.to_thread(self._download, url, work_dir)
            duration = float(info.get("duration") or 0)
            if duration <= 0:
                duration = await self._probe_duration(video_path)
            analyze_seconds = min(
                max(1, int(self.config.get("max_analyze_seconds", 300))),
                int(duration) if duration > 0 else 300,
            )
            frames = await self._extract_frames(video_path, work_dir, analyze_seconds)
            transcript = self._read_subtitles(work_dir)
            if not transcript:
                audio = await self._extract_audio(video_path, work_dir, analyze_seconds)
                stt = self.context.get_provider_by_id(
                    str(self.config.get("stt_provider_id", "siliconflow-asr"))
                )
                if stt:
                    transcript = (await stt.get_text(str(audio))).strip()

            title = str(info.get("title") or "未命名视频")[:120]
            uploader = str(info.get("uploader") or info.get("channel") or "")[:80]
            prompt = (
                f"标题：{title}\n作者：{uploader}\n"
                f"时长：{int(duration)}秒；已分析前{analyze_seconds}秒。\n"
                f"字幕或语音转写：\n{transcript or '没有可用转写，请主要依据画面判断。'}\n\n"
                "结合所有关键帧与转写说明这条视频讲了什么。必须简短自然，"
                "总计不超过90个中文字符；先说主要内容，再说一个具体亮点或感受。"
                "不要假装看到了关键帧和转写之外的内容。"
            )
            response = await self.context.llm_generate(
                chat_provider_id=str(
                    self.config.get("vision_provider_id", "qwen3-vl-8b")
                ),
                prompt=prompt,
                image_urls=[str(path) for path in frames],
                system_prompt=(
                    "你是汐夏。准确理解视频，语气自然亲近；只陈述有证据的内容，"
                    "不进行任何点赞、评论、关注、收藏、投币或发布操作。"
                ),
                temperature=0.2,
                max_tokens=220,
            )
            summary = str(getattr(response, "completion_text", "") or "").strip()
            if not summary:
                raise RuntimeError("视觉模型没有返回内容")
            canonical = str(info.get("webpage_url") or info.get("original_url") or url)
            return summary, {
                "url": canonical,
                "title": title,
                "platform": str(info.get("extractor_key") or info.get("extractor") or ""),
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _download_song_video(self, song_name: str) -> tuple[dict, Path]:
        work_dir = self.data_dir / "temp" / f"song_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=False)
        try:
            url, matched_title = await asyncio.to_thread(
                self._discover_bilibili_song_url, song_name
            )
            max_seconds = max(60, min(int(self.config.get("max_song_seconds", 600)), 600))
            info, video_path = await asyncio.to_thread(
                self._download, url, work_dir, max_seconds
            )
            title = str(info.get("title") or matched_title or song_name)[:120]
            if self._normalize_song_text(song_name) not in self._normalize_song_text(title):
                raise RuntimeError("搜索结果与歌名不匹配")
            destination_dir = self.data_dir / "song_downloads"
            destination_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:80]
            destination = destination_dir / f"{safe_title}_{uuid.uuid4().hex[:8]}{video_path.suffix}"
            shutil.move(str(video_path), destination)
            return {
                "url": str(info.get("webpage_url") or info.get("original_url") or url),
                "title": title,
                "platform": "bilibili",
            }, destination
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _download(self, url: str, work_dir: Path, max_seconds: int | None = None):
        host = (urlparse(url).hostname or "").lower()
        if host in {"douyin.com", "www.douyin.com", "v.douyin.com"}:
            from .douyin_browser import download_douyin_with_edge

            video_path = work_dir / "douyin.mp4"
            cookie_file = Path(str(self.config.get("cookie_file", "")))
            info = download_douyin_with_edge(
                url,
                video_path,
                cookie_file,
                Path(
                    str(
                        self.config.get(
                            "edge_path",
                            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                        )
                    )
                ),
                work_dir / "edge_profile",
            )
            return info, video_path

        module_text = str(self.config.get("yt_dlp_module_path", "")).strip()
        if module_text:
            module_path = Path(module_text)
            if not (module_path / "yt_dlp").is_dir():
                raise RuntimeError("yt-dlp 模块目录无效")
            if module_text not in sys.path:
                sys.path.insert(0, module_text)
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("未安装 yt-dlp") from exc
        from yt_dlp.utils import download_range_func

        ffmpeg = str(Path(str(self.config.get("ffmpeg_path", ""))).parent)
        max_seconds = max(
            1,
            int(max_seconds)
            if max_seconds is not None
            else int(self.config.get("max_analyze_seconds", 300)),
        )
        base_options = {
            "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "playlist_items": "1",
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/worst",
            "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg,
            "download_ranges": download_range_func([], [(0, max_seconds)]),
            "force_keyframes_at_cuts": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh-Hans", "zh-Hant", "zh", "en"],
            "subtitlesformat": "vtt/best",
            "max_filesize": 150 * 1024 * 1024,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
        }
        browsers = [
            part.strip().lower()
            for part in str(self.config.get("cookie_browsers", "edge,chrome")).split(",")
            if part.strip().lower() in {"edge", "chrome"}
        ]
        cookie_file = Path(str(self.config.get("cookie_file", "")))
        attempts = []
        if cookie_file.is_file():
            attempts.append(("file", str(cookie_file)))
        attempts.extend(("browser", browser) for browser in browsers)
        attempts.append(("public", ""))
        errors = []
        for source, value in attempts:
            options = dict(base_options)
            if source == "file":
                options["cookiefile"] = value
            elif source == "browser":
                options["cookiesfrombrowser"] = (value,)
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info.get("_type") == "playlist":
                        info = next(iter(info.get("entries") or []), None)
                    if not info:
                        raise RuntimeError("没有取得视频信息")
                videos = [
                    p
                    for p in work_dir.iterdir()
                    if p.suffix.lower() in {".mp4", ".webm", ".mkv", ".mov"}
                ]
                if not videos:
                    raise RuntimeError("视频下载结果为空")
                return info, max(videos, key=lambda p: p.stat().st_size)
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError(errors[-1] if errors else "视频读取失败")

    def _discover_bilibili_url(self) -> str:
        request = urllib.request.Request(
            "https://api.bilibili.com/x/web-interface/index/top/feed/rcmd?ps=20&fresh_type=4",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://www.bilibili.com/",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        items = payload.get("data", {}).get("item", [])
        seen = {str(item.get("url") or "") for item in self.ledger.data.get("items", [])}
        choices = []
        for item in items:
            bvid = str(item.get("bvid") or "")
            if not bvid:
                continue
            url = f"https://www.bilibili.com/video/{bvid}"
            if url not in seen:
                choices.append(url)
        if not choices:
            raise RuntimeError("暂时没有取得新的 B 站推荐")
        return random.SystemRandom().choice(choices[:10])

    def _discover_bilibili_song_url(self, song_name: str) -> tuple[str, str]:
        endpoint = (
            "https://api.bilibili.com/x/web-interface/search/type"
            f"?search_type=video&keyword={quote(song_name + ' 歌曲')}"
        )
        request = urllib.request.Request(
            endpoint,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://search.bilibili.com/",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if int(payload.get("code", -1)) != 0:
            raise RuntimeError("B站歌曲搜索失败")

        wanted = self._normalize_song_text(song_name)
        candidates = []
        for item in payload.get("data", {}).get("result", []) or []:
            bvid = str(item.get("bvid") or "")
            title = re.sub(r"<[^>]+>", "", html.unescape(str(item.get("title") or "")))
            if not bvid or not wanted or wanted not in self._normalize_song_text(title):
                continue
            score = sum(
                marker in title.lower()
                for marker in ("官方", "完整版", "mv", "歌曲", "音乐", "演唱")
            )
            candidates.append((score, title, f"https://www.bilibili.com/video/{bvid}"))
        if not candidates:
            raise RuntimeError("没有找到歌名匹配的视频")
        _score, title, url = max(candidates, key=lambda item: item[0])
        return url, title

    @staticmethod
    def _normalize_song_text(value: str) -> str:
        return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())

    async def _extract_frames(
        self, video: Path, work_dir: Path, duration: int
    ) -> list[Path]:
        count = max(3, min(int(self.config.get("frame_count", 6)), 8))
        timestamps = [max(0.1, duration * (i + 0.5) / count) for i in range(count)]
        paths = []
        for index, timestamp in enumerate(timestamps):
            output = work_dir / f"frame_{index:02d}.jpg"
            await self._run_ffmpeg(
                "-ss", f"{timestamp:.2f}", "-i", str(video), "-frames:v", "1",
                "-vf", "scale='min(960,iw)':-2", "-q:v", "3", str(output)
            )
            if output.exists():
                paths.append(output)
        if not paths:
            raise RuntimeError("关键帧提取失败")
        return paths

    async def _probe_duration(self, video: Path) -> float:
        ffprobe = Path(str(self.config.get("ffmpeg_path"))).with_name("ffprobe.exe")
        process = await asyncio.create_subprocess_exec(
            str(ffprobe), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(stderr.decode("utf-8", "ignore")[-300:] or "时长检测失败")
        try:
            return float(stdout.decode("ascii", "ignore").strip())
        except ValueError as exc:
            raise RuntimeError("无法读取视频时长") from exc

    async def _extract_audio(
        self, video: Path, work_dir: Path, duration: int
    ) -> Path:
        output = work_dir / "audio.wav"
        await self._run_ffmpeg(
            "-i", str(video), "-t", str(duration), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", str(output)
        )
        if not output.exists():
            raise RuntimeError("音频提取失败")
        return output

    async def _run_ffmpeg(self, *args: str) -> None:
        process = await asyncio.create_subprocess_exec(
            str(self.config.get("ffmpeg_path")), "-hide_banner", "-loglevel", "error",
            "-y", *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _stdout, stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(stderr.decode("utf-8", "ignore")[-300:] or "FFmpeg 失败")

    @staticmethod
    def _read_subtitles(work_dir: Path) -> str:
        for pattern in ("*.vtt", "*.srt"):
            for path in work_dir.glob(pattern):
                text = clean_subtitle(path.read_text(encoding="utf-8", errors="ignore"))
                if text:
                    return text
        return ""

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc)
        if "Unsupported URL" in text:
            return "这个链接格式还不支持。"
        if "Sign in" in text or "login" in text.lower():
            return "登录状态没读到。"
        if "HTTP Error 429" in text:
            return "平台限流了，晚点再试吧。"
        return "读取失败，稍后再试吧。"

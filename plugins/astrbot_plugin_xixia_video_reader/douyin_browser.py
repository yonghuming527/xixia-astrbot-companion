import json
import base64
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
)


def _cdp(ws, method: str, params: dict | None, message_id: int) -> dict:
    ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
    while True:
        payload = json.loads(ws.recv())
        if payload.get("method") == "Network.responseReceived":
            events = getattr(ws, "_xixia_network_events", None)
            if isinstance(events, list):
                events.append(payload.get("params", {}))
        if payload.get("id") == message_id:
            if payload.get("error"):
                raise RuntimeError(payload["error"].get("message", "CDP 调用失败"))
            return payload.get("result", {})


def _wait_tab(port: int, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json", timeout=1
            ) as response:
                tabs = json.load(response)
            pages = [tab for tab in tabs if tab.get("type") == "page"]
            if pages:
                return pages[0]
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("抖音只读浏览器启动超时")


def _read_netscape_cookies(path: Path) -> list[dict]:
    cookies = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) != 7 or not fields[5]:
            continue
        domain, _include_subdomains, cookie_path, secure, expires, name, value = fields
        item = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": cookie_path or "/",
            "secure": secure.upper() == "TRUE",
        }
        if expires.isdigit() and int(expires) > 0:
            item["expires"] = int(expires)
        cookies.append(item)
    return cookies


def _evaluate(ws, expression: str, message_id: int) -> object:
    result = _cdp(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        message_id,
    )
    return result.get("result", {}).get("value")


def _feed_video_url(ws) -> str:
    events = getattr(ws, "_xixia_network_events", [])
    candidates = []
    for event in reversed(events):
        response = event.get("response", {})
        url = str(response.get("url") or "")
        if "douyin.com/aweme/" in url and "feed" in url:
            candidates.append(str(event.get("requestId") or ""))
    for index, request_id in enumerate(candidates[:8]):
        if not request_id:
            continue
        try:
            result = _cdp(
                ws,
                "Network.getResponseBody",
                {"requestId": request_id},
                700 + index,
            )
            body = str(result.get("body") or "")
            if result.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", "ignore")
            payload = json.loads(body)
            items = payload.get("aweme_list") or payload.get("data") or []
            if isinstance(items, dict):
                items = items.get("aweme_list") or items.get("items") or []
            if isinstance(items, list):
                for item in items:
                    video_id = str(item.get("aweme_id") or item.get("item_id") or "")
                    if video_id.isdigit():
                        return f"https://www.douyin.com/video/{video_id}"
        except Exception:
            continue
    return ""


def download_douyin_with_edge(
    url: str,
    output: Path,
    cookie_file: Path,
    edge_path: Path,
    profile_dir: Path,
    *,
    port: int = 9224,
    max_bytes: int = 150 * 1024 * 1024,
) -> dict:
    if not cookie_file.is_file():
        raise RuntimeError("缺少机器人专用抖音 Cookie")
    profile_dir = profile_dir.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [
            str(edge_path),
            "--headless=new",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-extensions",
            "--lang=zh-CN",
            "--window-size=1920,1080",
            f"--remote-debugging-port={port}",
            f"--remote-allow-origins=http://127.0.0.1:{port}",
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    ws = None
    page_url = url
    try:
        tab = _wait_tab(port)
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=15)
        ws._xixia_network_events = []
        _cdp(ws, "Network.enable", {}, 1)
        _cdp(
            ws,
            "Network.setUserAgentOverride",
            {"userAgent": USER_AGENT, "acceptLanguage": "zh-CN,zh;q=0.9"},
            2,
        )
        _cdp(
            ws,
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "Object.defineProperty(navigator,'languages',{get:()=>['zh-CN','zh']});"
                )
            },
            3,
        )
        _cdp(
            ws,
            "Network.setCookies",
            {"cookies": _read_netscape_cookies(cookie_file)},
            4,
        )
        _cdp(ws, "Page.navigate", {"url": url}, 5)
        expression = r"""
(() => {
  const videos = [...document.querySelectorAll('video')];
  const direct = videos.flatMap(v => [v.currentSrc, v.src])
    .filter(x => x && /^https?:/.test(x));
  const resources = performance.getEntriesByType('resource').map(x => x.name)
    .filter(x => /^https?:/.test(x) && (/douyinvod|\.mp4|video\/tos/i.test(x)));
  const first = videos[0];
  const shareUrl = [...document.querySelectorAll('a[href*="/video/"]')]
    .map(a => a.href).find(x => /\/video\/\d+/.test(x)) || '';
  return {
    title: document.title || '',
    pageUrl: location.href,
    duration: first && Number.isFinite(first.duration) ? first.duration : 0,
    current: direct[0] || '',
    shareUrl,
    videoCount: videos.length,
    videoLinkCount: [...document.querySelectorAll('a[href*="/video/"]')].length,
    body: (document.body && document.body.innerText || '').slice(0, 160),
    media: [...new Set([...direct, ...resources])]
  };
})()
"""
        details = {}
        deadline = time.time() + 25
        message_id = 10
        navigated_share = False
        while time.time() < deadline:
            value = _evaluate(ws, expression, message_id)
            message_id += 1
            if isinstance(value, dict):
                details = value
                page_url = str(value.get("pageUrl") or page_url)
                if value.get("media"):
                    break
                share_url = str(value.get("shareUrl") or "")
                if share_url and not navigated_share:
                    _cdp(ws, "Page.navigate", {"url": share_url}, message_id)
                    message_id += 1
                    navigated_share = True
                    time.sleep(2)
                    continue
            _evaluate(
                ws,
                "window.scrollBy(0, 500); const v=document.querySelector('video');"
                "if(v){v.muted=true;v.play().catch(()=>{});} true",
                message_id,
            )
            message_id += 1
            time.sleep(1)
        media_urls = [
            str(item) for item in details.get("media", []) if str(item).startswith("http")
        ]
        if not media_urls:
            raise RuntimeError(
                "抖音页面没有返回可读媒体流："
                + str(
                    {
                        "title": details.get("title") or page_url,
                        "videos": details.get("videoCount", 0),
                        "links": details.get("videoLinkCount", 0),
                        "body": details.get("body", ""),
                    }
                )[:300]
            )
        current = str(details.get("current") or "")
        media_url = current if current.startswith("http") else max(
            media_urls, key=lambda item: ("douyinvod" in item, len(item))
        )
        feed_video_url = _feed_video_url(ws)
        if not details.get("shareUrl") and not feed_video_url:
            _evaluate(
                ws,
                r"""
(() => {
  const nodes = [...document.querySelectorAll('button,[role="button"],div,span')];
  const target = nodes.find(x => ((x.innerText || x.getAttribute('aria-label') || '').trim() === '分享'));
  const button = target && (target.closest('button,[role="button"]') || target);
  if (button) { button.click(); return true; }
  return false;
})()
""",
                850,
            )
            time.sleep(1)
            share_value = _evaluate(
                ws,
                r"""
(() => {
  const html = document.documentElement.innerHTML
    .replaceAll('\\u002F', '/').replaceAll('&amp;', '&');
  const direct = html.match(/https?:\/\/(?:www\.)?douyin\.com\/video\/\d+/i);
  if (direct) return direct[0];
  const id = html.match(/(?:awemeId|aweme_id)["'\\]*\s*[:=]\s*["'\\]*(\d{15,})/i);
  return id ? `https://www.douyin.com/video/${id[1]}` : '';
})()
""",
                851,
            )
            if isinstance(share_value, str) and share_value.startswith("http"):
                feed_video_url = share_value
        request = urllib.request.Request(
            media_url,
            headers={"User-Agent": USER_AGENT, "Referer": page_url},
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with urllib.request.urlopen(request, timeout=30) as response, output.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise RuntimeError("视频超过大小限制")
                handle.write(chunk)
        if size < 1024:
            raise RuntimeError("抖音媒体流为空")
        return {
            "title": str(details.get("title") or "抖音视频").replace(" - 抖音", "")[:120],
            "duration": float(details.get("duration") or 0),
            "webpage_url": str(details.get("shareUrl") or feed_video_url or page_url),
            "original_url": url,
            "extractor_key": "DouyinEdgeReadOnly",
        }
    finally:
        if ws is not None:
            try:
                _cdp(ws, "Browser.close", {}, 999)
            except Exception:
                pass
            try:
                ws.close()
            except Exception:
                pass
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)

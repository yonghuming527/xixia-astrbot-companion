import re


def normalize_content(content: str, max_length: int = 1000) -> str:
    text = content.strip()
    if not text:
        raise ValueError("动态内容不能为空")
    if len(text) > max_length:
        raise ValueError(f"动态最多 {max_length} 个字符")
    return text


def parse_natural_publish_request(message: str) -> tuple[str, str] | None:
    """返回 (direct, 正文) 或 (generate, '')；疑问和否定句不触发发布。"""
    text = message.strip()
    if not text or text.startswith("/"):
        return None
    if re.search(r"(?:别|不要|取消).{0,6}(?:发|发布).{0,8}(?:动态|说说)", text):
        return None
    if re.search(r"(?:吗|么|能不能|可不可以|会不会|[?？])\s*$", text):
        return None
    if not re.match(r"^(?:请)?(?:你)?(?:帮我)?(?:发|发布)", text):
        return None
    if not re.search(r"(?:动态|说说)", text):
        return None

    direct = re.search(r"(?:动态|说说)\s*[：:,，]\s*(.+)$", text)
    if direct:
        return "direct", direct.group(1).strip()
    direct = re.search(r"(?:动态|说说)\s+(.+)$", text)
    if direct and not re.search(r"(?:你自己|你想|想要发|随便|自己决定|自由发挥)", text):
        return "direct", direct.group(1).strip()
    return "generate", ""

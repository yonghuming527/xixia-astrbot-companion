from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

from .core import normalize_content, parse_natural_publish_request


class XixiaQzone(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.target_umo = str(config.get("target_umo", ""))

    def _allowed(self, event: AstrMessageEvent) -> bool:
        return bool(self.config.get("enabled", True)) and (
            event.unified_msg_origin == self.target_umo
        )

    async def _send(self, event: AstrMessageEvent, text: str) -> str:
        text = normalize_content(text, int(self.config.get("max_length", 1000)))
        result = await event.bot.api.call_action(
            "send_qzone_msg",
            content=text,
            images=[],
            ugc_right=int(self.config.get("visibility", 4)),
            target_uins=[],
        )
        tid = result.get("tid", "") if isinstance(result, dict) else ""
        logger.info("QQ空间动态发布成功，tid=%s", tid or "unknown")
        return text

    async def _draft(self) -> str:
        response = await self.context.llm_generate(
            chat_provider_id=str(self.config.get("llm_provider_id", "deepseek-flash")),
            prompt=(
                "写一条你现在真心想分享的QQ空间短动态，30到80个汉字。"
                "可以体现你喜欢夏夜、鲸鱼、画画、声音或日常小发现的审美；"
                "不要编造真实出门、见人或亲身经历，不泄露隐私，不写标签，"
                "不要解释，直接给正文。"
            ),
            system_prompt=(
                "你是汐夏，语气自然、简短、有自己的审美。内容适合好友可见的QQ空间。"
            ),
            temperature=0.9,
            max_tokens=120,
        )
        text = str(getattr(response, "completion_text", "") or "").strip()
        return text.strip("\"'“”‘’")

    @filter.command("动态")
    async def publish(self, event: AstrMessageEvent, content: GreedyStr):
        """发布一条好友可见的QQ空间文字动态。用法：/动态 内容"""
        event.should_call_llm(False)
        event.stop_event()

        if not self.config.get("enabled", True):
            yield event.plain_result("动态功能现在没有开启。")
            return
        if event.unified_msg_origin != self.target_umo:
            yield event.plain_result("你没有发布动态的权限。")
            return

        try:
            text = await self._send(event, str(content))
            yield event.plain_result("发好啦，默认只有好友能看到。")
        except ValueError as exc:
            yield event.plain_result(str(exc))
        except Exception:
            logger.exception("QQ空间动态发布失败")
            yield event.plain_result("这条没发出去，我没有重复尝试。")

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=1150)
    async def publish_naturally(self, event: AstrMessageEvent):
        request = parse_natural_publish_request(event.get_message_str())
        if request is None:
            return
        if event.unified_msg_origin != self.target_umo:
            return

        event.should_call_llm(False)
        event.stop_event()
        if not self._allowed(event):
            yield event.plain_result("动态功能现在没有开启。")
            return

        try:
            mode, supplied = request
            text = supplied if mode == "direct" else await self._draft()
            text = await self._send(event, text)
            yield event.plain_result(f"发好啦：{text}")
        except ValueError as exc:
            yield event.plain_result(str(exc))
        except Exception:
            logger.exception("自然语言QQ空间动态发布失败")
            yield event.plain_result("这条没发出去，我没有重复尝试。")

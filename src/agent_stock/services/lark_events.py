from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LarkMessage:
    message_type: str
    content: str
    sender_open_id: str
    chat_id: str | None = None
    message_id: str = ""


class LarkEventHandler:
    """飞书事件订阅处理器 — 接收用户消息并触发分析."""

    def __init__(self, encrypt_key: str = "") -> None:
        self.encrypt_key = encrypt_key

    def verify_signature(self, signature: str, timestamp: str, nonce: str, body: str) -> bool:
        """验证 Lark 请求签名."""
        if not self.encrypt_key:
            logger.warning("LARK_ENCRYPT_KEY not set, skipping signature verification")
            return True
        seed = timestamp + nonce + self.encrypt_key + body
        expected = hashlib.sha1(seed.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, signature)

    def handle_event(self, payload: dict) -> dict | str | None:
        """处理 Lark 事件，返回响应."""
        # URL 验证
        if "challenge" in payload:
            return {"challenge": payload["challenge"]}

        # 事件回调
        event_type = payload.get("header", {}).get("event_type", "")
        if event_type == "im.message.receive_v1":
            msg = self._parse_message(payload.get("event", {}))
            if msg:
                return self._handle_user_message(msg)

        return None

    def _parse_message(self, event: dict) -> LarkMessage | None:
        message = event.get("message", {})
        sender = event.get("sender", {})

        msg_type = message.get("message_type", "")
        content_str = message.get("content", "{}")
        try:
            content_json = json.loads(content_str)
        except json.JSONDecodeError:
            content_json = {}

        if msg_type == "text":
            text = content_json.get("text", "")
        else:
            text = content_str

        return LarkMessage(
            message_type=msg_type,
            content=text.strip(),
            sender_open_id=sender.get("sender_id", {}).get("open_id", ""),
            chat_id=message.get("chat_id"),
            message_id=message.get("message_id", ""),
        )

    def _handle_user_message(self, msg: LarkMessage) -> dict:
        """解析用户命令，返回待执行的分析任务."""
        text = msg.content.strip()
        logger.info("Received message from %s: %s", msg.sender_open_id, text)

        reply_to = {
            "open_id": msg.sender_open_id,
            "chat_id": msg.chat_id,
        }

        # 行业命令：行业 光伏 / 板块 半导体 / 产业链 锂电池
        for prefix in ("行业", "板块", "产业链"):
            if text.startswith(prefix):
                rest = text[len(prefix):].strip()
                if rest:
                    return {
                        "action": "industry",
                        "industry": rest,
                        "reply_to": reply_to,
                    }
                return {
                    "action": "reply",
                    "message": "请提供行业名，例如：行业 光伏",
                    "reply_to": reply_to,
                }

        # F3 大盘指数: 大盘 / 大盘 000001 / 大盘 上证 / 指数 399006
        for prefix in ("大盘指数", "大盘", "指数"):
            if text.startswith(prefix):
                rest = text[len(prefix):].strip()
                code = self._resolve_index_code(rest) if rest else "000001"
                if not code:
                    return {
                        "action": "reply",
                        "message": (
                            f"未识别的指数: {rest}\n"
                            f"支持: 上证 / 深证 / 创业板 / 沪深300 / 中证500\n"
                            f"或直接传代码: 大盘 000001"
                        ),
                        "reply_to": reply_to,
                    }
                return {
                    "action": "market",
                    "code": code,
                    "reply_to": reply_to,
                }

        # F4 ETF: ETF 510300 / etf 510300
        if text.lower().startswith("etf"):
            rest = text[3:].strip()
            if rest:
                return {
                    "action": "etf",
                    "code": rest,
                    "reply_to": reply_to,
                }
            return {
                "action": "reply",
                "message": "请提供 ETF 代码，例如：ETF 510300",
                "reply_to": reply_to,
            }

        # 简单命令解析
        if text.isdigit() or (len(text) == 6 and text.isdigit()):
            return {
                "action": "analyze",
                "symbol": text,
                "reply_to": reply_to,
            }

        if text.startswith("分析") or text.startswith("查看"):
            parts = text.split()
            for part in parts:
                if len(part) == 6 and part.isdigit():
                    return {
                        "action": "analyze",
                        "symbol": part,
                        "reply_to": reply_to,
                    }

        return {
            "action": "reply",
            "message": (
                "支持命令：\n"
                "  - 6 位 A 股代码（如 000001）→ 个股分析\n"
                "  - 行业 光伏 / 板块 半导体 → 产业链分析\n"
                "  - 大盘 / 大盘 000001 / 指数 399006 → 大盘指数分析\n"
                "  - ETF 510300 → ETF 技术分析"
            ),
            "reply_to": reply_to,
        }

    @staticmethod
    def _resolve_index_code(name: str) -> str | None:
        """支持代码或常见中文别名."""
        if not name:
            return None
        if name.isdigit() and len(name) == 6:
            return name
        aliases = {
            "上证": "000001",
            "上证指数": "000001",
            "上证综指": "000001",
            "深证": "399001",
            "深证成指": "399001",
            "创业板": "399006",
            "创业板指": "399006",
            "中小板": "399005",
            "上证50": "000016",
            "沪深300": "000300",
            "沪深300指数": "000300",
            "中证500": "000905",
            "中证1000": "000852",
            "北证50": "899050",
        }
        return aliases.get(name)

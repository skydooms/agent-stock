from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    token: str
    expire_at: datetime


class LarkGateway:
    """飞书消息推送 — 支持 Webhook 和 App 模式."""

    def __init__(
        self,
        webhook_url: str = "",
        app_id: str = "",
        app_secret: str = "",
        chat_id: str = "",
        timeout: int = 10,
        retry_count: int = 1,
    ) -> None:
        self.webhook_url = webhook_url
        self.app_id = app_id
        self.app_secret = app_secret
        self.chat_id = chat_id
        self.timeout = timeout
        self.retry_count = retry_count
        self._token_info: TokenInfo | None = None

    async def send_markdown(self, title: str, content: str) -> bool:
        if self.webhook_url:
            return await self._send_webhook(title, content)
        if self.app_id and self.app_secret:
            if not self.chat_id:
                logger.error("Lark App mode requires chat_id. Set LARK_CHAT_ID in .env")
                return False
            return await self._send_app(title, content)
        logger.error("No Lark configuration available")
        return False

    async def _send_webhook(self, title: str, content: str) -> bool:
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": content},
                    }
                ],
            },
        }
        return await self._post(self.webhook_url, payload)

    async def _send_app(self, title: str, content: str) -> bool:
        token = await self._ensure_token()
        if not token:
            return False

        payload = {
            "receive_id": self.chat_id,
            "content": json.dumps(
                {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "lark_md", "content": content},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            "msg_type": "interactive",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        return await self._post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            payload,
            headers=headers,
        )

    async def _ensure_token(self) -> str | None:
        if self._token_info and datetime.now(timezone.utc) < self._token_info.expire_at:
            return self._token_info.token

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    headers={"Content-Type": "application/json"},
                    json={"app_id": self.app_id, "app_secret": self.app_secret},
                ) as resp:
                    if resp.status != 200:
                        logger.error("Lark token request failed: HTTP %d", resp.status)
                        return None
                    data = await resp.json()
                    if data.get("code") != 0:
                        logger.error("Lark token API error: %s", data)
                        return None
                    token = data["tenant_access_token"]
                    expire = data.get("expire", 7200)
                    self._token_info = TokenInfo(
                        token=token,
                        expire_at=datetime.now(timezone.utc) + timedelta(seconds=expire - 60),
                    )
                    logger.debug("Lark token refreshed, expires in %ds", expire)
                    return token
        except Exception as exc:
            logger.error("Lark token request exception: %s", exc)
            return None

    async def _post(self, url: str, payload: dict, headers: dict | None = None) -> bool:
        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)

        last_error = ""
        for attempt in range(self.retry_count + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url,
                        headers=default_headers,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    ) as resp:
                        if resp.status == 200:
                            body = await resp.json()
                            if body.get("code") == 0:
                                logger.info("Lark message sent")
                                return True
                            last_error = f"Lark API error: {body}"
                        elif resp.status == 429:
                            last_error = "Rate limited (429)"
                            await asyncio.sleep(1)
                        elif resp.status >= 500:
                            last_error = f"Server error {resp.status}"
                        else:
                            last_error = f"HTTP {resp.status}"
            except asyncio.TimeoutError:
                last_error = "Timeout"
            except Exception as exc:
                last_error = f"Exception: {exc}"

            if attempt < self.retry_count:
                wait = 1 * (attempt + 1)
                logger.warning(
                    "Lark post failed (attempt %d): %s, retrying in %ds",
                    attempt + 1,
                    last_error,
                    wait,
                )
                await asyncio.sleep(wait)

        logger.error("Lark post failed after %d attempts: %s", self.retry_count + 1, last_error)
        return False

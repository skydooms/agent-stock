from __future__ import annotations

import asyncio
import json
import logging

import aiohttp

logger = logging.getLogger(__name__)


class LarkGateway:
    """飞书自定义机器人 Webhook 推送."""

    def __init__(self, webhook_url: str, timeout: int = 10, retry_count: int = 1) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.retry_count = retry_count

    async def send_markdown(self, title: str, content: str) -> bool:
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
        return await self._post(payload)

    async def _post(self, payload: dict) -> bool:
        last_error = ""
        for attempt in range(self.retry_count + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        self.webhook_url,
                        headers={"Content-Type": "application/json"},
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
                logger.warning("Lark post failed (attempt %d): %s, retrying in %ds", attempt + 1, last_error, wait)
                await asyncio.sleep(wait)

        logger.error("Lark post failed after %d attempts: %s", self.retry_count + 1, last_error)
        return False

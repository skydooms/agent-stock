from __future__ import annotations

import json
import logging
import os

from agent_stock.models import NewsArticle

logger = logging.getLogger(__name__)


class KimiSource:
    """Kimi Code API 新闻源 — 作为 Eastmoney 失效时的备用."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        api_key = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.getenv("ANTHROPIC_BASE_URL", "")
        if not api_key or not base_url:
            return
        try:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=api_key, base_url=base_url)
        except Exception as exc:
            logger.warning("Failed to init Anthropic client for Kimi: %s", exc)

    async def fetch(self, symbol: str, name: str = "", max_articles: int = 10) -> list[NewsArticle]:
        if self._client is None:
            logger.warning("Kimi client not initialized")
            return []

        prompt = self._build_prompt(symbol, name, max_articles)

        try:
            # Anthropic SDK 是同步的，在线程池中运行
            import asyncio

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.messages.create(
                    model="kimi-k2.5",
                    max_tokens=2000,
                    temperature=0.3,
                    system="你是一个财经信息助手。请根据用户请求返回指定格式的 JSON 数据，不要输出任何其他内容。",
                    messages=[{"role": "user", "content": prompt}],
                ),
            )
            content = response.content[0].text
            return self._parse_response(content, symbol)
        except Exception as exc:
            logger.warning("Kimi fetch failed: %s", exc)
            return []

    def _build_prompt(self, symbol: str, name: str, max_articles: int) -> str:
        stock_desc = f"{name}({symbol})" if name else symbol
        return (
            f"请查询股票 {stock_desc} 最近一周的重要财经新闻，"
            f"返回 {max_articles} 条以内的新闻列表。"
            "每条新闻包含：标题、来源、发布时间、摘要。"
            "请严格按以下 JSON 格式返回，不要添加 markdown 代码块标记：\n"
            '{"articles": [{"title": "...", "source": "...", "publish_time": "YYYY-MM-DD HH:MM", "summary": "..."}]}'
        )

    def _parse_response(self, content: str, symbol: str) -> list[NewsArticle]:
        # 去除可能的 markdown 代码块
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as exc:
            logger.warning("Kimi response JSON parse failed: %s", exc)
            return []

        articles = []
        for item in data.get("articles", []):
            try:
                articles.append(
                    NewsArticle(
                        title=str(item.get("title", "")),
                        source=str(item.get("source", "Kimi")),
                        publish_time=str(item.get("publish_time", "")),
                        url="",
                        content=str(item.get("summary", item.get("title", ""))),
                    )
                )
            except Exception as exc:
                logger.debug("Skip malformed Kimi article: %s", exc)
                continue

        logger.info("Kimi returned %d articles for %s", len(articles), symbol)
        return articles

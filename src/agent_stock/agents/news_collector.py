from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from agent_stock.agents.base import BaseAnalyzer
from agent_stock.models import BranchResult, NewsArticle, NewsList
from agent_stock.modules.cache import CacheManager
from agent_stock.modules.news_sources.eastmoney import EastmoneySource
from agent_stock.modules.news_sources.kimi import KimiSource

logger = logging.getLogger(__name__)


class NewsCollector(BaseAnalyzer):
    """新闻采集 Agent — 多源并行获取，合并去重，Eastmoney 失败时回退到 Kimi."""

    def __init__(
        self,
        cache: CacheManager | None = None,
        cache_ttl: int = 14400,
        max_articles: int = 20,
    ) -> None:
        super().__init__("NewsCollector")
        self.cache = cache or CacheManager()
        self.cache_ttl = cache_ttl
        self.max_articles = max_articles
        self.eastmoney = EastmoneySource()
        self.kimi = KimiSource()

    async def analyze(self, symbol: str) -> BranchResult:
        cache_key = f"news:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached is not None:
            self.logger.info("Cache hit for news %s", symbol)
            return self._ok(NewsList(symbol=symbol, articles=[NewsArticle(**a) for a in cached]))

        self.logger.info("Collecting news for %s", symbol)

        try:
            eastmoney_articles = await self._fetch_eastmoney(symbol)
            all_articles = eastmoney_articles

            # Eastmoney 失败时回退到 Kimi
            if not all_articles:
                self.logger.info("Eastmoney empty, falling back to Kimi for %s", symbol)
                kimi_articles = await self.kimi.fetch(symbol, max_articles=self.max_articles)
                all_articles = kimi_articles

            if not all_articles:
                return self._err("所有新闻源均无数据")

            # 去重（按标题）
            seen = set()
            unique = []
            for a in all_articles:
                key = a.title.strip()
                if key and key not in seen:
                    seen.add(key)
                    unique.append(a)

            unique = unique[: self.max_articles]
            news_list = NewsList(symbol=symbol, articles=unique)

            # 写入缓存
            serializable = [
                {
                    "title": a.title,
                    "source": a.source,
                    "publish_time": a.publish_time,
                    "url": a.url,
                    "content": a.content,
                }
                for a in unique
            ]
            await self.cache.set(cache_key, serializable, self.cache_ttl)

            return self._ok(news_list)
        except Exception as exc:
            return self._err(f"新闻采集异常: {exc}")

    async def _fetch_eastmoney(self, symbol: str) -> list[NewsArticle]:
        # Eastmoney 接口是同步的，在线程池中运行
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.eastmoney.fetch, symbol, self.max_articles)

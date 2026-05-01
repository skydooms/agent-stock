from __future__ import annotations

import logging
from datetime import datetime

import akshare as ak

from agent_stock.models import NewsArticle

logger = logging.getLogger(__name__)


class EastmoneySource:
    """东方财富快讯 — 主新闻源."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def fetch(self, symbol: str, max_articles: int = 10) -> list[NewsArticle]:
        """同步获取东财个股新闻."""
        try:
            df = ak.stock_news_em(symbol=symbol)
        except Exception as exc:
            logger.warning("Eastmoney fetch failed for %s: %s", symbol, exc)
            return []

        if df is None or df.empty:
            return []

        articles = []
        for _, row in df.head(max_articles).iterrows():
            try:
                pub_time = str(row.get("发布时间", ""))
                # 标准化时间格式
                if pub_time:
                    try:
                        dt = datetime.strptime(pub_time, "%Y-%m-%d %H:%M:%S")
                        pub_time = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass
                articles.append(
                    NewsArticle(
                        title=str(row.get("新闻标题", "")),
                        source="东方财富",
                        publish_time=pub_time,
                        url=str(row.get("新闻链接", "")),
                        content=str(row.get("新闻内容", row.get("新闻标题", ""))),
                    )
                )
            except Exception as exc:
                logger.debug("Skip malformed row: %s", exc)
                continue

        return articles

from __future__ import annotations

import logging

from agent_stock.agents.base import BaseAnalyzer
from agent_stock.models import BranchResult, Direction, ImpactResult, NewsList
from agent_stock.modules.sentiment import SentimentAnalyzer

logger = logging.getLogger(__name__)


class NewsImpactAnalyzer(BaseAnalyzer):
    """新闻影响评估 Agent — 规则引擎，不依赖 LLM."""

    def __init__(self) -> None:
        super().__init__("NewsImpactAnalyzer")
        self.sentiment = SentimentAnalyzer()

    async def analyze(self, news_list: NewsList) -> BranchResult:
        if not news_list.articles:
            return self._skip("无新闻可分析")

        self.logger.info("Analyzing impact for %s, %d articles", news_list.symbol, len(news_list.articles))

        try:
            directions = []
            strengths = []
            summaries = []

            for article in news_list.articles:
                text = f"{article.title} {article.content}"
                direction, strength, hit = self.sentiment.analyze(text)
                directions.append(direction)
                strengths.append(strength)
                if hit:
                    summaries.append(f"[{article.source}] {article.title}（{hit}）")
                else:
                    summaries.append(f"[{article.source}] {article.title}")

            # 综合方向：多数投票
            pos = sum(1 for d in directions if d == Direction.POSITIVE)
            neg = sum(1 for d in directions if d == Direction.NEGATIVE)
            neu = len(directions) - pos - neg

            if pos > neg and pos > neu:
                overall_direction = Direction.POSITIVE
            elif neg > pos and neg > neu:
                overall_direction = Direction.NEGATIVE
            else:
                overall_direction = Direction.NEUTRAL

            # 综合强度：平均
            overall_strength = int(round(sum(strengths) / len(strengths))) if strengths else 5
            overall_strength = max(1, min(10, overall_strength))

            # 摘要：取前5条
            summary = "；".join(summaries[:5])
            if len(summary) > 200:
                summary = summary[:200] + "..."

            result = ImpactResult(
                symbol=news_list.symbol,
                overall_direction=overall_direction,
                overall_strength=overall_strength,
                articles_analyzed=len(news_list.articles),
                summary=summary,
            )
            return self._ok(result)
        except Exception as exc:
            return self._err(f"影响评估异常: {exc}")

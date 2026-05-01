from __future__ import annotations

import logging

from agent_stock.agents.base import BaseAnalyzer
from agent_stock.models import (
    BranchResult,
    Direction,
    ImpactResult,
    Recommendation,
    StockData,
    TechResult,
)
from agent_stock.modules.indicator_engine import calculate_indicators

logger = logging.getLogger(__name__)


class StockTechAnalyst(BaseAnalyzer):
    """个股技术面分析 + 综合打分 Agent."""

    def __init__(
        self,
        tech_weight: float = 0.7,
        news_weight: float = 0.3,
        buy_threshold: int = 80,
        hold_threshold: int = 50,
    ) -> None:
        super().__init__("StockTechAnalyst")
        self.tech_weight = tech_weight
        self.news_weight = news_weight
        self.buy_threshold = buy_threshold
        self.hold_threshold = hold_threshold

    async def analyze(
        self,
        stock_data: StockData,
        impact: ImpactResult | None = None,
    ) -> BranchResult:
        self.logger.info("Analyzing technicals for %s", stock_data.symbol)

        try:
            df = stock_data.to_dataframe()
            if df.empty or len(df) < 30:
                return self._err(f"数据不足: {len(df)} 条 K 线")

            tech_result = calculate_indicators(df)
            tech_result.symbol = stock_data.symbol

            # 综合评分（若 impact 未就绪则留空，由 Orchestrator 最终计算）
            if impact is not None:
                impact_score = impact.impact_score
                composite = tech_result.tech_score * self.tech_weight + impact_score * self.news_weight
                composite = int(round(composite))
                composite = max(0, min(100, composite))

                if composite >= self.buy_threshold:
                    recommendation = Recommendation.BUY
                elif composite >= self.hold_threshold:
                    recommendation = Recommendation.HOLD
                else:
                    recommendation = Recommendation.SELL
            else:
                composite = tech_result.tech_score
                recommendation = Recommendation.HOLD

            result = {
                "tech": tech_result,
                "impact": impact,
                "composite_score": composite,
                "recommendation": recommendation,
            }
            return self._ok(result)
        except Exception as exc:
            return self._err(f"技术面分析异常: {exc}")

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent_stock.agents.base import BaseAnalyzer
from agent_stock.models import BranchResult, Recommendation, StockData, TechResult
from agent_stock.modules.indicator_engine import FULL_STRATEGIES, calculate_indicators

logger = logging.getLogger(__name__)


class MarketTechAnalyst(BaseAnalyzer):
    """F3/F4 大盘指数 + ETF 技术面分析 Agent (11 策略综合).

    与 StockTechAnalyst 区别:
      - 默认启用 11 策略 (含 MA Cross / Volume / ATR / ADX / OBV / Williams %R / CCI)
      - 不参与新闻舆情综合, 只输出纯技术评分
      - 阈值更严: buy_threshold=75 (个股 80 偏激进)
    """

    def __init__(
        self,
        buy_threshold: int = 75,
        hold_threshold: int = 50,
        template_dir: str | Path | None = None,
    ) -> None:
        super().__init__("MarketTechAnalyst")
        self.buy_threshold = buy_threshold
        self.hold_threshold = hold_threshold
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(),
        )

    async def analyze(self, stock_data: StockData) -> BranchResult:
        self.logger.info("Market analysis: %s (%s)", stock_data.symbol, stock_data.name)
        try:
            df = stock_data.to_dataframe()
            if df.empty or len(df) < 30:
                return self._err(f"数据不足: {len(df)} 条 K 线 (需要至少 30 条)")

            tech = calculate_indicators(df, strategies=FULL_STRATEGIES)
            tech.symbol = stock_data.symbol

            score = tech.tech_score
            if score >= self.buy_threshold:
                rec = Recommendation.BUY
            elif score >= self.hold_threshold:
                rec = Recommendation.HOLD
            else:
                rec = Recommendation.SELL

            return self._ok(
                {
                    "tech": tech,
                    "stock_data": stock_data,
                    "score": score,
                    "recommendation": rec,
                }
            )
        except Exception as exc:
            return self._err(f"市场技术分析异常: {exc}")

    def render(self, payload: dict, kind: str = "index") -> str:
        """渲染 Markdown 报告.

        kind: "index" (F3 大盘) 或 "etf" (F4 ETF), 仅影响标题文案.
        """
        kind_label = "大盘指数" if kind == "index" else "ETF"
        template = self.env.get_template("market_tech_report.md.j2")
        tech: TechResult = payload["tech"]
        stock_data: StockData = payload["stock_data"]
        return template.render(
            kind_label=kind_label,
            symbol=stock_data.symbol,
            name=stock_data.name,
            period=stock_data.period,
            tech=tech,
            indicators=self._format_indicators(tech),
            score=payload["score"],
            recommendation=payload["recommendation"].value,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    @staticmethod
    def _format_indicators(tech: TechResult) -> list[dict]:
        """转换 indicators dict 为模板友好的 list, 标注中文名 + 信号 + 简述."""
        labels = {
            "macd": "MACD 指数平滑异同",
            "kdj": "KDJ 随机指标",
            "rsi": "RSI 相对强弱",
            "bollinger": "布林带 BBands",
            "ma_cross": "MA 5/20 均线",
            "volume": "成交量 vs MA20",
            "atr": "ATR 平均波幅",
            "adx": "ADX 趋势强度",
            "obv": "OBV 能量潮",
            "williams_r": "威廉 %R",
            "cci": "CCI 顺势指标",
        }
        rows: list[dict] = []
        for key, ind in tech.indicators.items():
            rows.append(
                {
                    "key": key,
                    "label": labels.get(key, key),
                    "signal": ind.signal.value if hasattr(ind.signal, "value") else str(ind.signal),
                    "value": ind.value,
                    "note": ind.note,
                }
            )
        return rows

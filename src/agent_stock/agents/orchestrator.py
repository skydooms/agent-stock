from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from agent_stock.agents.news_collector import NewsCollector
from agent_stock.agents.news_impact import NewsImpactAnalyzer
from agent_stock.agents.report_writer import ReportWriter
from agent_stock.agents.stock_tech import StockTechAnalyst
from agent_stock.config import Config
from agent_stock.models import (
    BranchResult,
    ImpactResult,
    KLine,
    NewsList,
    StockData,
)
from agent_stock.modules.cache import CacheManager
from agent_stock.modules.data_fetcher import DataFetcher
from agent_stock.services.lark_gateway import LarkGateway

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    symbol: str
    report_md: str
    tech_score: int
    composite_score: int
    recommendation: str
    news_skipped: bool = False
    lark_ok: bool = False


class Orchestrator:
    """并行调度器 — F2 新闻分支 + F5 技术分支，汇聚后生成报告."""

    def __init__(self, config: Config | None = None, test_mode: bool = False) -> None:
        self.config = config or Config()
        self.test_mode = test_mode
        self.cache = CacheManager()
        self.data_fetcher = DataFetcher(
            cache=self.cache,
            kline_days=self.config.get("data.kline_days", 120),
            cache_ttl=self.config.get("data.cache_ttl_kline", 86400),
        )
        self.news_collector = NewsCollector(
            cache=self.cache,
            cache_ttl=self.config.get("data.cache_ttl_news", 14400),
            max_articles=self.config.get("news.max_articles", 20),
        )
        self.news_impact = NewsImpactAnalyzer()
        self.tech_analyst = StockTechAnalyst(
            tech_weight=self.config.get("scoring.tech_weight", 0.7),
            news_weight=self.config.get("scoring.news_weight", 0.3),
            buy_threshold=self.config.get("scoring.buy_threshold", 80),
            hold_threshold=self.config.get("scoring.hold_threshold", 50),
        )
        self.report_writer = ReportWriter()
        self.lark = None
        if self.config.lark_webhook_url or (self.config.lark_app_id and self.config.lark_app_secret):
            self.lark = LarkGateway(
                webhook_url=self.config.lark_webhook_url,
                app_id=self.config.lark_app_id,
                app_secret=self.config.lark_app_secret,
                chat_id=self.config.lark_chat_id,
                user_email=self.config.lark_user_email,
                user_id=self.config.lark_user_id,
                open_id=self.config.lark_open_id,
                timeout=self.config.get("lark.timeout", 10),
                retry_count=self.config.get("lark.retry_count", 1),
            )

    async def run(self, symbol: str) -> AnalysisResult:
        logger.info("=== Starting analysis for %s ===", symbol)

        # 1. 获取 K 线数据（同步前置，因为技术面必须）
        try:
            stock_data = await self.data_fetcher.fetch(symbol)
        except Exception as exc:
            if self.test_mode:
                logger.warning("AKShare failed in test mode, using synthetic data for %s", symbol)
                stock_data = self._synthetic_stock_data(symbol)
            else:
                logger.error("Data fetch failed for %s: %s", symbol, exc)
                raise

        # 2. 并行分支
        news_timeout = self.config.get("timeouts.news_branch", 30)
        tech_timeout = self.config.get("timeouts.tech_branch", 60)

        news_task = asyncio.create_task(self._news_branch(symbol))
        tech_task = asyncio.create_task(self._tech_branch(stock_data, None))

        # 等待新闻分支（带超时）
        news_result: BranchResult | None = None
        try:
            news_result = await asyncio.wait_for(news_task, timeout=news_timeout)
        except asyncio.TimeoutError:
            logger.warning("News branch timed out after %ds", news_timeout)
            news_task.cancel()
            try:
                await news_task
            except asyncio.CancelledError:
                pass

        # 获取新闻影响结果
        impact: ImpactResult | None = None
        news_list: NewsList | None = None
        news_skipped = True
        if news_result and news_result.success and news_result.data:
            news_list = news_result.data
            impact_result = await self.news_impact.analyze(news_list)
            if impact_result.success and impact_result.data:
                impact = impact_result.data
                news_skipped = False

        # 3. 技术分支（必须完成）
        tech_result = await asyncio.wait_for(tech_task, timeout=tech_timeout)
        if not tech_result.success or tech_result.data is None:
            raise RuntimeError(f"Technical analysis failed: {tech_result.error}")

        tech_data = tech_result.data
        tech_score = tech_data["tech"].tech_score

        # 4. 汇聚 — 综合评分（技术 70% + 新闻 30%）
        impact_score = impact.impact_score if impact else 0
        composite_score = int(round(tech_score * self.tech_analyst.tech_weight + impact_score * self.tech_analyst.news_weight))
        composite_score = max(0, min(100, composite_score))

        if composite_score >= self.tech_analyst.buy_threshold:
            recommendation = "买入"
        elif composite_score >= self.tech_analyst.hold_threshold:
            recommendation = "持有"
        else:
            recommendation = "卖出"

        # 5. 生成报告
        report_result = await self.report_writer.analyze(
            symbol=symbol,
            name=stock_data.name,
            tech_result=tech_data["tech"],
            impact=impact,
            news_list=news_list,
            composite_score=composite_score,
            recommendation=recommendation,
        )

        if not report_result.success or report_result.data is None:
            raise RuntimeError(f"Report generation failed: {report_result.error}")

        report_md = report_result.data

        # 5. 推送 Lark
        lark_ok = False
        if self.lark:
            lark_ok = await self.lark.send_markdown(
                title=f"智投研分析报告 — {stock_data.name} ({symbol})",
                content=report_md,
            )
            if not lark_ok:
                logger.warning("Lark push failed, report saved locally")

        # 本地保留
        self._save_local(report_md, symbol)

        return AnalysisResult(
            symbol=symbol,
            report_md=report_md,
            tech_score=tech_score,
            composite_score=composite_score,
            recommendation=recommendation,
            news_skipped=news_skipped,
            lark_ok=lark_ok,
        )

    async def _news_branch(self, symbol: str) -> BranchResult:
        return await self.news_collector.analyze(symbol)

    async def _tech_branch(self, stock_data: StockData, impact: ImpactResult | None) -> BranchResult:
        return await self.tech_analyst.analyze(stock_data, impact)

    def _synthetic_stock_data(self, symbol: str) -> StockData:
        """生成合成 K 线数据用于测试."""
        from datetime import datetime, timedelta
        import random

        klines = []
        base = datetime.now() - timedelta(days=120)
        close = 10.0
        for i in range(120):
            date = base + timedelta(days=i)
            close += (i % 7 - 3) * 0.05 + random.uniform(-0.1, 0.1)
            close = max(1.0, close)
            klines.append(
                KLine(
                    date=date.strftime("%Y-%m-%d"),
                    open=round(close - 0.05, 2),
                    high=round(close + 0.1, 2),
                    low=round(close - 0.1, 2),
                    close=round(close, 2),
                    volume=int(100000 + i * 500 + random.randint(-10000, 10000)),
                )
            )
        return StockData(
            symbol=symbol,
            name=f"测试-{symbol}",
            period=f"{klines[0].date}~{klines[-1].date}",
            klines=klines,
        )

    def _save_local(self, report_md: str, symbol: str) -> None:
        from datetime import datetime
        from pathlib import Path

        out_dir = Path("reports")
        out_dir.mkdir(exist_ok=True)
        filename = out_dir / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_md)
        logger.info("Report saved to %s", filename)

    async def run_batch(self, symbols: list[str], delay_ms: int = 100) -> list[AnalysisResult]:
        """批量分析，sequential + 间隔避免 Lark 限流."""
        results = []
        for symbol in symbols:
            result = await self.run(symbol)
            results.append(result)
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)
        return results

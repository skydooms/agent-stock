from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent_stock.agents.base import BaseAnalyzer
from agent_stock.models import (
    BranchResult,
    IndustryAnalysis,
    IndustryNode,
    IndustryStock,
)

logger = logging.getLogger(__name__)

SnapshotProvider = Callable[[list[str]], Awaitable[dict[str, dict[str, float]]]]
TIERS = ("upstream", "midstream", "downstream")


class IndustryAnalyst(BaseAnalyzer):
    """F1 行业产业链系统性分析 Agent."""

    def __init__(
        self,
        chains_path: str | Path = "config/industry_chains.yaml",
        template_dir: str | Path | None = None,
        snapshot_provider: SnapshotProvider | None = None,
    ) -> None:
        super().__init__("IndustryAnalyst")
        self.chains_path = Path(chains_path)
        self._chains: dict[str, Any] | None = None
        self.snapshot_provider = snapshot_provider
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(),
        )

    def _load_chains(self) -> dict[str, Any]:
        if self._chains is None:
            if not self.chains_path.exists():
                raise FileNotFoundError(
                    f"行业链配置不存在: {self.chains_path}, 请检查 config/industry_chains.yaml"
                )
            with open(self.chains_path, encoding="utf-8") as f:
                self._chains = yaml.safe_load(f) or {}
        return self._chains

    def list_industries(self) -> list[str]:
        return list(self._load_chains().keys())

    async def analyze(self, industry: str) -> BranchResult:
        try:
            chains = self._load_chains()
        except Exception as exc:
            return self._err(f"加载行业链失败: {exc}")

        if industry not in chains:
            return self._err(
                f"未知行业: {industry}, 可用: {', '.join(chains.keys())}"
            )

        config = chains[industry]
        symbols = self._collect_symbols(config)
        if not symbols:
            return self._err(f"行业 {industry} 没有定义任何股票")

        snapshot = await self._fetch_snapshot(symbols)

        nodes = []
        for tier in TIERS:
            tier_cfg = config.get(tier) or {}
            stocks_cfg = tier_cfg.get("stocks") or []
            stocks: list[IndustryStock] = []
            pcts: list[float] = []
            for entry in stocks_cfg:
                sym = str(entry.get("symbol", "")).strip()
                if not sym:
                    continue
                snap = snapshot.get(sym, {})
                pct = float(snap.get("pct_change", 0.0))
                cap = float(snap.get("market_cap", 0.0))
                stocks.append(
                    IndustryStock(
                        symbol=sym,
                        name=str(entry.get("name", sym)),
                        pct_change=pct,
                        market_cap=cap,
                    )
                )
                pcts.append(pct)
            avg_pct = round(sum(pcts) / len(pcts), 2) if pcts else 0.0
            nodes.append(
                IndustryNode(
                    tier=tier,
                    label=str(tier_cfg.get("label", tier)),
                    stocks=stocks,
                    avg_pct_change=avg_pct,
                    note=self._mood(avg_pct),
                )
            )

        sentiment = self._compute_sentiment(nodes)
        analysis = IndustryAnalysis(
            industry=industry,
            description=str(config.get("description", "")),
            nodes=nodes,
            sentiment_score=sentiment,
            risk_notes=list(config.get("risk_notes") or []),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        return self._ok(analysis)

    def render(self, analysis: IndustryAnalysis) -> str:
        template = self.env.get_template("industry_report.md.j2")
        return template.render(analysis=analysis)

    @staticmethod
    def _collect_symbols(config: dict[str, Any]) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        for tier in TIERS:
            for entry in (config.get(tier) or {}).get("stocks") or []:
                sym = str(entry.get("symbol", "")).strip()
                if sym and sym not in seen:
                    symbols.append(sym)
                    seen.add(sym)
        return symbols

    async def _fetch_snapshot(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        if self.snapshot_provider is not None:
            try:
                return await self.snapshot_provider(symbols)
            except Exception as exc:
                self.logger.warning("自定义 snapshot_provider 失败, 回退默认: %s", exc)

        return await self._akshare_snapshot(symbols)

    async def _akshare_snapshot(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("akshare 未安装, 无法获取行情快照")
            return self._zero_snapshot(symbols)

        loop = asyncio.get_running_loop()
        try:
            df = await loop.run_in_executor(None, ak.stock_zh_a_spot_em)
        except Exception as exc:
            self.logger.warning("AKShare 全市场快照失败: %s, 使用 0 涨跌占位", exc)
            return self._zero_snapshot(symbols)

        if df is None or df.empty:
            return self._zero_snapshot(symbols)

        wanted = set(symbols)
        result: dict[str, dict[str, float]] = {}
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).zfill(6)
            if code not in wanted:
                continue
            try:
                pct = float(row.get("涨跌幅") or 0.0)
            except (TypeError, ValueError):
                pct = 0.0
            try:
                cap = float(row.get("总市值") or 0.0) / 1e8
            except (TypeError, ValueError):
                cap = 0.0
            result[code] = {"pct_change": pct, "market_cap": cap}

        for sym in symbols:
            result.setdefault(sym, {"pct_change": 0.0, "market_cap": 0.0})
        return result

    @staticmethod
    def _zero_snapshot(symbols: list[str]) -> dict[str, dict[str, float]]:
        return {sym: {"pct_change": 0.0, "market_cap": 0.0} for sym in symbols}

    @staticmethod
    def _mood(avg_pct: float) -> str:
        if avg_pct >= 3:
            return f"节点平均 {avg_pct:+.2f}%, 板块强势"
        if avg_pct >= 1:
            return f"节点平均 {avg_pct:+.2f}%, 温和上涨"
        if avg_pct >= -1:
            return f"节点平均 {avg_pct:+.2f}%, 横盘震荡"
        if avg_pct >= -3:
            return f"节点平均 {avg_pct:+.2f}%, 阶段回调"
        return f"节点平均 {avg_pct:+.2f}%, 显著走弱"

    @staticmethod
    def _compute_sentiment(nodes: list[IndustryNode]) -> int:
        if not nodes:
            return 50
        score = 50
        for node in nodes:
            contrib = max(-12, min(12, node.avg_pct_change * 2.5))
            score += contrib
        return max(0, min(100, int(round(score))))

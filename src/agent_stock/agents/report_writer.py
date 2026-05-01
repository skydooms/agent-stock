from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent_stock.agents.base import BaseAnalyzer
from agent_stock.models import BranchResult, ImpactResult, NewsList, TechResult

logger = logging.getLogger(__name__)


class ReportWriter(BaseAnalyzer):
    """Markdown 报告生成 Agent."""

    def __init__(self, template_dir: str | None = None) -> None:
        super().__init__("ReportWriter")
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(),
        )

    async def analyze(
        self,
        symbol: str,
        name: str,
        tech_result: TechResult,
        impact: ImpactResult | None,
        news_list: NewsList | None,
        composite_score: int,
        recommendation: str,
    ) -> BranchResult:
        try:
            template = self.env.get_template("report.md.j2")
            from datetime import datetime
            md = template.render(
                symbol=symbol,
                name=name,
                tech=tech_result,
                impact=impact,
                news=news_list,
                composite_score=composite_score,
                recommendation=recommendation,
                report_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            return self._ok(md)
        except Exception as exc:
            return self._err(f"报告生成异常: {exc}")

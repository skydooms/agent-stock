from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agent_stock.agents.industry_analyst import IndustryAnalyst
from agent_stock.models import IndustryAnalysis, IndustryNode


SAMPLE_YAML = textwrap.dedent(
    """
    测试行业:
      description: "用于单元测试的迷你行业链."
      upstream:
        label: "上游 - 原料"
        stocks:
          - { symbol: "000001", name: "原料一号" }
          - { symbol: "000002", name: "原料二号" }
      midstream:
        label: "中游 - 加工"
        stocks:
          - { symbol: "000003", name: "加工一号" }
      downstream:
        label: "下游 - 终端"
        stocks:
          - { symbol: "000004", name: "终端一号" }
          - { symbol: "000005", name: "终端二号" }
      risk_notes:
        - "测试风险 1"
        - "测试风险 2"
    """
)


@pytest.fixture
def chains_path(tmp_path: Path) -> Path:
    p = tmp_path / "chains.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    return p


@pytest.fixture
def fake_snapshot():
    async def _provider(symbols: list[str]) -> dict[str, dict[str, float]]:
        # 上游平均 +2%, 中游 +0.5%, 下游 -3%
        canned = {
            "000001": {"pct_change": 2.5, "market_cap": 100.0},
            "000002": {"pct_change": 1.5, "market_cap": 50.0},
            "000003": {"pct_change": 0.5, "market_cap": 200.0},
            "000004": {"pct_change": -3.0, "market_cap": 80.0},
            "000005": {"pct_change": -3.0, "market_cap": 120.0},
        }
        return {sym: canned.get(sym, {"pct_change": 0.0, "market_cap": 0.0}) for sym in symbols}

    return _provider


def test_list_industries(chains_path: Path) -> None:
    analyst = IndustryAnalyst(chains_path=chains_path)
    assert analyst.list_industries() == ["测试行业"]


@pytest.mark.asyncio
async def test_analyze_unknown_industry(chains_path: Path) -> None:
    analyst = IndustryAnalyst(chains_path=chains_path)
    result = await analyst.analyze("不存在的行业")
    assert result.success is False
    assert "未知行业" in result.error


@pytest.mark.asyncio
async def test_analyze_with_fake_snapshot(chains_path: Path, fake_snapshot) -> None:
    analyst = IndustryAnalyst(chains_path=chains_path, snapshot_provider=fake_snapshot)
    result = await analyst.analyze("测试行业")
    assert result.success is True

    analysis: IndustryAnalysis = result.data
    assert analysis.industry == "测试行业"
    assert len(analysis.nodes) == 3

    upstream = analysis.nodes[0]
    midstream = analysis.nodes[1]
    downstream = analysis.nodes[2]

    assert upstream.tier == "upstream"
    assert upstream.avg_pct_change == pytest.approx(2.0)
    assert len(upstream.stocks) == 2

    assert midstream.tier == "midstream"
    assert midstream.avg_pct_change == pytest.approx(0.5)

    assert downstream.tier == "downstream"
    assert downstream.avg_pct_change == pytest.approx(-3.0)

    # 景气度: 50 + 2.0*2.5 + 0.5*2.5 + (-3.0)*2.5 = 50 + 5 + 1.25 - 7.5 = 48.75 → 49
    assert 47 <= analysis.sentiment_score <= 51
    assert analysis.risk_notes == ["测试风险 1", "测试风险 2"]


@pytest.mark.asyncio
async def test_render_markdown(chains_path: Path, fake_snapshot) -> None:
    analyst = IndustryAnalyst(chains_path=chains_path, snapshot_provider=fake_snapshot)
    result = await analyst.analyze("测试行业")
    md = analyst.render(result.data)

    assert "# 🏭 行业系统性分析 — 测试行业" in md
    assert "上游 - 原料" in md
    assert "中游 - 加工" in md
    assert "下游 - 终端" in md
    assert "原料一号" in md
    assert "终端二号" in md
    assert "测试风险 1" in md


def test_compute_sentiment_clipping() -> None:
    nodes_extreme_up = [
        IndustryNode(tier="upstream", label="x", avg_pct_change=20.0),
        IndustryNode(tier="midstream", label="x", avg_pct_change=20.0),
        IndustryNode(tier="downstream", label="x", avg_pct_change=20.0),
    ]
    score = IndustryAnalyst._compute_sentiment(nodes_extreme_up)
    assert score == 86  # 50 + 12*3 = 86

    nodes_extreme_down = [
        IndustryNode(tier="upstream", label="x", avg_pct_change=-20.0),
        IndustryNode(tier="midstream", label="x", avg_pct_change=-20.0),
        IndustryNode(tier="downstream", label="x", avg_pct_change=-20.0),
    ]
    score = IndustryAnalyst._compute_sentiment(nodes_extreme_down)
    assert score == 14  # 50 - 12*3 = 14


def test_mood_thresholds() -> None:
    assert "强势" in IndustryAnalyst._mood(5.0)
    assert "温和上涨" in IndustryAnalyst._mood(2.0)
    assert "横盘震荡" in IndustryAnalyst._mood(0.0)
    assert "阶段回调" in IndustryAnalyst._mood(-2.0)
    assert "显著走弱" in IndustryAnalyst._mood(-5.0)

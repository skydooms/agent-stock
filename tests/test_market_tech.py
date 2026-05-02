from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd
import pytest

from agent_stock.agents.market_tech import MarketTechAnalyst
from agent_stock.models import KLine, Signal, StockData
from agent_stock.modules.indicator_engine import (
    DEFAULT_STRATEGIES,
    FULL_STRATEGIES,
    calculate_indicators,
)
from agent_stock.services.lark_events import LarkEventHandler, LarkMessage


def _synth_klines(days: int = 60, slope: float = 0.05) -> list[KLine]:
    """生成可计算所有 11 指标的合成 K 线数据."""
    klines: list[KLine] = []
    base = datetime.now() - timedelta(days=days)
    close = 10.0
    for i in range(days):
        date = base + timedelta(days=i)
        close += slope + 0.3 * math.sin(i / 4)
        close = max(1.0, close)
        klines.append(
            KLine(
                date=date.strftime("%Y-%m-%d"),
                open=round(close - 0.05, 2),
                high=round(close + 0.15, 2),
                low=round(close - 0.15, 2),
                close=round(close, 2),
                volume=int(100000 + i * 800 + (i % 7) * 5000),
            )
        )
    return klines


def _to_df(klines: list[KLine]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": k.date,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
            }
            for k in klines
        ]
    )


def test_calculate_indicators_default_count() -> None:
    """F5 默认 4 策略, 保持向后兼容."""
    df = _to_df(_synth_klines(60))
    result = calculate_indicators(df)
    assert len(result.indicators) == 4
    assert set(result.indicators.keys()) == set(DEFAULT_STRATEGIES)
    assert 0 <= result.tech_score <= 100


def test_calculate_indicators_full_count() -> None:
    """F3/F4 全量 11 策略."""
    df = _to_df(_synth_klines(60))
    result = calculate_indicators(df, strategies=FULL_STRATEGIES)
    assert len(result.indicators) == 11
    assert set(result.indicators.keys()) == set(FULL_STRATEGIES)
    assert 0 <= result.tech_score <= 100


def test_full_strategies_signal_validity() -> None:
    """所有 11 指标应返回合法 Signal (不是 DATA_INSUFFICIENT 应有 value)."""
    df = _to_df(_synth_klines(60))
    result = calculate_indicators(df, strategies=FULL_STRATEGIES)
    for key, ind in result.indicators.items():
        assert isinstance(ind.signal, Signal), f"{key} signal not Signal enum"


@pytest.mark.asyncio
async def test_market_analyze_with_synthetic_data() -> None:
    klines = _synth_klines(60, slope=0.1)
    stock_data = StockData(
        symbol="000001",
        name="上证指数",
        period=f"{klines[0].date}~{klines[-1].date}",
        klines=klines,
    )
    analyst = MarketTechAnalyst()
    result = await analyst.analyze(stock_data)
    assert result.success is True
    payload = result.data
    assert payload["score"] >= 0 and payload["score"] <= 100
    assert payload["recommendation"].value in ("买入", "持有", "卖出")
    assert len(payload["tech"].indicators) == 11


@pytest.mark.asyncio
async def test_market_analyze_data_insufficient() -> None:
    klines = _synth_klines(15)  # 不足 30
    stock_data = StockData(
        symbol="000001",
        name="上证",
        period="x~y",
        klines=klines,
    )
    analyst = MarketTechAnalyst()
    result = await analyst.analyze(stock_data)
    assert result.success is False
    assert "数据不足" in result.error


@pytest.mark.asyncio
async def test_market_render_template() -> None:
    klines = _synth_klines(60)
    stock_data = StockData(
        symbol="510300",
        name="沪深300ETF",
        period=f"{klines[0].date}~{klines[-1].date}",
        klines=klines,
    )
    analyst = MarketTechAnalyst()
    result = await analyst.analyze(stock_data)
    assert result.success
    md_index = analyst.render(result.data, kind="index")
    md_etf = analyst.render(result.data, kind="etf")
    assert "大盘指数技术分析" in md_index
    assert "ETF技术分析" in md_etf
    assert "510300" in md_index
    assert "沪深300ETF" in md_index
    # 验证 11 指标全部出现在模板中
    assert "MACD" in md_index
    assert "MA 5/20 均线" in md_index
    assert "ADX" in md_index
    assert "OBV" in md_index
    assert "威廉" in md_index
    assert "CCI" in md_index


def test_lark_market_command_default() -> None:
    """大盘 (无参数) → 默认上证指数."""
    handler = LarkEventHandler()
    msg = LarkMessage(message_type="text", content="大盘", sender_open_id="u1")
    result = handler._handle_user_message(msg)
    assert result["action"] == "market"
    assert result["code"] == "000001"


def test_lark_market_command_with_code() -> None:
    handler = LarkEventHandler()
    msg = LarkMessage(message_type="text", content="大盘 399006", sender_open_id="u1")
    result = handler._handle_user_message(msg)
    assert result["action"] == "market"
    assert result["code"] == "399006"


def test_lark_market_command_alias() -> None:
    """中文别名 → 代码映射."""
    handler = LarkEventHandler()
    cases = {
        "大盘 上证": "000001",
        "大盘 创业板": "399006",
        "指数 沪深300": "000300",
        "大盘 中证500": "000905",
    }
    for text, expected in cases.items():
        msg = LarkMessage(message_type="text", content=text, sender_open_id="u1")
        result = handler._handle_user_message(msg)
        assert result["action"] == "market", f"{text} not parsed as market"
        assert result["code"] == expected, f"{text} → {result['code']}, expected {expected}"


def test_lark_market_unknown_alias() -> None:
    handler = LarkEventHandler()
    msg = LarkMessage(message_type="text", content="大盘 火星指数", sender_open_id="u1")
    result = handler._handle_user_message(msg)
    assert result["action"] == "reply"
    assert "未识别" in result["message"]


def test_lark_etf_command() -> None:
    handler = LarkEventHandler()
    msg = LarkMessage(message_type="text", content="ETF 510300", sender_open_id="u1")
    result = handler._handle_user_message(msg)
    assert result["action"] == "etf"
    assert result["code"] == "510300"


def test_lark_etf_lowercase() -> None:
    handler = LarkEventHandler()
    msg = LarkMessage(message_type="text", content="etf 159915", sender_open_id="u1")
    result = handler._handle_user_message(msg)
    assert result["action"] == "etf"
    assert result["code"] == "159915"


def test_lark_etf_no_code() -> None:
    handler = LarkEventHandler()
    msg = LarkMessage(message_type="text", content="ETF", sender_open_id="u1")
    result = handler._handle_user_message(msg)
    assert result["action"] == "reply"
    assert "ETF" in result["message"]


def test_resolve_index_code_direct() -> None:
    assert LarkEventHandler._resolve_index_code("000001") == "000001"
    assert LarkEventHandler._resolve_index_code("399006") == "399006"
    assert LarkEventHandler._resolve_index_code("123") is None  # 非 6 位
    assert LarkEventHandler._resolve_index_code("") is None

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Direction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Signal(str, Enum):
    GOLDEN_CROSS = "golden_cross"
    DEAD_CROSS = "dead_cross"
    OVERBOUGHT = "overbought"
    OVERSOLD = "oversold"
    UPPER_TOUCH = "upper_touch"
    LOWER_TOUCH = "lower_touch"
    MIDDLE_BAND = "middle_band"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    BEARISH = "bearish"
    DATA_INSUFFICIENT = "data_insufficient"
    VOLUME_SURGE = "volume_surge"
    VOLUME_SHRINK = "volume_shrink"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TREND_STRONG = "trend_strong"
    TREND_WEAK = "trend_weak"


class Recommendation(str, Enum):
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"


@dataclass(frozen=True)
class KLine:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class StockData:
    symbol: str
    name: str
    period: str
    klines: list[KLine] = field(default_factory=list)

    def to_dataframe(self):
        import pandas as pd

        if not self.klines:
            return pd.DataFrame()
        records = [
            {
                "date": k.date,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
            }
            for k in self.klines
        ]
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        return df


@dataclass(frozen=True)
class NewsArticle:
    title: str
    source: str
    publish_time: str
    url: str
    content: str = ""


@dataclass
class NewsList:
    symbol: str
    articles: list[NewsArticle] = field(default_factory=list)


@dataclass
class IndicatorValue:
    signal: Signal
    value: dict[str, Any] | float | None = None
    note: str = ""


@dataclass
class TechResult:
    symbol: str
    indicators: dict[str, IndicatorValue] = field(default_factory=dict)
    tech_score: int = 50


@dataclass
class ImpactResult:
    symbol: str
    overall_direction: Direction = Direction.NEUTRAL
    overall_strength: int = 5
    articles_analyzed: int = 0
    summary: str = ""

    @property
    def impact_score(self) -> int:
        direction_map = {
            Direction.POSITIVE: 1,
            Direction.NEGATIVE: -1,
            Direction.NEUTRAL: 0,
        }
        return direction_map[self.overall_direction] * self.overall_strength * 2


@dataclass
class BranchResult:
    success: bool
    data: Any | None = None
    error: str = ""
    skipped: bool = False


@dataclass(frozen=True)
class IndustryStock:
    symbol: str
    name: str
    pct_change: float = 0.0
    market_cap: float = 0.0


@dataclass
class IndustryNode:
    tier: str
    label: str
    stocks: list[IndustryStock] = field(default_factory=list)
    avg_pct_change: float = 0.0
    note: str = ""


@dataclass
class IndustryAnalysis:
    industry: str
    description: str = ""
    nodes: list[IndustryNode] = field(default_factory=list)
    sentiment_score: int = 50
    risk_notes: list[str] = field(default_factory=list)
    generated_at: str = ""

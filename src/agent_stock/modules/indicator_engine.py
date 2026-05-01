from __future__ import annotations

import logging

import pandas as pd
import pandas_ta as ta

from agent_stock.models import IndicatorValue, Signal, TechResult

logger = logging.getLogger(__name__)


def _macd_signal(df: pd.DataFrame) -> IndicatorValue:
    try:
        macd = ta.macd(df["close"])
        if macd is None or macd.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        last = macd.iloc[-1]
        prev = macd.iloc[-2] if len(macd) > 1 else last
        val = {
            "macd": round(float(last["MACD_12_26_9"]), 4),
            "signal": round(float(last["MACDs_12_26_9"]), 4),
            "hist": round(float(last["MACDh_12_26_9"]), 4),
        }
        if prev["MACDh_12_26_9"] < 0 and last["MACDh_12_26_9"] >= 0:
            return IndicatorValue(signal=Signal.GOLDEN_CROSS, value=val)
        if prev["MACDh_12_26_9"] > 0 and last["MACDh_12_26_9"] <= 0:
            return IndicatorValue(signal=Signal.DEAD_CROSS, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("MACD calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _kdj_signal(df: pd.DataFrame) -> IndicatorValue:
    try:
        stoch = ta.stoch(df["high"], df["low"], df["close"])
        if stoch is None or stoch.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        last = stoch.iloc[-1]
        k = float(last["STOCHk_14_3_3"])
        d = float(last["STOCHd_14_3_3"])
        j = 3 * k - 2 * d
        val = {"k": round(k, 2), "d": round(d, 2), "j": round(j, 2)}
        if k > 80 and d > 80:
            return IndicatorValue(signal=Signal.OVERBOUGHT, value=val)
        if k < 20 and d < 20:
            return IndicatorValue(signal=Signal.OVERSOLD, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("KDJ calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _rsi_signal(df: pd.DataFrame) -> IndicatorValue:
    try:
        rsi = ta.rsi(df["close"], length=14)
        if rsi is None or rsi.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        val = round(float(rsi.iloc[-1]), 2)
        if val > 70:
            return IndicatorValue(signal=Signal.OVERBOUGHT, value=val)
        if val < 30:
            return IndicatorValue(signal=Signal.OVERSOLD, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("RSI calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _bollinger_signal(df: pd.DataFrame) -> IndicatorValue:
    try:
        bbands = ta.bbands(df["close"], length=20)
        if bbands is None or bbands.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        last = bbands.iloc[-1]
        close = float(df["close"].iloc[-1])
        # pandas-ta 0.4.x 列名格式: BBU_20_2.0_2.0
        upper_col = next((c for c in bbands.columns if c.startswith("BBU_20")), None)
        middle_col = next((c for c in bbands.columns if c.startswith("BBM_20")), None)
        lower_col = next((c for c in bbands.columns if c.startswith("BBL_20")), None)
        if not all([upper_col, middle_col, lower_col]):
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="布林带列名不匹配")
        upper = float(last[upper_col])
        middle = float(last[middle_col])
        lower = float(last[lower_col])
        val = {"upper": round(upper, 2), "middle": round(middle, 2), "lower": round(lower, 2)}
        if close >= upper:
            return IndicatorValue(signal=Signal.UPPER_TOUCH, value=val)
        if close <= lower:
            return IndicatorValue(signal=Signal.LOWER_TOUCH, value=val)
        return IndicatorValue(signal=Signal.MIDDLE_BAND, value=val)
    except Exception as exc:
        logger.warning("Bollinger calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


# 信号到分数映射
SIGNAL_SCORES = {
    Signal.GOLDEN_CROSS: 85,
    Signal.DEAD_CROSS: 35,
    Signal.OVERBOUGHT: 40,
    Signal.OVERSOLD: 80,
    Signal.UPPER_TOUCH: 45,
    Signal.LOWER_TOUCH: 75,
    Signal.MIDDLE_BAND: 60,
    Signal.BULLISH: 80,
    Signal.BEARISH: 30,
    Signal.NEUTRAL: 55,
    Signal.DATA_INSUFFICIENT: 50,
}

WEIGHTS = {
    "macd": 0.30,
    "kdj": 0.25,
    "rsi": 0.25,
    "bollinger": 0.20,
}


def calculate_indicators(df: pd.DataFrame) -> TechResult:
    """计算技术指标并打分."""
    indicators = {
        "macd": _macd_signal(df),
        "kdj": _kdj_signal(df),
        "rsi": _rsi_signal(df),
        "bollinger": _bollinger_signal(df),
    }

    total = 0.0
    total_weight = 0.0
    for key, weight in WEIGHTS.items():
        score = SIGNAL_SCORES.get(indicators[key].signal, 50)
        total += score * weight
        total_weight += weight

    tech_score = int(round(total / total_weight)) if total_weight > 0 else 50
    tech_score = max(0, min(100, tech_score))

    return TechResult(symbol="", indicators=indicators, tech_score=tech_score)

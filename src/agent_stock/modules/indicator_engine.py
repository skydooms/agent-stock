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


def _ma_cross_signal(df: pd.DataFrame) -> IndicatorValue:
    """5/20 日均线金叉死叉."""
    try:
        if len(df) < 25:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        ma5 = df["close"].rolling(5).mean()
        ma20 = df["close"].rolling(20).mean()
        if ma5.iloc[-1] is None or pd.isna(ma5.iloc[-1]) or pd.isna(ma20.iloc[-1]):
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="均线 NaN")
        last_5 = float(ma5.iloc[-1])
        last_20 = float(ma20.iloc[-1])
        prev_5 = float(ma5.iloc[-2]) if not pd.isna(ma5.iloc[-2]) else last_5
        prev_20 = float(ma20.iloc[-2]) if not pd.isna(ma20.iloc[-2]) else last_20
        val = {"ma5": round(last_5, 2), "ma20": round(last_20, 2)}
        if prev_5 <= prev_20 and last_5 > last_20:
            return IndicatorValue(signal=Signal.GOLDEN_CROSS, value=val)
        if prev_5 >= prev_20 and last_5 < last_20:
            return IndicatorValue(signal=Signal.DEAD_CROSS, value=val)
        if last_5 > last_20:
            return IndicatorValue(signal=Signal.BULLISH, value=val)
        if last_5 < last_20:
            return IndicatorValue(signal=Signal.BEARISH, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("MA Cross calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _volume_signal(df: pd.DataFrame) -> IndicatorValue:
    """成交量放大/萎缩信号: vs 20 日均量."""
    try:
        if len(df) < 21:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        vol = df["volume"]
        ma_vol = vol.rolling(20).mean()
        last_vol = float(vol.iloc[-1])
        last_ma = float(ma_vol.iloc[-1])
        if last_ma <= 0:
            return IndicatorValue(signal=Signal.NEUTRAL, note="均量为 0")
        ratio = last_vol / last_ma
        val = {"volume": last_vol, "ma20_volume": round(last_ma, 0), "ratio": round(ratio, 2)}
        if ratio >= 2.0:
            return IndicatorValue(signal=Signal.VOLUME_SURGE, value=val)
        if ratio <= 0.5:
            return IndicatorValue(signal=Signal.VOLUME_SHRINK, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("Volume calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _atr_signal(df: pd.DataFrame) -> IndicatorValue:
    """ATR 平均真实波幅, 用收盘价占比刻画高低波动."""
    try:
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr_series is None or atr_series.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        last_atr = float(atr_series.iloc[-1])
        last_close = float(df["close"].iloc[-1])
        if last_close <= 0:
            return IndicatorValue(signal=Signal.NEUTRAL, note="收盘价为 0")
        pct = last_atr / last_close * 100
        val = {"atr": round(last_atr, 3), "atr_pct": round(pct, 2)}
        if pct >= 4.0:
            return IndicatorValue(signal=Signal.HIGH_VOLATILITY, value=val)
        if pct <= 1.0:
            return IndicatorValue(signal=Signal.LOW_VOLATILITY, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("ATR calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _adx_signal(df: pd.DataFrame) -> IndicatorValue:
    """ADX 趋势强度: >25 强趋势, <20 弱趋势."""
    try:
        adx = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx is None or adx.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        adx_col = next((c for c in adx.columns if c.startswith("ADX")), None)
        dmp_col = next((c for c in adx.columns if c.startswith("DMP")), None)
        dmn_col = next((c for c in adx.columns if c.startswith("DMN")), None)
        if not adx_col:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="ADX 列名不匹配")
        last_adx = float(adx[adx_col].iloc[-1])
        dmp = float(adx[dmp_col].iloc[-1]) if dmp_col else 0.0
        dmn = float(adx[dmn_col].iloc[-1]) if dmn_col else 0.0
        val = {"adx": round(last_adx, 2), "dmp": round(dmp, 2), "dmn": round(dmn, 2)}
        if last_adx >= 25:
            if dmp > dmn:
                return IndicatorValue(signal=Signal.TREND_STRONG, value=val, note="多头趋势")
            return IndicatorValue(signal=Signal.TREND_STRONG, value=val, note="空头趋势")
        if last_adx <= 20:
            return IndicatorValue(signal=Signal.TREND_WEAK, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("ADX calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _obv_signal(df: pd.DataFrame) -> IndicatorValue:
    """OBV 能量潮: 5 日斜率判断方向."""
    try:
        obv_series = ta.obv(df["close"], df["volume"])
        if obv_series is None or obv_series.empty or len(obv_series) < 6:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        recent = obv_series.iloc[-5:]
        slope = float(recent.iloc[-1]) - float(recent.iloc[0])
        val = {"obv": float(obv_series.iloc[-1]), "5d_change": slope}
        # 用相对幅度避免大盘 OBV 量级影响
        base = abs(float(recent.iloc[0])) or 1.0
        rel = slope / base
        if rel > 0.05:
            return IndicatorValue(signal=Signal.BULLISH, value=val)
        if rel < -0.05:
            return IndicatorValue(signal=Signal.BEARISH, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("OBV calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _williams_r_signal(df: pd.DataFrame) -> IndicatorValue:
    """威廉指标 %R: 取值 [-100, 0]; <-80 超卖, >-20 超买."""
    try:
        wr = ta.willr(df["high"], df["low"], df["close"], length=14)
        if wr is None or wr.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        val = round(float(wr.iloc[-1]), 2)
        if val > -20:
            return IndicatorValue(signal=Signal.OVERBOUGHT, value=val)
        if val < -80:
            return IndicatorValue(signal=Signal.OVERSOLD, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("Williams %%R calculation failed: %s", exc)
        return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note=str(exc))


def _cci_signal(df: pd.DataFrame) -> IndicatorValue:
    """CCI 顺势指标: >100 超买, <-100 超卖."""
    try:
        cci = ta.cci(df["high"], df["low"], df["close"], length=14)
        if cci is None or cci.empty:
            return IndicatorValue(signal=Signal.DATA_INSUFFICIENT, note="数据不足")
        val = round(float(cci.iloc[-1]), 2)
        if val > 100:
            return IndicatorValue(signal=Signal.OVERBOUGHT, value=val)
        if val < -100:
            return IndicatorValue(signal=Signal.OVERSOLD, value=val)
        return IndicatorValue(signal=Signal.NEUTRAL, value=val)
    except Exception as exc:
        logger.warning("CCI calculation failed: %s", exc)
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
    Signal.VOLUME_SURGE: 75,
    Signal.VOLUME_SHRINK: 45,
    Signal.HIGH_VOLATILITY: 50,
    Signal.LOW_VOLATILITY: 55,
    Signal.TREND_STRONG: 70,
    Signal.TREND_WEAK: 50,
}

# 默认 4 策略权重 (F5 个股向后兼容)
WEIGHTS = {
    "macd": 0.30,
    "kdj": 0.25,
    "rsi": 0.25,
    "bollinger": 0.20,
}

# 11 策略全集权重 (F3/F4 大盘+ETF)
FULL_WEIGHTS = {
    "macd": 0.15,
    "kdj": 0.10,
    "rsi": 0.10,
    "bollinger": 0.08,
    "ma_cross": 0.15,
    "volume": 0.07,
    "atr": 0.05,
    "adx": 0.10,
    "obv": 0.08,
    "williams_r": 0.06,
    "cci": 0.06,
}

STRATEGY_FUNCS = {
    "macd": _macd_signal,
    "kdj": _kdj_signal,
    "rsi": _rsi_signal,
    "bollinger": _bollinger_signal,
    "ma_cross": _ma_cross_signal,
    "volume": _volume_signal,
    "atr": _atr_signal,
    "adx": _adx_signal,
    "obv": _obv_signal,
    "williams_r": _williams_r_signal,
    "cci": _cci_signal,
}

DEFAULT_STRATEGIES = ("macd", "kdj", "rsi", "bollinger")
FULL_STRATEGIES = (
    "macd", "kdj", "rsi", "bollinger",
    "ma_cross", "volume", "atr", "adx", "obv", "williams_r", "cci",
)


def calculate_indicators(
    df: pd.DataFrame,
    strategies: tuple[str, ...] | list[str] | None = None,
) -> TechResult:
    """计算技术指标并打分.

    strategies: 指标键集合, 默认 DEFAULT_STRATEGIES (4 策略, F5 个股使用).
                传 FULL_STRATEGIES 时启用 11 策略 (F3/F4 大盘 + ETF).
    """
    if strategies is None:
        strategies = DEFAULT_STRATEGIES

    indicators: dict[str, IndicatorValue] = {}
    for key in strategies:
        func = STRATEGY_FUNCS.get(key)
        if func is None:
            logger.warning("未知策略: %s, 跳过", key)
            continue
        indicators[key] = func(df)

    # 选择权重表: 任一策略不在 WEIGHTS 中说明启用了扩展集, 用 FULL_WEIGHTS
    use_full = any(key not in WEIGHTS for key in indicators)
    weights_source = FULL_WEIGHTS if use_full else WEIGHTS
    total = 0.0
    total_weight = 0.0
    for key, ind in indicators.items():
        weight = weights_source.get(key, 0.0)
        if weight == 0.0:
            continue
        score = SIGNAL_SCORES.get(ind.signal, 50)
        total += score * weight
        total_weight += weight

    tech_score = int(round(total / total_weight)) if total_weight > 0 else 50
    tech_score = max(0, min(100, tech_score))

    return TechResult(symbol="", indicators=indicators, tech_score=tech_score)

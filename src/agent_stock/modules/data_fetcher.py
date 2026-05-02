from __future__ import annotations

import logging
from datetime import datetime, timedelta

import akshare as ak

from agent_stock.models import KLine, StockData
from agent_stock.modules.cache import CacheManager

logger = logging.getLogger(__name__)

# AKShare 列名映射标准化
COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "收盘价": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    # 备选列名
    "time": "date",
    "open": "open",
    "close": "close",
    "high": "high",
    "low": "low",
    "volume": "volume",
}


# 常见大盘指数中文名 (F3 用)
INDEX_NAME_MAP = {
    "000001": "上证指数",
    "000300": "沪深300",
    "000905": "中证500",
    "000852": "中证1000",
    "000016": "上证50",
    "399001": "深证成指",
    "399006": "创业板指",
    "399005": "中小板指",
    "899050": "北证50",
}


class DataFetcher:
    """AKShare 数据获取与缓存封装."""

    def __init__(
        self,
        cache: CacheManager | None = None,
        kline_days: int = 120,
        cache_ttl: int = 86400,
    ) -> None:
        self.cache = cache or CacheManager()
        self.kline_days = kline_days
        self.cache_ttl = cache_ttl

    async def fetch(self, symbol: str) -> StockData:
        cache_key = f"kline:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for %s", symbol)
            return self._deserialize(cached)

        logger.info("Fetching K-line for %s from AKShare", symbol)
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=(datetime.now() - timedelta(days=self.kline_days)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )
        except Exception as exc:
            logger.error("AKShare fetch failed for %s: %s", symbol, exc)
            raise DataFetchError(f"AKShare error: {exc}") from exc

        if df is None or df.empty:
            raise DataFetchError(f"No data returned for {symbol}")

        logger.debug("AKShare raw columns: %s", list(df.columns))
        df = self._normalize_columns(df)
        logger.debug("Normalized columns: %s", list(df.columns))
        required = {"date", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise DataFetchError(f"Missing columns: {missing}")

        klines = [
            KLine(
                date=str(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
            for _, row in df.iterrows()
        ]

        name = self._fetch_name(symbol)
        period = f"{klines[0].date}~{klines[-1].date}"
        stock_data = StockData(symbol=symbol, name=name, period=period, klines=klines)

        await self.cache.set(cache_key, self._serialize(stock_data), self.cache_ttl)
        return stock_data

    async def fetch_index(self, code: str) -> StockData:
        """F3 大盘指数日线数据 (代码如 000001 / 399001 / 399006)."""
        cache_key = f"index:{code}"
        cached = await self.cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for index %s", code)
            return self._deserialize(cached)

        logger.info("Fetching index K-line for %s from AKShare", code)
        try:
            df = ak.index_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=(datetime.now() - timedelta(days=self.kline_days)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            )
        except Exception as exc:
            logger.error("AKShare index fetch failed for %s: %s", code, exc)
            raise DataFetchError(f"AKShare index error: {exc}") from exc

        if df is None or df.empty:
            raise DataFetchError(f"No index data returned for {code}")

        df = self._normalize_columns(df)
        klines = self._df_to_klines(df, allow_missing_volume=True)
        if not klines:
            raise DataFetchError(f"Index {code} 无可用 K 线")

        name = INDEX_NAME_MAP.get(code, f"指数{code}")
        period = f"{klines[0].date}~{klines[-1].date}"
        data = StockData(symbol=code, name=name, period=period, klines=klines)
        await self.cache.set(cache_key, self._serialize(data), self.cache_ttl)
        return data

    async def fetch_etf(self, code: str) -> StockData:
        """F4 ETF 日线数据 (代码如 510300 / 510500 / 159915)."""
        cache_key = f"etf:{code}"
        cached = await self.cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for ETF %s", code)
            return self._deserialize(cached)

        logger.info("Fetching ETF K-line for %s from AKShare", code)
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=(datetime.now() - timedelta(days=self.kline_days)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )
        except Exception as exc:
            logger.error("AKShare ETF fetch failed for %s: %s", code, exc)
            raise DataFetchError(f"AKShare ETF error: {exc}") from exc

        if df is None or df.empty:
            raise DataFetchError(f"No ETF data returned for {code}")

        df = self._normalize_columns(df)
        klines = self._df_to_klines(df, allow_missing_volume=False)
        if not klines:
            raise DataFetchError(f"ETF {code} 无可用 K 线")

        name = self._fetch_etf_name(code)
        period = f"{klines[0].date}~{klines[-1].date}"
        data = StockData(symbol=code, name=name, period=period, klines=klines)
        await self.cache.set(cache_key, self._serialize(data), self.cache_ttl)
        return data

    @staticmethod
    def _df_to_klines(df, allow_missing_volume: bool = False) -> list[KLine]:
        required = {"date", "open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise DataFetchError(f"Missing columns: {missing}")
        if "volume" not in df.columns:
            if not allow_missing_volume:
                raise DataFetchError("Missing volume column")
            df = df.copy()
            df["volume"] = 0
        klines: list[KLine] = []
        for _, row in df.iterrows():
            try:
                klines.append(
                    KLine(
                        date=str(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"] or 0),
                    )
                )
            except (TypeError, ValueError):
                continue
        return klines

    def _fetch_etf_name(self, code: str) -> str:
        try:
            df = ak.fund_etf_spot_em()
            if df is None or df.empty:
                return f"ETF{code}"
            for _, row in df.iterrows():
                if str(row.get("代码", "")).strip() == code:
                    return str(row.get("名称", f"ETF{code}"))
        except Exception as exc:
            logger.warning("Failed to fetch ETF name for %s: %s", code, exc)
        return f"ETF{code}"

    def _normalize_columns(self, df):
        rename = {}
        for col in df.columns:
            if col in COLUMN_MAP:
                rename[col] = COLUMN_MAP[col]
        return df.rename(columns=rename)

    def _fetch_name(self, symbol: str) -> str:
        try:
            info = ak.stock_individual_info_em(symbol=symbol)
            if info is not None and not info.empty:
                return str(info.iloc[0].get("股票简称", symbol))
        except Exception as exc:
            logger.warning("Failed to fetch name for %s: %s", symbol, exc)
        return symbol

    def _serialize(self, data: StockData) -> dict:
        return {
            "symbol": data.symbol,
            "name": data.name,
            "period": data.period,
            "klines": [
                {
                    "date": k.date,
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                }
                for k in data.klines
            ],
        }

    def _deserialize(self, payload: dict) -> StockData:
        return StockData(
            symbol=payload["symbol"],
            name=payload["name"],
            period=payload["period"],
            klines=[KLine(**k) for k in payload["klines"]],
        )


class DataFetchError(Exception):
    pass

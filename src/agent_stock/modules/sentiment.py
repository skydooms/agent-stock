from __future__ import annotations

import logging
from pathlib import Path

import yaml

from agent_stock.models import Direction

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = {
    "positive": [
        "增持", "回购", "业绩预增", "净利润增长", "营收增长", "中标", "签约",
        "突破", "创新高", "利好", "政策支持", "补贴", "降准", "降息",
        "外资流入", "机构买入", "评级上调", "目标价上调", "分红", "高送转",
    ],
    "negative": [
        "减持", "亏损", "业绩预亏", "净利润下降", "营收下滑", "暴雷", "退市",
        "监管函", "立案调查", "处罚", "跌停", "破发", "破发潮", "利空",
        "政策收紧", "加息", "外资流出", "机构卖出", "评级下调", "目标价下调",
        "债务违约", "裁员", "停产",
    ],
}


class SentimentAnalyzer:
    """基于规则的情感分析引擎 — pysenti + 关键词词典."""

    def __init__(self, keyword_path: str | Path | None = None) -> None:
        self.keywords = self._load_keywords(keyword_path)
        self._pysenti = None
        try:
            from pysenti import RuleClassifier

            self._pysenti = RuleClassifier()
        except Exception as exc:
            logger.warning("pysenti not available: %s", exc)

    def _load_keywords(self, path: str | Path | None) -> dict[str, list[str]]:
        if path is None:
            return DEFAULT_KEYWORDS
        p = Path(path)
        if not p.exists():
            logger.warning("Keyword file not found: %s, using defaults", path)
            return DEFAULT_KEYWORDS
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "positive" in data and "negative" in data:
                return data
        except Exception as exc:
            logger.warning("Failed to load keyword file: %s", exc)
        return DEFAULT_KEYWORDS

    def analyze(self, text: str) -> tuple[Direction, int, str]:
        """分析单条文本，返回 (方向, 强度1-10, 命中关键词)."""
        text = text.lower()
        pos_hits = [kw for kw in self.keywords["positive"] if kw in text]
        neg_hits = [kw for kw in self.keywords["negative"] if kw in text]

        pos_score = len(pos_hits)
        neg_score = len(neg_hits)

        # pysenti 增强
        if self._pysenti is not None:
            try:
                result = self._pysenti.classify(text)
                # RuleClassifier 返回 {score: float, ...}
                # score > 0 偏正面，score < 0 偏负面
                score = result.get("score", 0.0)
                if score > 0.5:
                    pos_score += score
                elif score < -0.5:
                    neg_score += abs(score)
            except Exception as exc:
                logger.debug("pysenti classify failed: %s", exc)

        if pos_score > neg_score:
            strength = min(10, int(5 + pos_score))
            return Direction.POSITIVE, strength, ",".join(pos_hits[:3]) or "情感正面"
        if neg_score > pos_score:
            strength = min(10, int(5 + neg_score))
            return Direction.NEGATIVE, strength, ",".join(neg_hits[:3]) or "情感负面"
        return Direction.NEUTRAL, 5, "中性"

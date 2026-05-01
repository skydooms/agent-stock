from __future__ import annotations

import abc
import logging
from typing import Any

from agent_stock.models import BranchResult

logger = logging.getLogger(__name__)


class BaseAnalyzer(abc.ABC):
    """Agent 抽象基类 — 所有分析 Agent 必须继承."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abc.abstractmethod
    async def analyze(self, *args: Any, **kwargs: Any) -> BranchResult:
        """执行分析，返回标准化的 BranchResult.

        子类必须内部捕获所有异常，不允许抛出。
        """
        ...

    def _ok(self, data: Any) -> BranchResult:
        return BranchResult(success=True, data=data)

    def _err(self, error: str) -> BranchResult:
        self.logger.warning("%s failed: %s", self.name, error)
        return BranchResult(success=False, error=error)

    def _skip(self, reason: str) -> BranchResult:
        self.logger.info("%s skipped: %s", self.name, reason)
        return BranchResult(success=False, skipped=True, error=reason)

from __future__ import annotations

import os
from pathlib import Path

import yaml


class Config:
    """YAML + 环境变量配置聚合."""

    def __init__(self, path: str | Path = "config.yaml") -> None:
        self._path = Path(path)
        self._data: dict = {}
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}

    def get(self, key: str, default: any = None) -> any:
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    @property
    def lark_webhook_url(self) -> str:
        return os.getenv("LARK_WEBHOOK_URL", self.get("lark.webhook_url", ""))

    @property
    def lark_app_id(self) -> str:
        return os.getenv("LARK_APP_ID", "")

    @property
    def lark_app_secret(self) -> str:
        return os.getenv("LARK_APP_SECRET", "")

    @property
    def serpapi_key(self) -> str:
        return os.getenv("SERPAPI_KEY", "")

    @property
    def tavily_key(self) -> str:
        return os.getenv("TAVILY_KEY", "")

    @property
    def kimi_code_key(self) -> str | None:
        return os.getenv("KIMI_CODE_KEY") or None

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from agent_stock.agents.orchestrator import Orchestrator
from agent_stock.config import Config
from agent_stock.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="智投研 — F2+F5 并行分析流水线")
    parser.add_argument("symbol", help="A股代码，如 000001")
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--debug", action="store_true", help="开启调试日志")
    parser.add_argument("--test-mode", action="store_true", help="测试模式：AKShare 失败时使用合成 K 线数据")
    args = parser.parse_args()

    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)

    config = Config(args.config)
    if not config.lark_webhook_url:
        logger.warning("LARK_WEBHOOK_URL 未设置，报告将仅保存到本地")

    async def _run():
        orch = Orchestrator(config, test_mode=args.test_mode)
        result = await orch.run(args.symbol)
        print(f"\n=== 分析完成 ===")
        print(f"股票: {result.symbol}")
        print(f"技术评分: {result.tech_score}")
        print(f"综合评分: {result.composite_score}")
        print(f"建议: {result.recommendation}")
        if result.news_skipped:
            print("新闻分支: 已跳过")
        print(f"Lark 推送: {'成功' if result.lark_ok else '失败'}")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(1)
    except Exception as exc:
        logger.error("分析失败: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

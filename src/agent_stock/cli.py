from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from agent_stock.agents.orchestrator import Orchestrator
from agent_stock.config import Config
from agent_stock.logging_config import force_utf8_stdio, setup_logging

logger = logging.getLogger(__name__)

SUBCOMMANDS = {"stock", "industry", "market", "etf"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-stock",
        description="智投研 CLI — 个股 / 行业 / 大盘 / ETF 分析",
    )
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--debug", action="store_true", help="开启调试日志")

    subparsers = parser.add_subparsers(dest="cmd")

    stock_p = subparsers.add_parser("stock", help="个股 F2+F5 并行分析")
    stock_p.add_argument("symbol", help="A 股代码，如 000001")
    stock_p.add_argument(
        "--test-mode",
        action="store_true",
        help="测试模式：AKShare 失败时使用合成 K 线数据",
    )

    industry_p = subparsers.add_parser("industry", help="F1 行业产业链系统性分析")
    industry_p.add_argument(
        "name",
        nargs="?",
        default=None,
        help="行业名（如 光伏、半导体），不填则需配合 --list",
    )
    industry_p.add_argument(
        "--list",
        action="store_true",
        help="列出 config/industry_chains.yaml 已配置的所有行业",
    )

    market_p = subparsers.add_parser("market", help="F3 大盘指数技术面分析 (11 策略)")
    market_p.add_argument("code", help="指数代码, 如 000001 (上证) / 399006 (创业板)")

    etf_p = subparsers.add_parser("etf", help="F4 ETF 技术面分析 (11 策略)")
    etf_p.add_argument("code", help="ETF 代码, 如 510300 (沪深300ETF) / 159915 (创业板ETF)")

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """向后兼容: 旧用法 `cli.py 000001 [--test-mode]` 自动注入 `stock` 子命令."""
    cleaned = [a for a in argv if not a.startswith("-")]
    if cleaned and cleaned[0] not in SUBCOMMANDS:
        return ["stock", *argv]
    return argv


def main() -> None:
    force_utf8_stdio()
    parser = _build_parser()
    argv = _normalize_argv(sys.argv[1:])
    args = parser.parse_args(argv)

    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)

    config = Config(args.config)
    cmd = getattr(args, "cmd", None) or "stock"

    try:
        if cmd == "stock":
            _run_stock(args, config)
        elif cmd == "industry":
            _run_industry(args, config)
        elif cmd == "market":
            _run_market(args, config)
        elif cmd == "etf":
            _run_etf(args, config)
        else:
            parser.print_help()
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(1)
    except Exception as exc:
        logger.error("命令执行失败: %s", exc)
        sys.exit(1)


def _run_stock(args: argparse.Namespace, config: Config) -> None:
    if not config.lark_webhook_url and not (config.lark_app_id and config.lark_app_secret):
        logger.warning("Lark 未配置, 报告将仅保存到本地")

    async def _go() -> None:
        orch = Orchestrator(config, test_mode=getattr(args, "test_mode", False))
        result = await orch.run(args.symbol)
        print("\n=== 分析完成 ===")
        print(f"股票: {result.symbol}")
        print(f"技术评分: {result.tech_score}")
        print(f"综合评分: {result.composite_score}")
        print(f"建议: {result.recommendation}")
        if result.news_skipped:
            print("新闻分支: 已跳过")
        print(f"Lark 推送: {'成功' if result.lark_ok else '失败'}")

    asyncio.run(_go())


def _run_industry(args: argparse.Namespace, config: Config) -> None:
    orch = Orchestrator(config)

    if getattr(args, "list", False):
        names = orch.list_industries()
        if not names:
            print("尚未配置任何行业, 请编辑 config/industry_chains.yaml")
            return
        print("可用行业:")
        for n in names:
            print(f"  - {n}")
        return

    if not args.name:
        print("缺少行业名, 用法: agent-stock industry 光伏 或 agent-stock industry --list")
        sys.exit(2)

    async def _go() -> None:
        result = await orch.run_industry(args.name)
        print("\n=== 行业分析完成 ===")
        print(f"行业: {result.industry}")
        print(f"景气度: {result.sentiment_score}/100")
        print(f"产业链节点: {result.node_count}, 覆盖股票: {result.stock_count}")
        print(f"Lark 推送: {'成功' if result.lark_ok else '失败/未配置'}")

    asyncio.run(_go())


def _run_market(args: argparse.Namespace, config: Config) -> None:
    orch = Orchestrator(config)

    async def _go() -> None:
        result = await orch.run_market(args.code)
        print("\n=== 大盘指数分析完成 ===")
        print(f"指数: {result.name} ({result.symbol})")
        print(f"技术评分: {result.tech_score}/100")
        print(f"操作建议: {result.recommendation}")
        print(f"指标数: {result.indicator_count}")
        print(f"Lark 推送: {'成功' if result.lark_ok else '失败/未配置'}")

    asyncio.run(_go())


def _run_etf(args: argparse.Namespace, config: Config) -> None:
    orch = Orchestrator(config)

    async def _go() -> None:
        result = await orch.run_etf(args.code)
        print("\n=== ETF 分析完成 ===")
        print(f"ETF: {result.name} ({result.symbol})")
        print(f"技术评分: {result.tech_score}/100")
        print(f"操作建议: {result.recommendation}")
        print(f"指标数: {result.indicator_count}")
        print(f"Lark 推送: {'成功' if result.lark_ok else '失败/未配置'}")

    asyncio.run(_go())


if __name__ == "__main__":
    main()

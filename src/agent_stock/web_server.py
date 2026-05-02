from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agent_stock.agents.orchestrator import Orchestrator
from agent_stock.config import Config
from agent_stock.logging_config import setup_logging
from agent_stock.services.lark_events import LarkEventHandler
from agent_stock.services.lark_gateway import LarkGateway

logger = logging.getLogger(__name__)

app = FastAPI(title="智投研 — Lark 事件订阅服务")
config = Config()
event_handler = LarkEventHandler(encrypt_key=os.getenv("LARK_ENCRYPT_KEY", ""))
lark = None
orchestrator = None


@app.on_event("startup")
async def startup():
    global lark, orchestrator
    setup_logging()
    if config.lark_app_id and config.lark_app_secret:
        lark = LarkGateway(
            app_id=config.lark_app_id,
            app_secret=config.lark_app_secret,
            user_email=config.lark_user_email,
            user_id=config.lark_user_id,
            open_id=config.lark_open_id,
        )
    orchestrator = Orchestrator(config, test_mode=os.getenv("TEST_MODE", "").lower() == "true")
    logger.info("Web server started")


@app.post("/lark/events")
async def lark_events(
    request: Request,
    x_lark_signature: str | None = Header(None),
    x_lark_timestamp: str | None = Header(None),
    x_lark_nonce: str | None = Header(None),
):
    body = await request.body()
    body_str = body.decode("utf-8")

    # 签名验证（可选，生产环境建议开启）
    if event_handler.encrypt_key and x_lark_signature:
        if not event_handler.verify_signature(
            x_lark_signature, x_lark_timestamp or "", x_lark_nonce or "", body_str
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    result = event_handler.handle_event(payload)

    # URL 验证返回 challenge
    if isinstance(result, dict) and "challenge" in result:
        return JSONResponse(result)

    # 异步处理用户命令，不阻塞 Lark 回调
    if isinstance(result, dict):
        asyncio.create_task(_handle_command(result))

    return JSONResponse({"code": 0})


async def _handle_command(cmd: dict):
    action = cmd.get("action")
    reply_to = cmd.get("reply_to", {})

    if action == "analyze":
        symbol = cmd["symbol"]
        try:
            result = await orchestrator.run(symbol)
            reply_text = (
                f"**{symbol} 分析报告**\n"
                f"技术评分: {result.tech_score}\n"
                f"综合评分: {result.composite_score}\n"
                f"建议: {result.recommendation}\n"
            )
            if result.news_skipped:
                reply_text += "新闻分支: 已跳过\n"
        except Exception as exc:
            logger.error("Analysis failed for %s: %s", symbol, exc)
            reply_text = f"分析 {symbol} 失败: {exc}"

        await _send_reply(reply_text, reply_to)

    elif action == "industry":
        industry = cmd["industry"]
        try:
            result = await orchestrator.run_industry(industry)
            reply_text = (
                f"**行业产业链分析 — {result.industry}**\n"
                f"景气度: {result.sentiment_score}/100\n"
                f"产业链节点: {result.node_count}, 覆盖股票: {result.stock_count}\n"
                f"\n完整报告已推送，详见消息列表。"
            )
        except Exception as exc:
            logger.error("Industry analysis failed for %s: %s", industry, exc)
            available = ", ".join(orchestrator.list_industries()) if orchestrator else ""
            if available:
                reply_text = f"行业 {industry} 分析失败: {exc}\n可用行业: {available}"
            else:
                reply_text = f"行业 {industry} 分析失败: {exc}"

        await _send_reply(reply_text, reply_to)

    elif action == "market":
        code = cmd["code"]
        try:
            result = await orchestrator.run_market(code)
            reply_text = (
                f"**大盘指数技术分析 — {result.name} ({result.symbol})**\n"
                f"技术评分: {result.tech_score}/100\n"
                f"操作建议: {result.recommendation}\n"
                f"指标数: {result.indicator_count}\n"
                f"\n完整报告已推送, 详见消息列表."
            )
        except Exception as exc:
            logger.error("Market analysis failed for %s: %s", code, exc)
            reply_text = f"大盘指数 {code} 分析失败: {exc}"

        await _send_reply(reply_text, reply_to)

    elif action == "etf":
        code = cmd["code"]
        try:
            result = await orchestrator.run_etf(code)
            reply_text = (
                f"**ETF 技术分析 — {result.name} ({result.symbol})**\n"
                f"技术评分: {result.tech_score}/100\n"
                f"操作建议: {result.recommendation}\n"
                f"指标数: {result.indicator_count}\n"
                f"\n完整报告已推送, 详见消息列表."
            )
        except Exception as exc:
            logger.error("ETF analysis failed for %s: %s", code, exc)
            reply_text = f"ETF {code} 分析失败: {exc}"

        await _send_reply(reply_text, reply_to)

    elif action == "reply":
        await _send_reply(cmd["message"], reply_to)


async def _send_reply(text: str, reply_to: dict):
    if not lark:
        logger.warning("Lark gateway not initialized, skipping reply")
        return

    # 动态设置接收者并发送
    chat_id = reply_to.get("chat_id")
    open_id = reply_to.get("open_id")

    if chat_id:
        lark.chat_id = chat_id
        lark.open_id = ""
    elif open_id:
        lark.open_id = open_id
        lark.chat_id = ""
    else:
        logger.warning("No receiver specified for reply")
        return

    await lark.send_markdown("智投研", text)


def main() -> None:
    import uvicorn

    setup_logging()
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("agent_stock.web_server:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

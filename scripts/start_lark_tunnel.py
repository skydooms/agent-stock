"""一键启动 ngrok + Lark 事件订阅服务."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

NGROK_API = "http://localhost:4040/api/tunnels"
WEB_PORT = 8000


def find_ngrok() -> str | None:
    """查找 ngrok 可执行文件."""
    for name in ("ngrok", "ngrok.exe"):
        # 先检查 PATH
        try:
            result = subprocess.run(
                [name, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return name
        except FileNotFoundError:
            pass
    return None


def get_ngrok_url(timeout: int = 30) -> str | None:
    """从 ngrok 本地 API 获取公网 URL."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(NGROK_API, timeout=2) as resp:
                data = json.loads(resp.read())
                for tunnel in data.get("tunnels", []):
                    url = tunnel.get("public_url", "")
                    if url.startswith("https://"):
                        return url
        except Exception:
            pass
        time.sleep(1)
    return None


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    ngrok_cmd = find_ngrok()
    if not ngrok_cmd:
        print("错误：未找到 ngrok。请先安装：https://ngrok.com/download")
        print("安装后运行：ngrok config add-authtoken <你的token>")
        sys.exit(1)

    print(f"正在启动 ngrok (端口 {WEB_PORT})...")
    ngrok_proc = subprocess.Popen(
        [ngrok_cmd, "http", str(WEB_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def cleanup(*args):
        print("\n正在关闭 ngrok...")
        ngrok_proc.terminate()
        try:
            ngrok_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ngrok_proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("等待 ngrok 隧道建立...")
    public_url = get_ngrok_url()
    if not public_url:
        print("错误：ngrok 隧道未能建立")
        cleanup()

    webhook_url = f"{public_url}/lark/events"

    print("\n" + "=" * 60)
    print(f"公网地址: {webhook_url}")
    print("=" * 60)
    print("请复制上方地址到飞书开发者后台 → 事件订阅 → 请求地址")
    print("按 Ctrl+C 停止服务\n")

    # 启动 Web 服务
    from agent_stock.web_server import main as web_main

    web_main()


if __name__ == "__main__":
    main()

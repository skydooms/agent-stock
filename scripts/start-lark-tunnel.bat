@echo off
chcp 65001 >nul
echo 正在启动 Lark 事件订阅隧道服务...
python -m scripts.start_lark_tunnel
pause

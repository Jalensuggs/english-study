#!/bin/zsh
# 双击这个文件就能启动英语学习网站（关掉这个终端窗口网站就停了）
cd "$(dirname "$0")"
if lsof -i :8848 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "网站已经在运行了"
else
  python3 server.py &
  sleep 1
fi
open "http://localhost:8848"
wait

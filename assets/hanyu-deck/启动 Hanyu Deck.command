#!/bin/zsh
# 启动 Hanyu Deck 的本地高级功能。关闭窗口或按 Ctrl+C 即停止。
set -u
cd "$(dirname "$0")"

if /usr/bin/lsof -nP -iTCP:8123 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 8123 已被占用。请先关闭旧的 Hanyu Deck 服务窗口。"
  read -k 1 "?按任意键退出。"
  exit 1
fi

if [ -x "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" ]; then
  "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" scripts/prompter_server.py
else
  /usr/bin/python3 scripts/prompter_server.py
fi

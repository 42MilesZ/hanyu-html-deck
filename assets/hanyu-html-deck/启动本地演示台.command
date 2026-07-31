#!/bin/zsh
# 启动本地演示台的高级功能（手机提词、写回、导出）。关闭窗口或按 Ctrl+C 即停止。
set -u
cd "$(dirname "$0")"

PORT="${HANYU_DECK_PORT:-8123}"

if /usr/bin/lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用。请先关闭旧的服务窗口，或设置 HANYU_DECK_PORT 换一个端口。"
  read -k 1 "?按任意键退出。"
  exit 1
fi

PY="$(command -v python3 || true)"
if [ ! -x "${PY:-}" ]; then
  PY="/usr/bin/python3"
fi
if [ ! -x "$PY" ]; then
  echo "没找到 python3。安装 Python 3 后再双击本文件。"
  read -k 1 "?按任意键退出。"
  exit 1
fi

"$PY" scripts/prompter_server.py
status=$?
if [ $status -ne 0 ]; then
  echo "服务异常退出（退出码 $status）。"
  read -k 1 "?按任意键退出。"
fi

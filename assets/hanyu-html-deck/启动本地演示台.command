#!/bin/zsh
# 启动本地演示台的高级功能（手机提词、写回、导出），并打开演示稿。
# 关闭窗口或按 Ctrl+C 即停止。
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

if [ -f "index.html" ]; then
  # 写回凭据由服务写进 index.html。必须等服务开始应答再打开页面,
  # 否则页面读到的是上一次运行留下的空值,写回会被拒。
  # --noproxy:curl 只认环境变量里的代理(不读 macOS 系统设置)。环境里漏进
  # http_proxy 时,回环探测会被代理接手,可能在凭据写好前就返回成功。
  (
    for _ in $(seq 1 60); do
      if /usr/bin/curl -s -o /dev/null -m 1 --noproxy '*' "http://127.0.0.1:$PORT/" ; then break; fi
      sleep 0.25
    done
    /usr/bin/open "$PWD/index.html"
  ) &
  echo "正在打开演示稿：index.html"
else
  echo "这个目录里没有 index.html，只启动服务。"
fi

"$PY" scripts/prompter_server.py
status=$?
if [ $status -ne 0 ]; then
  echo "服务异常退出（退出码 $status）。"
  read -k 1 "?按任意键退出。"
fi

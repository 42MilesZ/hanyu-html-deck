#!/usr/bin/env python3
"""从仓库内的模板资产创建一个独立演示稿目录。"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "hanyu-html-deck"
# 资产目录本身可运行,会留下运行状态与导出中间物,这些不该跟着新演示稿走
JUNK = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".DS_Store", ".prompter-*", "发送版.html", "导出图片",
    "图片版.pdf", "图文讲稿.pdf"
)
TOKEN_LINE_RE = re.compile(r"(var TOKEN = ')([^']*)('; /\* HANYU_TOKEN \*/)")
TOP_LEVEL_EXCLUDES = {
    "AGENTS.md", "deck-content.json", "发送版.html", "导出图片", "图片版.pdf", "图文讲稿.pdf"
}


def create(target: pathlib.Path):
    if target.exists() and any(target.iterdir()):
        raise SystemExit("目标目录不是空目录：%s" % target)
    target.mkdir(parents=True, exist_ok=True)
    for item in SOURCE.iterdir():
        if item.name.startswith(".prompter-") or item.name in TOP_LEVEL_EXCLUDES:
            continue
        if item.is_dir():
            shutil.copytree(item, target / item.name, ignore=JUNK)
        else:
            shutil.copy2(item, target / item.name)
    deck = target / "index.html"
    # 模板此刻可能正被本地服务占用,行内带着本机写回凭据:带走它会把新稿的改动写回模板
    deck.write_text(
        TOKEN_LINE_RE.sub(r"\g<1>\g<3>", deck.read_text(encoding="utf-8")), encoding="utf-8"
    )
    # 生成目录是本软件的副本，MIT 许可声明必须随副本保留。
    shutil.copy2(ROOT / "LICENSE", target / "LICENSE")
    subprocess.run(
        [sys.executable, str(target / "scripts" / "deck_content.py"), "--root", str(target), "init"],
        check=True,
    )
    print("已创建本地演示台演示稿：%s" % target)
    print("打开 index.html 可离线使用；双击“启动本地演示台.command”启用高级功能。")


def main():
    parser = argparse.ArgumentParser(description="创建本地演示台演示稿")
    parser.add_argument("target", type=pathlib.Path)
    args = parser.parse_args()
    if not SOURCE.exists():
        sys.exit("模板资产不存在：%s" % SOURCE)
    create(args.target.expanduser().resolve())


if __name__ == "__main__":
    main()

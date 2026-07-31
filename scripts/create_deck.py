#!/usr/bin/env python3
"""从仓库内的模板资产创建一个独立演示稿目录。"""

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "hanyu-html-deck"
JUNK = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def create(target: pathlib.Path):
    if target.exists() and any(target.iterdir()):
        raise SystemExit("目标目录不是空目录：%s" % target)
    target.mkdir(parents=True, exist_ok=True)
    for item in SOURCE.iterdir():
        if item.name == "template.html":
            shutil.copy2(item, target / "index.html")
        elif item.is_dir():
            shutil.copytree(item, target / item.name, ignore=JUNK)
        else:
            shutil.copy2(item, target / item.name)
    shutil.copy2(ROOT / "assets" / "deck-readme.md", target / "README.md")
    # 生成目录会被整体转发,必须自带许可与第三方声明
    shutil.copy2(ROOT / "LICENSE", target / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", target / "THIRD_PARTY_NOTICES.md")
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


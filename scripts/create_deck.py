#!/usr/bin/env python3
"""从仓库内的 Hanyu Deck 资产创建一个独立演示稿目录。"""

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "hanyu-deck"


def create(target: pathlib.Path):
    if target.exists() and any(target.iterdir()):
        raise SystemExit("目标目录不是空目录：%s" % target)
    target.mkdir(parents=True, exist_ok=True)
    for item in SOURCE.iterdir():
        if item.name == "template.html":
            shutil.copy2(item, target / "index.html")
        elif item.is_dir():
            shutil.copytree(item, target / item.name)
        else:
            shutil.copy2(item, target / item.name)
    shutil.copy2(ROOT / "assets" / "deck-readme.md", target / "README.md")
    print("已创建 Hanyu Deck：%s" % target)
    print("打开 index.html 可离线使用；双击“启动 Hanyu Deck.command”启用高级功能。")


def main():
    parser = argparse.ArgumentParser(description="创建 Hanyu Deck 演示稿")
    parser.add_argument("target", type=pathlib.Path)
    args = parser.parse_args()
    if not SOURCE.exists():
        sys.exit("模板资产不存在：%s" % SOURCE)
    create(args.target.expanduser().resolve())


if __name__ == "__main__":
    main()


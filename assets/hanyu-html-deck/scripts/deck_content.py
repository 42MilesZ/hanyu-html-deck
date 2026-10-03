#!/usr/bin/env python3
"""Hanyu HTML Deck 的讲稿/备注内容仓与 AI 写入命令。

index.html 保留可离线阅读的种子；deck-content.json 是编辑态真源。浏览器和 AI
都通过 prompter_server.py 写入，避免直接改同一份 HTML 时互相覆盖。
"""

import argparse
import html
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.request


SCHEMA_VERSION = 1
FIELDS = ("script", "note")
SELECTORS = {"script": "ns", "note": "nc"}
SECTION_RE = re.compile(r'<section\b(?=[^>]*\bclass="[^"]*\bslide\b[^"]*")[^>]*>')
TOKEN_RE = re.compile(r"var TOKEN = '([^']*)'; /\* HANYU_TOKEN \*/")


class ContentConflict(Exception):
    pass


def _attr(tag, name):
    match = re.search(r'\b%s="([^"]*)"' % re.escape(name), tag)
    return html.unescape(match.group(1)) if match else ""


def _find_div_inner(document, selector, start, end):
    opening = re.search(
        r'<div\b(?=[^>]*\bclass="[^"]*\b%s\b[^"]*")[^>]*>' % re.escape(selector),
        document[start:end],
    )
    if not opening:
        return None
    inner_start = start + opening.end()
    depth = 1
    for match in re.finditer(r"<div\b|</div>", document[inner_start:end]):
        depth += 1 if match.group(0).startswith("<div") else -1
        if depth == 0:
            return inner_start, inner_start + match.start()
    raise ValueError(".%s 区块的 div 开闭不配平" % selector)


def extract_slides(document):
    sections = list(SECTION_RE.finditer(document))
    slides = []
    for index, section in enumerate(sections):
        start = section.end()
        end = sections[index + 1].start() if index + 1 < len(sections) else len(document)
        slide_id = _attr(section.group(0), "data-slide-id")
        if not slide_id:
            raise ValueError("每页必须设置 data-slide-id")
        record = {"id": slide_id, "title": _attr(section.group(0), "data-title")}
        for field, selector in SELECTORS.items():
            found = _find_div_inner(document, selector, start, end)
            record[field] = document[found[0] : found[1]] if found else ""
        slides.append(record)
    return slides


def _new_store(document):
    slides = extract_slides(document)
    slide_ids = [slide["id"] for slide in slides]
    if len(slide_ids) != len(set(slide_ids)):
        raise ValueError("data-slide-id 必须唯一")
    return {
        "version": SCHEMA_VERSION,
        "revision": 0,
        "order": slide_ids,
        "slides": {
            slide["id"]: {
                "title": slide["title"],
                "script": {"html": slide["script"], "revision": 0},
                "note": {"html": slide["note"], "revision": 0},
            }
            for slide in slides
        },
    }


def read_store(content_path):
    path = pathlib.Path(content_path)
    with path.open(encoding="utf-8") as handle:
        store = json.load(handle)
    if store.get("version") != SCHEMA_VERSION or not isinstance(store.get("slides"), dict):
        raise ValueError("不支持的 deck-content.json 结构")
    return store


def write_store(content_path, store):
    path = pathlib.Path(content_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(store, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_store(index_path, content_path, *, persist=True):
    """合并当前种子与已保存修订；导出用 persist=False，避免修改源稿。"""
    index_path = pathlib.Path(index_path)
    document = index_path.read_text(encoding="utf-8")
    seeds = _new_store(document)
    path = pathlib.Path(content_path)
    if not path.exists():
        if persist:
            write_store(path, seeds)
        return seeds
    store = read_store(path)
    changed = False
    for slide_id in seeds["order"]:
        seed = seeds["slides"][slide_id]
        if slide_id not in store["slides"]:
            store["slides"][slide_id] = seed
            changed = True
        else:
            existing = store["slides"][slide_id]
            if existing.get("title") != seed["title"]:
                existing["title"] = seed["title"]
                changed = True
            # revision=0 表示尚未进入协作写入阶段。此时 AI 仍可先在 HTML 中生成
            # 初稿；第一次启动服务会吸收这些新种子。正式写入过的字段绝不被覆盖。
            for field in FIELDS:
                current = existing.get(field, {})
                if int(current.get("revision", 0)) == 0 and current.get("html") != seed[field]["html"]:
                    existing[field] = seed[field]
                    changed = True
    if store.get("order") != seeds["order"]:
        store["order"] = seeds["order"]
        changed = True
    if changed and persist:
        write_store(path, store)
    return store


def patch_store(content_path, slide_id, field, value, base_revision):
    if field not in FIELDS:
        raise ValueError("field 必须是 script 或 note")
    store = read_store(content_path)
    if slide_id not in store["slides"]:
        raise KeyError("找不到页面 %s" % slide_id)
    current = store["slides"][slide_id][field]
    if int(base_revision) != int(current.get("revision", 0)):
        raise ContentConflict("内容已更新，请重新读取后再修改")
    store["revision"] = int(store.get("revision", 0)) + 1
    current["html"] = value
    current["revision"] = store["revision"]
    write_store(content_path, store)
    return store, current


def hydrate_html(document, store):
    sections = list(SECTION_RE.finditer(document))
    replacements = []
    for index, section in enumerate(sections):
        start = section.end()
        end = sections[index + 1].start() if index + 1 < len(sections) else len(document)
        slide_id = _attr(section.group(0), "data-slide-id")
        if not slide_id:
            raise ValueError("每页必须设置 data-slide-id")
        slide = store.get("slides", {}).get(slide_id)
        if not slide:
            continue
        for field, selector in SELECTORS.items():
            found = _find_div_inner(document, selector, start, end)
            if found:
                replacements.append((found[0], found[1], slide[field]["html"]))
    for start, end, value in sorted(replacements, reverse=True):
        document = document[:start] + value + document[end:]
    return document


def _server_url(args, path):
    root = pathlib.Path(args.root).resolve()
    index_path = root / "index.html"
    token_match = TOKEN_RE.search(index_path.read_text(encoding="utf-8"))
    token = token_match.group(1) if token_match else ""
    if not token:
        raise SystemExit("本地演示台未连接：先运行“启动本地演示台.command”")
    return "http://127.0.0.1:%d%s?t=%s" % (args.port, path, token)


def _server_show(args):
    request = urllib.request.Request(_server_url(args, "/content"))
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise SystemExit("读取失败（HTTP %d）：%s" % (error.code, detail))
    except urllib.error.URLError as error:
        raise SystemExit("本地演示台未连接：%s" % error.reason)


def _server_patch(args):
    value = pathlib.Path(args.value_file).read_text(encoding="utf-8")
    payload = json.dumps(
        {
            "slideId": args.slide_id,
            "field": args.field,
            "html": value,
            "baseRevision": args.base_revision,
            "owner": args.owner,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        _server_url(args, "/content/patch"), data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise SystemExit("写入失败（HTTP %d）：%s" % (error.code, detail))
    except urllib.error.URLError as error:
        raise SystemExit("本地演示台未连接：%s" % error.reason)


def main():
    parser = argparse.ArgumentParser(description="读取或安全修改 Hanyu HTML Deck 的讲稿/备注")
    parser.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    show = sub.add_parser("show")
    show.add_argument("--port", type=int, default=8123)
    patch = sub.add_parser("patch")
    patch.add_argument("--slide-id", required=True)
    patch.add_argument("--field", choices=FIELDS, required=True)
    patch.add_argument("--base-revision", type=int, required=True)
    patch.add_argument("--value-file", required=True)
    patch.add_argument("--owner", default="ai-cli")
    patch.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    content_path = root / "deck-content.json"
    if args.command == "init":
        store = ensure_store(root / "index.html", content_path)
        print("已初始化 %d 页内容仓" % len(store["order"]))
    elif args.command == "show":
        # 与 patch 共用服务端单写者边界；/content 会在 content_lock 内核对当前 HTML。
        store = _server_show(args)
        json.dump(store, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        _server_patch(args)


if __name__ == "__main__":
    main()

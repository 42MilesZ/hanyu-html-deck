#!/usr/bin/env python3
"""Hanyu Deck 本地服务。

只在当前局域网内提供手机提词、遥控、源文件写回与导出调度。
不连接公共中继，不上传讲稿，不依赖外部网络。
"""

import hashlib
import io
import json
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX_FILE = os.path.join(ROOT, "index.html")
PHONE_FILE = os.path.join(HERE, "prompter-phone.html")
NOTES_FILE = os.path.join(HERE, ".prompter-notes.json")
STATE_FILE = os.path.join(HERE, ".prompter-state.json")
PAGES_DIR = os.path.join(ROOT, "导出图片")
THUMB_DIR = os.path.join(HERE, ".prompter-thumbs")
STEPS_DIR = os.path.join(HERE, ".prompter-steps")
PORT = int(os.environ.get("HANYU_DECK_PORT") or 8123)

sys.path.insert(0, os.path.join(HERE, "vendor"))
import qrcode  # noqa: E402
import qrcode.image.svg  # noqa: E402

state = {"seq": int(time.time()), "page": 1, "step": 0, "steps": 0, "nv": ""}
notes = None
lock = threading.Lock()
seed_lock = threading.Lock()
sse_clients = []
phone_seen = {}
export_busy = False


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def broadcast(event, value):
    message = "event: %s\ndata: %s\n\n" % (
        event,
        json.dumps(value, ensure_ascii=False),
    )
    for client in list(sse_clients):
        try:
            client.put_nowait(message)
        except queue.Full:
            pass


def local_ips():
    """返回手机可访问的 IPv4，排除回环、代理 TUN 与链路本地地址。"""
    found = []
    try:
        host = socket.gethostname()
        for item in socket.getaddrinfo(host, None, socket.AF_INET):
            found.append(item[4][0])
    except OSError:
        pass
    if sys.platform == "darwin":
        try:
            output = subprocess.run(
                ["ifconfig"], capture_output=True, text=True, timeout=3
            ).stdout
            found.extend(re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", output))
        except Exception:
            pass
    blocked = ("127.", "169.254.", "198.18.", "198.19.")
    return sorted({ip for ip in found if ip and not ip.startswith(blocked)})


def phone_urls():
    return ["http://%s:%d/p" % (ip, PORT) for ip in local_ips()]


def preferred_url(urls):
    hotspot = [url for url in urls if "//172.20.10." in url]
    return (hotspot or urls or [""])[0]


def save_state():
    with lock:
        snapshot = {key: state[key] for key in ("page", "step", "steps")}
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle)
    os.replace(tmp, STATE_FILE)


def page_sources():
    result = {}
    if not os.path.isdir(PAGES_DIR):
        return result
    for name in os.listdir(PAGES_DIR):
        match = re.match(r"^(\d+)-.*\.png$", name)
        if not match:
            continue
        number = int(match.group(1))
        path = os.path.join(PAGES_DIR, name)
        if number not in result or os.path.getmtime(path) > os.path.getmtime(result[number]):
            result[number] = path
    return result


def thumb_path(number):
    source = page_sources().get(number)
    if not source:
        return None
    os.makedirs(THUMB_DIR, exist_ok=True)
    target = os.path.join(THUMB_DIR, "%02d.jpg" % number)
    if not os.path.exists(target) or os.path.getmtime(target) < os.path.getmtime(source):
        subprocess.run(
            [
                "sips",
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                "70",
                "-Z",
                "640",
                source,
                "--out",
                target,
            ],
            capture_output=True,
        )
    return target if os.path.exists(target) else None


def sync_notes_page(page, fragment, selector):
    global notes
    field = "html" if selector == "ns" else "comm"
    with lock:
        pages = (notes or {}).get("pages") or []
        if page > len(pages):
            return
        pages[page - 1][field] = fragment
        raw = json.dumps(notes, ensure_ascii=False)
        state["nv"] = hashlib.md5(raw.encode()).hexdigest()[:8]
        state["seq"] += 1
        snapshot = dict(state)
    with open(NOTES_FILE, "w", encoding="utf-8") as handle:
        handle.write(raw)
    broadcast("notes", {"nv": snapshot["nv"]})
    broadcast("state", snapshot)


def save_seed(page, fragment, selector):
    with seed_lock:
        with open(INDEX_FILE, encoding="utf-8") as handle:
            document = handle.read()
        blocks = list(
            re.finditer(r'<div class="%s">.*?</div>' % selector, document, re.S)
        )
        if page > len(blocks):
            return False, "文件里没有第 %d 页的 %s 区域" % (page, selector)
        match = blocks[page - 1]
        replacement = '<div class="%s">%s</div>' % (selector, fragment)
        document = document[: match.start()] + replacement + document[match.end() :]
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(document)
        os.replace(tmp, INDEX_FILE)
    return True, ""


def save_canvas(page, fragment, dom_total):
    with seed_lock:
        with open(INDEX_FILE, encoding="utf-8") as handle:
            document = handle.read()
        sections = list(re.finditer(r'<section class="slide"[\s>]', document))
        if dom_total and dom_total != len(sections):
            return False, "源文件页数已变化，请刷新后再修改"
        if page < 1 or page > len(sections):
            return False, "页码不在源文件范围内"
        start = sections[page - 1].start()
        end = sections[page].start() if page < len(sections) else len(document)
        opening = re.search(r'<div class="canvas[^>]*>', document[start:end])
        if not opening:
            return False, "没有找到本页画布"
        content_start = start + opening.end()
        closing = re.search(r"</div>\s*<aside>", document[content_start:end])
        if not closing:
            return False, "画布与讲稿的边界不符合模板约定"
        content_end = content_start + closing.start()
        if fragment.count("<div") != fragment.count("</div>"):
            return False, "新内容的 div 开闭不配平"
        if len(fragment) < max(20, (content_end - content_start) * 0.5):
            return False, "新内容明显短于原内容，已拒绝写回"
        backup = os.path.join(tempfile.gettempdir(), "hanyu-deck-canvas-backup.html")
        with open(backup, "w", encoding="utf-8") as handle:
            handle.write(document)
        document = document[:content_start] + fragment + document[content_end:]
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(document)
        os.replace(tmp, INDEX_FILE)
    return True, ""


def notify(title, message):
    if sys.platform != "darwin":
        return
    safe_title = str(title).replace('"', "'")
    safe_message = str(message).replace('"', "'")
    subprocess.run(
        [
            "osascript",
            "-e",
            'display notification "%s" with title "%s"' % (safe_message, safe_title),
        ],
        capture_output=True,
    )


def run_export(kind):
    global export_busy
    try:
        scripts = {
            "send": ["build_send.py"],
            "imgs": ["export_pages.py"],
            "pdf": ["export_pages.py", "build_img_pdf.py"],
        }[kind]
        for script in scripts:
            command = [sys.executable, os.path.join(HERE, script)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)
            if result.returncode:
                detail = (result.stderr or result.stdout or "")[-400:]
                raise RuntimeError("%s：%s" % (script, detail.strip()))
        notify("Hanyu Deck", "导出已完成")
    except Exception as error:
        print("[导出失败]", error)
        notify("Hanyu Deck 导出失败", str(error)[:120])
    finally:
        export_busy = False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def headers_base(self, content_type):
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")

    def send_bytes(self, data, content_type, code=200):
        self.send_response(code)
        self.headers_base(content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value, code=200):
        self.send_bytes(json_bytes(value), "application/json; charset=utf-8", code)

    def body_json(self):
        size = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(size) or b"{}")

    def write_allowed(self):
        origin = self.headers.get("Origin")
        if origin in (None, "null"):
            return True
        return origin.split("//")[-1] == (self.headers.get("Host") or "")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/p"):
            with open(PHONE_FILE, "rb") as handle:
                self.send_bytes(handle.read(), "text/html; charset=utf-8")
        elif path == "/info":
            urls = phone_urls()
            now = time.time()
            with lock:
                stale = [ip for ip, seen in phone_seen.items() if now - seen > 12]
                for ip in stale:
                    phone_seen.pop(ip, None)
                phone_count = len(phone_seen)
            self.send_json(
                {
                    "urls": urls,
                    "preferred": preferred_url(urls),
                    "clients": phone_count,
                    "port": PORT,
                }
            )
        elif path == "/qr.svg":
            target = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
            if not target.startswith("http://"):
                self.send_json({"err": "bad url"}, 400)
                return
            image = qrcode.make(target, image_factory=qrcode.image.svg.SvgPathImage)
            output = io.BytesIO()
            image.save(output)
            self.send_bytes(output.getvalue(), "image/svg+xml")
        elif path == "/notes.json":
            with lock:
                self.send_json({"nv": state["nv"], "notes": notes})
        elif re.match(r"^/thumbs/\d+\.jpg$", path):
            number = int(re.search(r"(\d+)", path).group(1))
            target = thumb_path(number)
            if not target:
                self.send_json({"err": "no thumb"}, 404)
                return
            with open(target, "rb") as handle:
                self.send_bytes(handle.read(), "image/jpeg")
        elif re.match(r"^/steps/\d+-\d+\.jpg$", path):
            target = os.path.join(STEPS_DIR, os.path.basename(path))
            if not os.path.exists(target):
                self.send_json({"err": "no step frame"}, 404)
                return
            with open(target, "rb") as handle:
                self.send_bytes(handle.read(), "image/jpeg")
        elif path == "/events":
            client = queue.Queue(50)
            sse_clients.append(client)
            try:
                self.send_response(200)
                self.headers_base("text/event-stream")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                with lock:
                    initial = "event: state\ndata: %s\n\n" % json.dumps(state)
                self.wfile.write(initial.encode())
                self.wfile.flush()
                while True:
                    try:
                        message = client.get(timeout=15)
                    except queue.Empty:
                        message = ": ping\n\n"
                    self.wfile.write(message.encode())
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                if client in sse_clients:
                    sse_clients.remove(client)
        else:
            self.send_json({"err": "not found"}, 404)

    def do_POST(self):
        try:
            body = self.body_json()
        except Exception:
            self.send_json({"err": "bad json"}, 400)
            return
        path = urllib.parse.urlparse(self.path).path
        if path in ("/canvas", "/seed", "/export") and not self.write_allowed():
            self.send_json({"err": "来源不被信任，拒绝写入"}, 403)
            return
        if path == "/canvas" and self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send_json({"err": "画布写回只允许本机"}, 403)
            return
        if path == "/flip":
            with lock:
                state["seq"] += 1
                state["page"] = int(body.get("page") or 1)
                state["step"] = int(body.get("step") or 0)
                state["steps"] = int(body.get("steps") or 0)
                snapshot = dict(state)
            save_state()
            broadcast("state", snapshot)
            self.send_json({"ok": 1})
        elif path == "/phone-heartbeat":
            with lock:
                phone_seen[self.client_address[0]] = time.time()
            self.send_json({"ok": 1})
        elif path == "/goto":
            command = {}
            if "dir" in body:
                command["dir"] = 1 if int(body["dir"]) >= 0 else -1
            elif body.get("page"):
                command["page"] = max(1, int(body["page"]))
            if command:
                broadcast("cmd", command)
            self.send_json({"ok": 1})
        elif path == "/notes":
            global notes
            raw = json.dumps(body, ensure_ascii=False)
            version = hashlib.md5(raw.encode()).hexdigest()[:8]
            with lock:
                notes = body
                changed = version != state["nv"]
                state["nv"] = version
                if changed:
                    state["seq"] += 1
                snapshot = dict(state)
            with open(NOTES_FILE, "w", encoding="utf-8") as handle:
                handle.write(raw)
            if changed:
                broadcast("notes", {"nv": version})
                broadcast("state", snapshot)
            self.send_json({"ok": 1})
        elif path == "/seed":
            page = int(body.get("page") or 0)
            fragment = body.get("html") or ""
            selector = body.get("sel") or "ns"
            if selector not in ("ns", "nc") or not (1 <= page <= 999):
                self.send_json({"err": "参数不对"}, 400)
                return
            if not fragment.strip() or re.search(
                r"</?div|</?aside|<script|<!--", fragment, re.I
            ):
                self.send_json({"err": "内容为空或含不安全标签"}, 400)
                return
            ok, error = save_seed(page, fragment, selector)
            if ok:
                sync_notes_page(page, fragment, selector)
                self.send_json({"ok": 1})
            else:
                self.send_json({"err": error}, 500)
        elif path == "/canvas":
            fragment = body.get("html") or ""
            if re.search(r"<script|<iframe|\son[a-z]+\s*=", fragment, re.I):
                self.send_json({"err": "内容含脚本或事件属性"}, 400)
                return
            ok, error = save_canvas(
                int(body.get("page") or 0),
                fragment,
                int(body.get("total") or 0),
            )
            self.send_json({"ok": 1} if ok else {"err": error}, 200 if ok else 500)
        elif path == "/export":
            global export_busy
            kind = body.get("what") or "imgs"
            if kind not in ("imgs", "pdf", "send"):
                self.send_json({"err": "未知导出类型"}, 400)
                return
            with lock:
                if export_busy:
                    self.send_json({"busy": 1})
                    return
                export_busy = True
            threading.Thread(target=run_export, args=(kind,), daemon=True).start()
            self.send_json({"ok": 1})
        else:
            self.send_json({"err": "not found"}, 404)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, _request, _client_address):
        pass


def main():
    global notes
    if os.path.exists(NOTES_FILE):
        try:
            with open(NOTES_FILE, encoding="utf-8") as handle:
                notes = json.load(handle)
            state["nv"] = hashlib.md5(json_bytes(notes)).hexdigest()[:8]
        except Exception:
            notes = None
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as handle:
                saved = json.load(handle)
            for key in ("page", "step", "steps"):
                state[key] = int(saved.get(key) or 0)
            state["page"] = max(1, state["page"])
        except Exception:
            pass
    urls = phone_urls()
    print("Hanyu Deck 本地服务已启动：http://127.0.0.1:%d" % PORT)
    if urls:
        print("手机与电脑在同一网络时，打开：")
        for url in urls:
            print("  " + url)
    else:
        print("暂未发现手机可访问的局域网地址。切换网络后无需重启，二维码会自动刷新。")
    print("关闭这个窗口或按 Ctrl+C 即停止服务。")
    try:
        Server(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")


if __name__ == "__main__":
    main()

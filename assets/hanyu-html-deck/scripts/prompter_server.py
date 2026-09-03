#!/usr/bin/env python3
"""本地演示台服务。

只在当前局域网内提供手机提词、遥控、源文件写回与导出调度。
不连接公共中继，不上传讲稿，不依赖外部网络。
"""

import hashlib
import html as html_mod
import io
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from deck_content import ContentConflict, ensure_store, patch_store, read_store
from deck_source import archived_slide_pages, set_archived_slides

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX_FILE = os.path.join(ROOT, "index.html")
CONTENT_FILE = os.path.join(ROOT, "deck-content.json")
PHONE_FILE = os.path.join(HERE, "prompter-phone.html")
NOTES_FILE = os.path.join(HERE, ".prompter-notes.json")
STATE_FILE = os.path.join(HERE, ".prompter-state.json")
PAGES_DIR = os.path.join(ROOT, "导出图片")
THUMB_DIR = os.path.join(HERE, ".prompter-thumbs")
STEPS_DIR = os.path.join(HERE, ".prompter-steps")
THUMB_STATE_FILE = os.path.join(HERE, ".prompter-thumb-state.json")
STEP_STATE_FILE = os.path.join(HERE, ".prompter-step-state.json")
PORT = int(os.environ.get("HANYU_DECK_PORT") or 8123)
# 访问凭据:保护写回与手机侧。浏览器里的任意网页都能伪装成本地文件(Origin: null),
# 光靠"来自本机"判断挡不住它,故写回也要求凭据——网页拿不到它。
# 演示稿是 file:// 页面,而 macOS 的 open 会丢掉 file:// URL 上的 query 与 fragment,
# 凭据传不进去,故改为启动时写进 index.html(见 stamp_token),退出时清空。
TOKEN = os.environ.get("HANYU_DECK_TOKEN") or secrets.token_urlsafe(16)
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")

sys.path.insert(0, os.path.join(HERE, "vendor"))
import qrcode  # noqa: E402
import qrcode.image.svg  # noqa: E402

state = {"seq": int(time.time()), "page": 1, "step": 0, "steps": 0, "nv": ""}
notes = None
lock = threading.Lock()
seed_lock = threading.Lock()
content_lock = threading.RLock()
content_leases = {}
CONTENT_LEASE_SECONDS = 8
sse_clients = []
phone_seen = {}
export_busy = False
preview_revision = 0


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


_ip_cache = {"at": 0.0, "ips": []}


def cached_ips():
    now = time.time()
    if now - _ip_cache["at"] > 5:
        _ip_cache["ips"] = local_ips()
        _ip_cache["at"] = now
    return _ip_cache["ips"]


def phone_urls():
    return ["http://%s:%d/p?t=%s" % (ip, PORT, TOKEN) for ip in cached_ips()]


def display_urls():
    """给界面显示用的地址:不带凭据。凭据只随二维码交给手机。"""
    return ["http://%s:%d/p" % (ip, PORT) for ip in cached_ips()]


def allowed_hosts():
    names = ["127.0.0.1", "localhost", "[::1]", "::1"] + cached_ips()
    hosts = set()
    for name in names:
        hosts.add(name)
        hosts.add("%s:%d" % (name, PORT))
    return hosts


def allowed_origins():
    origins = {"null", "file://"}
    for name in ["127.0.0.1", "localhost", "[::1]"] + cached_ips():
        origins.add("http://%s:%d" % (name, PORT))
    return origins


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


def export_state_matches(path):
    """Do cached previews use the same archive sequence as the current source?"""
    try:
        with open(INDEX_FILE, encoding="utf-8") as handle:
            current = archived_slide_pages(handle.read())
    except (OSError, ValueError):
        return False
    if not os.path.exists(path):
        return not current  # Legacy all-current exports had no manifest and are still aligned.
    try:
        with open(path, encoding="utf-8") as handle:
            exported = json.load(handle).get("archived") or []
        return [int(page) for page in exported] == current
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def thumb_path(number):
    if not export_state_matches(THUMB_STATE_FILE):
        return None
    source = page_sources().get(number)
    if not source:
        return None
    os.makedirs(THUMB_DIR, exist_ok=True)
    target = os.path.join(THUMB_DIR, "%02d.jpg" % number)
    if not os.path.exists(target) or os.path.getmtime(target) < os.path.getmtime(source):
        try:
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
        except OSError:
            return None      # 非 macOS 没有 sips:没有缩略图,但不影响其他功能
    return target if os.path.exists(target) else None


notes_lock = threading.Lock()


def write_notes_file(raw):
    """原子写:并发的 /notes 与写回同步不会交错出半截 JSON。"""
    with notes_lock:
        tmp = NOTES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(raw)
        os.replace(tmp, NOTES_FILE)


def sync_notes_page(page, fragment, selector):
    global notes
    field = "html" if selector == "ns" else "comm"
    with lock:
        pages = (notes or {}).get("pages") or []
        target = None
        for index, item in enumerate(pages, 1):
            if not isinstance(item, dict):
                continue
            try:
                source = int(item.get("source") or item.get("n") or index)
            except (TypeError, ValueError):
                continue
            if source == page:
                target = item
                break
        if target is None:
            return
        target[field] = fragment
        raw = json.dumps(notes, ensure_ascii=False)
        state["nv"] = hashlib.md5(raw.encode()).hexdigest()[:8]
        state["seq"] += 1
        snapshot = dict(state)
    write_notes_file(raw)
    broadcast("notes", {"nv": snapshot["nv"]})
    broadcast("state", snapshot)


NOTE_TAGS = {"p", "br", "b", "strong", "i", "em", "span", "ul", "ol", "li"}
NOTE_ATTRS = {"class"}
CANVAS_TAGS = {
    "div", "span", "p", "br", "b", "strong", "i", "em", "small", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote",
    "table", "thead", "tbody", "tr", "td", "th", "figure", "figcaption",
    "section", "article", "header", "footer", "img", "code", "pre", "a",
    "svg", "g", "path", "circle", "rect", "line", "polyline", "polygon",
    "text", "tspan", "defs", "lineargradient", "radialgradient", "stop", "use",
}
CANVAS_ATTRS = {
    "class", "id", "style", "title", "role", "alt", "src", "srcset", "href",
    "target", "rel", "loading", "decoding", "width", "height", "colspan",
    "rowspan", "viewbox", "xmlns", "d", "fill", "fill-rule", "clip-rule",
    "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-dasharray", "transform", "opacity", "offset", "stop-color",
    "gradientunits", "patternunits", "preserveaspectratio", "points",
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "text-anchor", "dominant-baseline", "font-size", "font-weight",
}
# 像标签的起始:用来核对分词器是否把每一个都真正解析成了 token(未闭合标签会被它悄悄吃掉)
TAGLIKE_RE = re.compile(r"<[!/?a-zA-Z]")
BAD_URL_RE = re.compile(r"^(javascript:|data:text/html|vbscript:)", re.I)
# 区块定位靠这些边界标记,不允许出现在属性值里,否则写回时会把区间算错
BOUNDARY_RE = re.compile(r"</?(div|aside|section)\b", re.I)


class MarkupCheck(HTMLParser):
    """用标准库分词器逐 token 校验白名单。

    不能用正则:属性区 `[^>]*` 会在引号内的 `>` 处提前收尾,
    余下的 `onclick=...` 落在两个尖括号之间,正则看不见、浏览器却当真属性执行。
    """

    def __init__(self, tags, attrs):
        super().__init__(convert_charrefs=False)
        self.tags = tags
        self.attrs = attrs
        self.err = None
        self.tokens = 0

    def fail(self, message):
        if not self.err:
            self.err = message

    def handle_starttag(self, tag, attrs):
        self.tokens += 1
        if tag not in self.tags:
            self.fail("不允许的标签 <%s>" % tag)
            return
        for key, value in attrs:
            key = key.lower()
            if key.startswith("data-") or key.startswith("aria-"):
                continue
            if key not in self.attrs:
                self.fail("不允许的属性 %s" % key)
                return
            text = html_mod.unescape(value or "")
            if BOUNDARY_RE.search(text):
                self.fail("属性值里不允许出现 div / aside / section 标记")
                return
            if key in ("href", "src", "srcset"):
                # 先解码再去掉空白与控制字符:javascript&#58; 与 java\tscript: 都要拦住
                if BAD_URL_RE.match(re.sub(r"[\s\x00-\x1f]", "", text)):
                    self.fail("不允许的链接协议")
                    return

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        self.tokens += 1
        if tag not in self.tags:
            self.fail("不允许的标签 </%s>" % tag)

    def handle_comment(self, _data):
        self.tokens += 1
        self.fail("内容含注释")

    def handle_decl(self, _decl):
        self.tokens += 1
        self.fail("内容含文档声明")

    def unknown_decl(self, _data):
        self.tokens += 1
        self.fail("内容含未知声明")

    def handle_pi(self, _data):
        self.tokens += 1
        self.fail("内容含处理指令")


def check_markup(fragment, tags, attrs):
    """白名单校验:标签与属性都必须在清单里,未列出的一律拒绝(含 on* 事件属性)。"""
    checker = MarkupCheck(tags, attrs)
    try:
        checker.feed(fragment)
        checker.close()
    except Exception:
        return False, "内容无法解析"
    if checker.err:
        return False, checker.err
    if checker.tokens != len(TAGLIKE_RE.findall(fragment)):
        return False, "有未闭合的标签"
    return True, ""


TOKEN_LINE_RE = re.compile(r"(var TOKEN = ')([^']*)('; /\* HANYU_TOKEN \*/)")


def stamp_token(value):
    """把本次运行的凭据写进演示稿;传空字符串即清除。

    演示稿是 file:// 页面,凭据没法经 URL 传入,只能落到文件里。服务停止时清空,
    这样"服务没在跑"与"文件里没有凭据"始终一致。
    """
    with seed_lock:
        try:
            with open(INDEX_FILE, encoding="utf-8") as handle:
                document = handle.read()
        except OSError:
            return False
        updated, count = TOKEN_LINE_RE.subn(r"\g<1>" + value + r"\g<3>", document, count=1)
        if count != 1:
            return False
        if updated == document:
            return True
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        os.replace(tmp, INDEX_FILE)
    return True


def find_block(document, selector, page):
    """按 div 开闭配平定位第 page 个 .ns/.nc 区块,返回内容区间。

    不能用非贪婪正则:区块内若有嵌套 div,`.*?</div>` 会在中途截断,
    写回后多出的 </div> 会提前关掉 <aside>,把源文件结构改坏。
    """
    opens = [m for m in re.finditer(r'<div class="%s">' % selector, document)]
    if page > len(opens):
        return None
    start = opens[page - 1].end()
    depth = 1
    for match in re.finditer(r"<div\b|</div>", document[start:]):
        depth += 1 if match.group(0).startswith("<div") else -1
        if depth == 0:
            return start, start + match.start(), start + match.end()
    return None


def save_seed(page, fragment, selector, dom_total):
    with seed_lock:
        with open(INDEX_FILE, encoding="utf-8") as handle:
            document = handle.read()
        sections = len(re.findall(r'<section class="slide"[\s>]', document))
        if dom_total != sections:
            return False, "源文件页数已变化，请刷新后再修改"
        found = find_block(document, selector, page)
        if not found:
            return False, "文件里没有第 %d 页的 %s 区域" % (page, selector)
        inner_start, inner_end, _ = found
        document = document[:inner_start] + fragment + document[inner_end:]
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
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


def save_archive(archived_pages, dom_total):
    """Write the complete archive set atomically; pages themselves remain in the source."""
    with seed_lock:
        with open(INDEX_FILE, encoding="utf-8") as handle:
            document = handle.read()
        try:
            updated = set_archived_slides(document, archived_pages, dom_total)
        except (TypeError, ValueError) as error:
            return False, str(error)
        if updated == document:
            return True, ""
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        os.replace(tmp, INDEX_FILE)
    return True, ""


def notify(title, message):
    if sys.platform != "darwin":
        return

    def esc(text):
        return str(text).replace("\\", "\\\\").replace('"', '\\"')

    subprocess.run(
        [
            "osascript",
            "-e",
            'display notification "%s" with title "%s"' % (esc(message), esc(title)),
        ],
        capture_output=True,
    )


def run_export(kind):
    global export_busy, preview_revision
    try:
        scripts = {
            "send": ["build_send.py"],
            "imgs": ["export_pages.py"],
            "pdf": ["export_pages.py", "build_img_pdf.py"],
            "previews": ["export_pages.py", "export_steps.py"],
        }[kind]
        for script in scripts:
            command = [sys.executable, os.path.join(HERE, script)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)
            if result.returncode:
                detail = (result.stderr or result.stdout or "")[-400:]
                raise RuntimeError("%s: %s" % (script, detail.strip()))
        if kind == "previews":
            preview_revision = time.time_ns()
            broadcast("preview", {"rev": preview_revision})
        else:
            notify("Hanyu HTML Deck", "Export complete")
    except Exception as error:
        print("[导出失败]", error)
        if kind != "previews":
            notify("Hanyu HTML Deck · Export failed", "Check the local service log for details.")
    finally:
        export_busy = False


LOCAL_ONLY = (
    "/archive", "/canvas", "/seed", "/export", "/notes", "/flip", "/info", "/qr.svg",
    "/content", "/content/lease", "/content/patch",
)
PHONE_PATHS = ("/", "/p", "/notes.json", "/events", "/goto", "/phone-heartbeat")
MAX_SSE_CLIENTS = 8


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 15          # 只建连不发数据的客户端不该把线程永久占住(鉴权之前就发生)

    def log_message(self, *_args):
        pass

    def headers_base(self, content_type):
        self.send_header("Content-Type", content_type)
        origin = self.headers.get("Origin")
        if origin and origin in allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
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
        if size > 8 * 1024 * 1024:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def from_loopback(self):
        return self.client_address[0] in LOOPBACK

    def host_ok(self):
        """Host 必须指向本机:堵住 DNS rebinding(攻击页把自己的域名重绑到 127.0.0.1)。"""
        return (self.headers.get("Host") or "") in allowed_hosts()

    def origin_ok(self):
        origin = self.headers.get("Origin")
        return origin is None or origin in allowed_origins()

    def token_ok(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        given = query.get("t", [""])[0]
        # compare_digest 对非 ASCII 会抛 TypeError,先编码再比,免得异常把连接静默切断
        return secrets.compare_digest(given.encode("utf-8", "ignore"), TOKEN.encode())

    def allow(self, path):
        """返回 (是否放行, 拒绝原因)。默认拒绝:只放行显式登记的路径与前缀。"""
        if not self.host_ok():
            return False, "请求的主机名不是本机地址"
        if path.startswith("/thumbs/") or path.startswith("/steps/"):
            if self.from_loopback() or self.token_ok():
                return True, ""
            return False, "需要有效的手机访问令牌"
        if path in LOCAL_ONLY:
            if not self.from_loopback():
                return False, "这个操作只允许本机"
            if not self.origin_ok():
                return False, "来源不被信任，拒绝写入"
            if not self.token_ok():
                # 浏览器里的任意网页都能伪装成本地文件,只看"来自本机"挡不住它;
                # 凭据由服务启动时写进 index.html,网页拿不到
                return False, "缺少访问凭据：这个页面比服务先打开，刷新一下即可"
            return True, ""
        if path in PHONE_PATHS:
            if self.from_loopback() or self.token_ok():
                return True, ""
            return False, "需要有效的手机访问令牌，请重新扫码"
        return False, "未知的请求路径"

    def guard(self, path):
        ok, why = self.allow(path)
        if not ok:
            self.send_json({"err": why}, 403)
        return ok

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if not self.host_ok() or not (origin and origin in allowed_origins()):
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not self.guard(path):
            return
        if path in ("/", "/p"):
            with open(PHONE_FILE, "rb") as handle:
                self.send_bytes(handle.read(), "text/html; charset=utf-8")
        elif path == "/info":
            urls = display_urls()
            now = time.time()
            with lock:
                stale = [ip for ip, seen in phone_seen.items() if now - seen > 12]
                for ip in stale:
                    phone_seen.pop(ip, None)
                phone_count = len(phone_seen)
            preferred = preferred_url(urls)
            self.send_json(
                {
                    "urls": urls,                       # 不带凭据:界面只用来显示
                    "preferred": preferred,
                    "qr": "/qr.svg?i=%d" % (urls.index(preferred) if preferred in urls else 0),
                    "clients": phone_count,
                    "port": PORT,
                }
            )
        elif path == "/qr.svg":
            # 只收序号,链接由服务端自己拼:凭据不经过调用方,也就不会被读走
            try:
                index = int(urllib.parse.parse_qs(parsed.query).get("i", ["0"])[0])
            except ValueError:
                index = 0
            urls = phone_urls()
            if not urls:
                self.send_json({"err": "no lan address"}, 404)
                return
            target = urls[index] if 0 <= index < len(urls) else urls[0]
            image = qrcode.make(target, image_factory=qrcode.image.svg.SvgPathImage)
            output = io.BytesIO()
            image.save(output)
            self.send_bytes(output.getvalue(), "image/svg+xml")
        elif path == "/notes.json":
            with lock:                      # 锁内只取快照:发送在锁外,慢客户端卡不住其他请求
                payload = {"nv": state["nv"], "notes": notes}
            self.send_json(payload)
        elif path == "/content":
            with content_lock:
                payload = read_store(CONTENT_FILE)
            self.send_json(payload)
        elif re.match(r"^/thumbs/\d+\.jpg$", path):
            number = int(re.search(r"(\d+)", path).group(1))
            target = thumb_path(number)
            if not target:
                self.send_json({"err": "no thumb"}, 404)
                return
            with open(target, "rb") as handle:
                self.send_bytes(handle.read(), "image/jpeg")
        elif re.match(r"^/steps/\d+-\d+\.jpg$", path):
            if not export_state_matches(STEP_STATE_FILE):
                self.send_json({"err": "step frames need export"}, 404)
                return
            target = os.path.join(STEPS_DIR, os.path.basename(path))
            if not os.path.exists(target):
                self.send_json({"err": "no step frame"}, 404)
                return
            with open(target, "rb") as handle:
                self.send_bytes(handle.read(), "image/jpeg")
        elif path == "/events":
            if len(sse_clients) >= MAX_SSE_CLIENTS:
                self.send_json({"err": "同时连接的设备过多"}, 503)
                return
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

    def drain_body(self):
        """把请求体读掉丢弃:keep-alive 下不读干净,残留字节会被当成下一个请求。"""
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            size = 0
        while size > 0:
            chunk = self.rfile.read(min(size, 65536))
            if not chunk:
                break
            size -= len(chunk)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        ok, why = self.allow(path)
        if not ok:
            self.drain_body()
            self.send_json({"err": why}, 403)
            return
        try:
            body = self.body_json()
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
        except Exception:
            self.send_json({"err": "bad json"}, 400)
            return
        try:
            self.handle_post(path, body)
        except (TypeError, ValueError, AttributeError, KeyError):
            self.send_json({"err": "参数不对"}, 400)

    def handle_post(self, path, body):
        if path == "/content/lease":
            slide_id = body.get("slideId") or ""
            field = body.get("field") or ""
            owner = body.get("owner") or ""
            action = body.get("action") or "acquire"
            if field not in ("script", "note") or not slide_id or not owner:
                self.send_json({"err": "参数不对"}, 400)
                return
            key = (slide_id, field)
            now = time.monotonic()
            with content_lock:
                active = content_leases.get(key)
                if active and active["expires"] <= now:
                    content_leases.pop(key, None)
                    active = None
                if action == "release":
                    if active and active["owner"] == owner:
                        content_leases.pop(key, None)
                    self.send_json({"ok": 1})
                    return
                if action not in ("acquire", "renew"):
                    self.send_json({"err": "未知的租约动作"}, 400)
                    return
                if active and active["owner"] != owner:
                    self.send_json({"err": "这个字段正在另一处编辑"}, 423)
                    return
                content_leases[key] = {"owner": owner, "expires": now + CONTENT_LEASE_SECONDS}
            self.send_json({"ok": 1, "expiresIn": CONTENT_LEASE_SECONDS})
        elif path == "/content/patch":
            slide_id = body.get("slideId") or ""
            field = body.get("field") or ""
            fragment = body.get("html")
            owner = body.get("owner") or ""
            if field not in ("script", "note") or not slide_id or not owner or not isinstance(fragment, str):
                self.send_json({"err": "参数不对"}, 400)
                return
            safe, why = check_markup(fragment, NOTE_TAGS, NOTE_ATTRS)
            if not safe:
                self.send_json({"err": why}, 400)
                return
            key = (slide_id, field)
            with content_lock:
                now = time.monotonic()
                active = content_leases.get(key)
                if active and active["expires"] <= now:
                    content_leases.pop(key, None)
                    active = None
                if active and active["owner"] != owner:
                    self.send_json({"err": "这个字段正在另一处编辑"}, 423)
                    return
                try:
                    store, current = patch_store(
                        CONTENT_FILE, slide_id, field, fragment, int(body.get("baseRevision"))
                    )
                except ContentConflict as error:
                    latest = read_store(CONTENT_FILE)["slides"].get(slide_id, {}).get(field)
                    self.send_json({"err": str(error), "current": latest}, 409)
                    return
                except KeyError as error:
                    self.send_json({"err": str(error)}, 404)
                    return
            selector = "ns" if field == "script" else "nc"
            if slide_id in store["order"]:
                sync_notes_page(store["order"].index(slide_id) + 1, fragment, selector)
            event = {
                "slideId": slide_id,
                "field": field,
                "html": current["html"],
                "fieldRevision": current["revision"],
                "revision": store["revision"],
                "actor": owner,
            }
            broadcast("content", event)
            self.send_json({"ok": 1, **event})
        elif path == "/flip":
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
            # 这里的内容会下发给手机端并以 innerHTML 渲染,必须与 /seed 同一套白名单,
            # 否则等于开了第二条不设防的入口
            for page in (body.get("pages") or []):
                if not isinstance(page, dict):
                    self.send_json({"err": "页数据格式不对"}, 400)
                    return
                for field in ("html", "comm"):
                    value = page.get(field)
                    if value in (None, ""):
                        continue
                    if not isinstance(value, str):
                        self.send_json({"err": "页内容必须是文本"}, 400)
                        return
                    safe, why = check_markup(value, NOTE_TAGS, NOTE_ATTRS)
                    if not safe:
                        self.send_json({"err": why}, 400)
                        return
            raw = json.dumps(body, ensure_ascii=False)
            version = hashlib.md5(raw.encode()).hexdigest()[:8]
            with lock:
                notes = body
                changed = version != state["nv"]
                state["nv"] = version
                if changed:
                    state["seq"] += 1
                snapshot = dict(state)
            write_notes_file(raw)
            if changed:
                broadcast("notes", {"nv": version})
                broadcast("state", snapshot)
            self.send_json({"ok": 1})
        elif path == "/seed":
            page = int(body.get("page") or 0)
            fragment = body.get("html") or ""
            selector = body.get("sel") or "ns"
            dom_total = int(body.get("total") or 0)
            if selector not in ("ns", "nc") or not (1 <= page <= 999) or dom_total < 1:
                self.send_json({"err": "参数不对"}, 400)
                return
            if not fragment.strip():
                self.send_json({"err": "内容为空"}, 400)
                return
            safe, why = check_markup(fragment, NOTE_TAGS, NOTE_ATTRS)
            if not safe:
                self.send_json({"err": why}, 400)
                return
            ok, error = save_seed(page, fragment, selector, dom_total)
            if ok:
                sync_notes_page(page, fragment, selector)
                self.send_json({"ok": 1})
            else:
                self.send_json({"err": error}, 500)
        elif path == "/canvas":
            fragment = body.get("html") or ""
            dom_total = int(body.get("total") or 0)
            if dom_total < 1:
                self.send_json({"err": "缺少页数，拒绝写回"}, 400)
                return
            safe, why = check_markup(fragment, CANVAS_TAGS, CANVAS_ATTRS)
            if not safe:
                self.send_json({"err": why}, 400)
                return
            ok, error = save_canvas(int(body.get("page") or 0), fragment, dom_total)
            self.send_json({"ok": 1} if ok else {"err": error}, 200 if ok else 500)
        elif path == "/archive":
            archived = body.get("archived")
            try:
                dom_total = int(body.get("total") or 0)
            except (TypeError, ValueError):
                dom_total = 0
            if not isinstance(archived, list) or dom_total < 1:
                self.send_json({"err": "参数不对"}, 400)
                return
            ok, error = save_archive(archived, dom_total)
            self.send_json({"ok": 1} if ok else {"err": error}, 200 if ok else 409)
        elif path == "/export":
            global export_busy
            kind = body.get("what") or "imgs"
            if kind not in ("imgs", "pdf", "send", "previews"):
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
    ensure_store(INDEX_FILE, CONTENT_FILE)
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
    print("本地演示台服务已启动：http://127.0.0.1:%d" % PORT)
    if urls:
        print("手机与电脑在同一网络时，打开（链接含本次运行的访问令牌）：")
        for url in urls:
            print("  " + url)
    else:
        print("暂未发现手机可访问的局域网地址。切换网络后无需重启，二维码会自动刷新。")
    print("关闭这个窗口或按 Ctrl+C 即停止服务。")
    try:
        server = Server(("0.0.0.0", PORT), Handler)
    except OSError as error:
        # 先占端口再动文件:端口被占说明另有服务在跑,它写进去的凭据不能被清掉。
        print("端口 %d 起不来：%s" % (PORT, error))
        print("可能已有一个本地演示台服务在跑；或设置 HANYU_DECK_PORT 换一个端口。")
        sys.exit(1)
    if stamp_token(TOKEN):
        print("已把本次运行的写回凭据写进 index.html，停止服务时自动清除。")
    else:
        print("index.html 里没有凭据锚点（版本较旧），写回与导出会被拒绝。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        stamp_token("")


if __name__ == "__main__":
    main()

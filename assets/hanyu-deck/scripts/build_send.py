"""发送版单文件 HTML：图片重压缩后 base64 内联，剥掉备注与联服务行为 → ../发送版.html

发送版会交到外部人手里，绝不能带 .nc（或旧模板 .na）内部注记。
剥除按 div 开闭配平定位，不能用非贪婪正则——备注里若有嵌套 div，
`.*?</div>` 会在中途截断，把内部内容留在发送版里而自检还显示"通过"。
"""
import base64
import pathlib
import re
import subprocess
import sys
import tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.gettempdir()) / "deck-export" / "send-img"
TMP.mkdir(parents=True, exist_ok=True)
SOURCE = (BASE / "index.html").read_text(encoding="utf-8")
html = SOURCE


def fail(message):
    sys.exit("发送版导出中止：%s" % message)


def strip_blocks(document, selector):
    """按 div 开闭配平删除全部 <div class="selector">…</div> 区块，返回 (结果, 删除数, 原文本列表)。"""
    removed = []
    while True:
        opening = re.search(r'\s*<div class="%s">' % selector, document)
        if not opening:
            return document, len(removed), removed
        inner = opening.end()
        depth = 1
        end = None
        for match in re.finditer(r"<div\b|</div>", document[inner:]):
            depth += 1 if match.group(0).startswith("<div") else -1
            if depth == 0:
                end = inner + match.end()
                break
        if end is None:
            fail("第 %d 个 .%s 区块的 div 开闭不配平，无法安全剥除" % (len(removed) + 1, selector))
        removed.append(document[inner : end - len("</div>")])
        document = document[: opening.start()] + document[end:]


# 1) 剥备注/内部注记。.nc 是当前模板；.na 是旧模板兼容。
html, n_nc, texts_nc = strip_blocks(html, "nc")
html, n_na, texts_na = strip_blocks(html, "na")
n_private = n_nc + n_na
private_texts = texts_nc + texts_na

# 1b) 剥画布就地编辑：外发文件没有本地服务，留着只会弹内部工具提示
html, n_cvedit = re.subn(
    r"\s*// ===== CVEDIT-START.*?// ===== CVEDIT-END =====", "", html, flags=re.S
)

# 1c) 置发送版标记：写回、提词推送、事件流、手机弹窗与相关入口一并失效
html, n_flag = re.subn(r"var SEND_VERSION = false;", "var SEND_VERSION = true;", html)

# 2) 收集引用的图片与字体
refs = sorted(set(re.findall(r"(?:images|fonts)/[A-Za-z0-9._-]+\.[A-Za-z0-9]+", html)))
missing = [r for r in refs if not (BASE / r).exists()]
if missing:
    fail("缺少文件 %s" % missing)

KEEP_PNG = set()  # 需要透明通道的图(logo 等)写进来,如 {"images/logo.png"};其余统一转 JPEG 压体积
uri = {}
total = 0
for r in refs:
    src = BASE / r
    if r.endswith(".woff2"):
        data = src.read_bytes()
        mime = "font/woff2"
    elif r in KEEP_PNG:
        data = src.read_bytes()
        mime = "image/png"
    else:
        out = TMP / (pathlib.Path(r).stem + ".jpg")
        try:
            subprocess.run(
                ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                 str(src), "--out", str(out)],
                capture_output=True, check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            fail("压缩 %s 需要 macOS 的 sips 命令" % r)
        data = out.read_bytes()
        mime = "image/jpeg"
    total += len(data)
    uri[r] = "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())

# 3) 替换(长名先替,避免前缀误替)
for r in sorted(refs, key=len, reverse=True):
    html = html.replace(r, uri[r])

# 4) 自检。用显式退出而不是 assert：python -O 会把 assert 整体移除，
#    安全自检不能建在会被优化掉的语句上。
if 'class="nc"' in html or 'class="na"' in html:
    fail("备注区块没剥净")
for text in private_texts:
    stripped = re.sub(r"<[^>]+>", "", text).strip()
    if len(stripped) >= 8 and stripped in html:
        fail("备注正文仍残留在发送版里：%s" % stripped[:30])
if n_cvedit != 1 or "CVEDIT-START" in html:
    fail("画布就地编辑没剥净")
if n_flag != 1:
    fail("没能置上发送版标记，写回与提词代码仍会联本地服务")
left = set(re.findall(r"(?:images|fonts)/[A-Za-z0-9._-]+\.[A-Za-z0-9]+", html))
if left:
    fail("这些文件没内联成功 %s" % left)

out = BASE / "发送版.html"
out.write_text(html, encoding="utf-8")
print(
    "备注剥除 %d 处｜画布编辑剥除 %d 处｜发送版标记已置｜图片字体内联 %d 个｜原始 %dMB｜成品 %dMB"
    % (n_private, n_cvedit, len(refs), total // 1024 // 1024, out.stat().st_size // 1024 // 1024)
)

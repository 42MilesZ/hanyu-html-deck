"""发送版单文件 HTML:图片重压缩后 base64 内联,剥掉备注栏与画布就地编辑 → ../发送版.html
发送版绝不能带 .nc(或旧模板 .na)内部注记,本脚本自动剥除并自检。"""
import base64, pathlib, re, subprocess, sys, tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.gettempdir()) / "deck-export" / "send-img"
TMP.mkdir(parents=True, exist_ok=True)
html = (BASE / "index.html").read_text(encoding="utf-8")

# 1) 剥备注/内部注记。.nc 是当前模板；.na 是旧模板兼容。
html, n_private = re.subn(r'\s*<div class="(?:nc|na)">.*?</div>', '', html, flags=re.S)

# 1b) 剥画布就地编辑:外发文件没有本地服务,留着只会弹内部工具提示
html, n_cvedit = re.subn(r'\s*// ===== CVEDIT-START.*?// ===== CVEDIT-END =====', '', html, flags=re.S)

# 2) 收集引用的图片与内嵌字体子集
refs = sorted(set(re.findall(r'(?:images|fonts)/[A-Za-z0-9._-]+\.[A-Za-z0-9]+', html)))
missing = [r for r in refs if not (BASE / r).exists()]
if missing:
    sys.exit("missing files: %s" % missing)

KEEP_PNG = set()  # 需要透明通道的图(logo 等)写进来,如 {"images/logo.png"};其余统一转 JPEG 压体积
uri = {}
total = 0
for r in refs:
    src = BASE / r
    if r.endswith('.woff2'):
        data = src.read_bytes()
        mime = "font/woff2"
    elif r in KEEP_PNG:
        data = src.read_bytes()
        mime = "image/png"
    else:
        out = TMP / (pathlib.Path(r).stem + ".jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                        str(src), "--out", str(out)], capture_output=True, check=True)
        data = out.read_bytes()
        mime = "image/jpeg"
    total += len(data)
    uri[r] = f"data:{mime};base64," + base64.b64encode(data).decode()

# 3) 替换(长名先替,避免前缀误替)
for r in sorted(refs, key=len, reverse=True):
    html = html.replace(r, uri[r])

# 自检:备注栏已剥净、所有文件引用已内联。
left = set(re.findall(r'(?:images|fonts)/[A-Za-z0-9._-]+\.[A-Za-z0-9]+', html))
assert 'class="nc"' not in html and 'class="na"' not in html and not left, left
assert n_cvedit == 1 and 'CVEDIT-START' not in html, '画布就地编辑没剥净'
out = BASE / "发送版.html"
out.write_text(html, encoding="utf-8")
print(f"private notes removed: {n_private} | canvas-edit stripped: {n_cvedit} | images inlined: {len(refs)} | raw {total//1024//1024}MB | html {out.stat().st_size//1024//1024}MB")

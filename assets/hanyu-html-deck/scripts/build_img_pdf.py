"""纯图片 PDF:导出图片/*.png 按页序合成 → ../图片版.pdf(不带讲稿,当 PPT 发人用)
依赖:先跑 export_pages.py 产出 PNG;playwright(chromium) 打印;sips 压 JPEG 控体积。"""
from playwright.sync_api import sync_playwright
import pathlib, re, shutil, subprocess, tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
PNGS = BASE / "导出图片"
OUT = BASE / "图片版.pdf"
WORK = pathlib.Path(tempfile.gettempdir()) / "deck-export" / "imgpdf"
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)

# 同页号若有多份文件(页面改名后的旧残留),取 mtime 最新的一份——与提词服务缩略图同一规则
byp = {}
for f in PNGS.glob("*.png"):
    m = re.match(r"(\d+)", f.stem)
    if not m:
        continue
    n = int(m.group(1))
    if n not in byp or f.stat().st_mtime > byp[n].stat().st_mtime:
        byp[n] = f
files = [byp[k] for k in sorted(byp)]
assert files, "导出图片 里没有 PNG,先跑 export_pages.py"

imgs = []
for f in files:
    j = WORK / (f.stem + ".jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88", "-Z", "2560",
                    str(f), "--out", str(j)], capture_output=True, check=True)
    imgs.append(j)

# 508mm × 285.75mm 恰为 16:9,一图一页无边距
html = ("<style>@page{size:508mm 285.75mm;margin:0}html,body{margin:0;padding:0}"
        "img{display:block;width:508mm;height:285.75mm;object-fit:cover;page-break-after:always}"
        "img:last-child{page-break-after:auto}</style>"
        + "".join(f'<img src="{i.as_uri()}">' for i in imgs))
(WORK / "book.html").write_text(html, encoding="utf-8")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.goto((WORK / "book.html").as_uri())
    pg.wait_for_timeout(600)
    pg.pdf(path=str(OUT), prefer_css_page_size=True, print_background=True,
           margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    b.close()

print(f"✓ {OUT.name}  {OUT.stat().st_size / 1e6:.1f} MB, {len(imgs)} 页")

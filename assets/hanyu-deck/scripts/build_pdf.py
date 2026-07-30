"""图文对照 PDF:每页 = 幻灯片截图 + 对应演讲稿 → ../图文讲稿.pdf
依赖:先跑 export_pages.py(产出 PNG + notes.json);本脚本自带 PNG→JPEG 压缩(sips)。"""
from playwright.sync_api import sync_playwright
import pathlib, json, html as H, re, subprocess, tempfile, shutil

BASE = pathlib.Path(__file__).resolve().parent.parent
PNGS = BASE / "导出图片"
WORK = pathlib.Path(tempfile.gettempdir()) / "deck-export"
_m = re.search(r"<title>(.*?)</title>", (BASE / "index.html").read_text(encoding="utf-8"))
TITLE = _m.group(1) if _m else "演示稿"
IMG = WORK / "pdf-img"
shutil.rmtree(IMG, ignore_errors=True)  # 页名变动后旧 jpg 会被 {页号}-* 通配误收,先清空
IMG.mkdir(parents=True, exist_ok=True)
notes = json.loads((WORK / "notes.json").read_text(encoding="utf-8"))

for f in PNGS.glob("*.png"):
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", "-Z", "1920",
                    str(f), "--out", str(IMG / (f.stem + ".jpg"))], capture_output=True, check=True)

secs = []
for n in notes:
    p, title, header, paras = n["page"], n["title"], n["header"], n["paras"]
    pics = "".join(f'<img src="{f.as_uri()}">' for f in sorted(IMG.glob(f"{p:02d}-*.jpg")))
    body = "".join(f"<p>{H.escape(t)}</p>" for t in paras)
    secs.append(f"""<section>
  <div class="hd"><span class="no">{p:02d}</span><span class="tt">{H.escape(title)}</span><span class="tm">{H.escape(header)}</span></div>
  {pics}
  <div class="tx">{body}</div>
</section>""")

doc = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: "Noto Sans SC", "PingFang SC", sans-serif; color: #111; font-weight: 300; }}
  section {{ break-before: page; padding: 2mm 0; }}
  section:first-child {{ break-before: auto; }}
  .hd {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 4mm; border-bottom: 0.3mm solid #111; padding-bottom: 2.6mm; }}
  .hd .no {{ font-size: 15pt; font-weight: 300; }}
  .hd .tt {{ font-size: 13pt; font-weight: 600; letter-spacing: .04em; }}
  .hd .tm {{ font-size: 9pt; color: #777; margin-left: auto; letter-spacing: .06em; }}
  img {{ width: 100%; display: block; margin-bottom: 3mm; outline: 0.2mm solid #ddd; }}
  .tx {{ margin-top: 2mm; }}
  .tx p {{ font-size: 10pt; line-height: 1.82; margin-bottom: 2mm; text-align: justify; }}
  @page {{ size: A4 portrait; margin: 13mm 14mm; }}
</style></head><body>
<div style="height:100%;display:flex;flex-direction:column;justify-content:center;break-after:page">
  <div style="font-size:24pt;font-weight:300;letter-spacing:.08em">{H.escape(TITLE)} · 图文讲稿</div>
  <div style="font-size:11pt;color:#777;margin-top:6mm;letter-spacing:.06em">{len(notes)} 页 · 页面与对应演讲稿对照</div>
</div>
{''.join(secs)}
</body></html>"""

src = WORK / "pdf-doc.html"
src.write_text(doc, encoding="utf-8")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.goto(src.as_uri())
    pg.wait_for_timeout(1200)
    pg.pdf(path=str(BASE / "图文讲稿.pdf"), format="A4", print_background=True)
    b.close()
print("PDF done:", (BASE / "图文讲稿.pdf").stat().st_size // 1024, "KB")

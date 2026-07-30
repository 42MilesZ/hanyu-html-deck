"""逐页导出 3840×2160 PNG(覆盖 ../导出图片/ 同名文件)+ 抽取讲稿 JSON(供 build_pdf.py)。
页表自动从 DOM 派生:每页取 data-title 命名文件,分步页(data-steps)取步进完成态。
依赖:python3 + playwright(chromium)。改稿后先跑本脚本,再跑 build_pdf.py / build_send.py。"""
from playwright.sync_api import sync_playwright
import pathlib, json, re, tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
URL = (BASE / "index.html").as_uri()
OUT = BASE / "导出图片"
OUT.mkdir(exist_ok=True)
WORK = pathlib.Path(tempfile.gettempdir()) / "deck-export"
WORK.mkdir(parents=True, exist_ok=True)

# 把入场动画/过渡压到 1ms:截图恒为静态终态(与总览缩略图同一原则)
FF_CSS = "*{animation-delay:0s !important;animation-duration:1ms !important;transition-duration:1ms !important;transition-delay:0s !important;}"

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={'width': 1980, 'height': 1114}, device_scale_factor=2)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    def load(p):
        pg.goto("about:blank")
        pg.goto(URL + f"#p{p}")
        pg.evaluate("document.body.classList.add('present', 'exporting'); window.dispatchEvent(new Event('resize'))")
        pg.add_style_tag(content=FF_CSS)
        pg.wait_for_timeout(350)

    # 页表 + 讲稿 JSON(供 build_pdf.py 与手机提词缩略图管线)
    load(1)
    meta = pg.evaluate("""(() => Array.from(document.querySelectorAll('#stage .slide')).map((s, i) => {
      const c = s.querySelector('.canvas');
      const ns = s.querySelector('aside .ns');
      const b = ns ? ns.querySelector('b') : null;
      return { page: i + 1, title: s.dataset.title || '',
               steps: c && c.dataset.steps ? +c.dataset.steps : 0,
               header: b ? b.innerText : '',
               paras: ns ? Array.from(ns.querySelectorAll('p')).map(p => p.innerText) : [] };
    }))()""")
    (WORK / "notes.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    for m in meta:
        p = m["page"]
        safe = re.sub(r'[/\\:*?"<>|]', "·", m["title"]) or f"页{p}"
        name = f"{p:02d}-{safe}.png"
        load(p)
        if m["steps"]:
            # 分步页取步进完成态(data-autostep 定时器也可能在跑,直接设终值覆盖)
            pg.evaluate(f"document.querySelector('.slide.current .canvas').dataset.step = {m['steps']}")
            pg.wait_for_timeout(250)
        pg.wait_for_timeout(300)
        box = pg.evaluate("(() => { const r = document.querySelector('.slide.current .canvas').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()")
        pg.screenshot(path=str(OUT / name), clip=box)
        print("✓", name)

    print("pages:", len(meta), "| JS errors:", errs if errs else "none")
    b.close()

"""逐页导出 3840×2160 PNG(覆盖 ../导出图片/ 同名文件)+ 抽取讲稿 JSON(供 build_pdf.py)。
页表自动从 DOM 派生:每页取 data-title 命名文件,分步页(data-steps)取步进完成态。
依赖:python3 + playwright(chromium)。改稿后先跑本脚本,再跑 build_pdf.py / build_send.py。"""
from playwright.sync_api import sync_playwright
import pathlib, json, re, tempfile

from deck_content import ensure_store

BASE = pathlib.Path(__file__).resolve().parent.parent
URL = (BASE / "index.html").as_uri()
OUT = BASE / "导出图片"
WORK = pathlib.Path(tempfile.gettempdir()) / "deck-export"
WORK.mkdir(parents=True, exist_ok=True)
CONTENT = ensure_store(BASE / "index.html", BASE / "deck-content.json")

# 把入场动画/过渡压到 1ms:截图恒为静态终态(与总览缩略图同一原则)
FF_CSS = "*{animation-delay:0s !important;animation-duration:1ms !important;transition-duration:1ms !important;transition-delay:0s !important;}"

with tempfile.TemporaryDirectory(prefix="deck-export-pages-", dir=str(BASE)) as staging_dir:
    staging = pathlib.Path(staging_dir)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={'width': 1980, 'height': 1114}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        def load(p):
            pg.goto("about:blank")
            pg.goto(URL + f"#p{p}")
            pg.evaluate("""store => document.querySelectorAll('#stage .slide').forEach((slide, i) => {
              const id = slide.dataset.slideId || `slide-${String(i + 1).padStart(3, '0')}`;
              const item = store.slides && store.slides[id];
              if (!item) return;
              const script = slide.querySelector('aside .ns'), note = slide.querySelector('aside .nc');
              if (script && item.script) script.innerHTML = item.script.html;
              if (note && item.note) note.innerHTML = item.note.html;
            })""", CONTENT)
            pg.evaluate("document.body.classList.add('present', 'exporting'); window.dispatchEvent(new Event('resize'))")
            pg.add_style_tag(content=FF_CSS)
            pg.wait_for_timeout(350)

        # 页表 + 讲稿 JSON(供 build_pdf.py 与手机提词缩略图管线)
        load(1)
        archived = pg.evaluate("""(() => Array.from(document.querySelectorAll('#stage .slide'))
          .filter(s => s.dataset.archived === '1').map(s => +s.dataset.page))()""")
        meta = pg.evaluate("""(() => Array.from(document.querySelectorAll('#stage .slide'))
          .filter(s => s.dataset.archived !== '1').map((s, i) => {
          const c = s.querySelector('.canvas');
          const ns = s.querySelector('aside .ns');
          const b = ns ? ns.querySelector('b') : null;
          return { page: i + 1, title: s.dataset.title || '',
                   steps: c && c.dataset.steps ? +c.dataset.steps : 0,
                   header: b ? b.innerText : '',
                   paras: ns ? Array.from(ns.querySelectorAll('p')).map(p => p.innerText) : [] };
        }))()""")
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
            pg.screenshot(path=str(staging / name), clip=box)
            print("✓", name)

        print("pages:", len(meta), "| JS errors:", errs if errs else "none")
        b.close()

    # 截图全部成功后才替换上一版，避免 Playwright/页面异常留下空目录或半套产物。
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    for fresh in staging.glob("*.png"):
        fresh.replace(OUT / fresh.name)
    (WORK / "notes.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    state = BASE / "scripts" / ".prompter-thumb-state.json"
    state_tmp = BASE / "scripts" / ".prompter-thumb-state.json.tmp"
    state_tmp.write_text(json.dumps({"archived": archived}), encoding="utf-8")
    state_tmp.replace(state)

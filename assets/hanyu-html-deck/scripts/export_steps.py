"""分步页关键帧导出:凡带 data-steps 的页,把每个 step(0..N)各截一帧存 scripts/.prompter-steps/页-步.jpg,
供手机提词页的当前页预览随步进换帧(目录名要与 prompter_server.py 的 STEPS_DIR 一致,否则手机端拿到 404)。
改了分步页版面后重跑本脚本(整页缩略图另由 export_pages.py 管)。
依赖:python3 + playwright(chromium)。headless 实例 navigator.webdriver=true,deck 的提词上报自动关闭,不打扰演示。"""
from playwright.sync_api import sync_playwright
import json, pathlib, subprocess, tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
URL = (BASE / "index.html").as_uri()
OUT = BASE / "scripts" / ".prompter-steps"

FF_CSS = "*{animation-delay:0s !important;animation-duration:1ms !important;transition-duration:1ms !important;transition-delay:0s !important;}"

with tempfile.TemporaryDirectory(prefix="deck-export-steps-", dir=str(BASE / "scripts")) as staging_dir:
    staging = pathlib.Path(staging_dir)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={'width': 1980, 'height': 1114})
        pg.goto(URL)
        archived = pg.evaluate("""(() => Array.from(document.querySelectorAll('#stage .slide'))
          .filter(s => s.dataset.archived === '1').map(s => +s.dataset.page))()""")
        meta = pg.evaluate("""(() => Array.from(document.querySelectorAll('#stage .slide'))
          .filter(s => s.dataset.archived !== '1').map((s, i) => {
          const c = s.querySelector('.canvas');
          return { page: i + 1, steps: c && c.dataset.steps ? +c.dataset.steps : 0 };
        }))()""")
        count = 0
        for m in (x for x in meta if x['steps']):
            pg.goto("about:blank")
            pg.goto(URL + "#p%d" % m['page'])
            pg.evaluate("document.body.classList.add('present'); window.dispatchEvent(new Event('resize'))")
            pg.add_style_tag(content=FF_CSS)
            pg.wait_for_timeout(1600)  # 等 data-autostep 定时器走完,之后手动设 step 不再被它覆盖
            for s in range(0, m['steps'] + 1):
                pg.evaluate("document.querySelector('.slide.current .canvas').dataset.step = %d" % s)
                pg.wait_for_timeout(250)
                box = pg.evaluate("(() => { const r = document.querySelector('.slide.current .canvas').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()")
                raw = staging / ("%d-%d.raw.png" % (m['page'], s))
                dst = staging / ("%d-%d.jpg" % (m['page'], s))
                pg.screenshot(path=str(raw), clip=box)
                subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '70',
                                '-Z', '640', str(raw), '--out', str(dst)], capture_output=True, check=True)
                raw.unlink()
                count += 1
                print("✓ P%d 步 %d/%d" % (m['page'], s, m['steps']))
        b.close()

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        if old.is_file():
            old.unlink()
    for fresh in staging.glob("*.jpg"):
        fresh.replace(OUT / fresh.name)
    state = BASE / "scripts" / ".prompter-step-state.json"
    state_tmp = BASE / "scripts" / ".prompter-step-state.json.tmp"
    state_tmp.write_text(json.dumps({"archived": archived}), encoding="utf-8")
    state_tmp.replace(state)
print("共 %d 帧 → %s" % (count, OUT))

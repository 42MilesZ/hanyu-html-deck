import json
import pathlib
import re
import sys
import tempfile
import unittest
from urllib.parse import quote

from playwright.sync_api import sync_playwright


SKILL = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from create_deck import create  # noqa: E402


LONG_SCRIPT = "内容" * 600


SLIDES = f"""<template id="slides">
<section class="slide" data-slide-id="test-001" data-title="One" data-part="Start" data-outline="One">
  <div class="canvas"><p>One</p></div>
  <aside><div class="ns"><p>One</p></div><div class="nc"></div></aside>
</section>
<section class="slide" data-slide-id="test-002" data-title="Auto" data-part="Steps" data-outline="Auto">
  <div class="canvas" data-steps="1" data-step="0"><p>Auto</p></div>
  <aside><div class="ns"><p>{LONG_SCRIPT}</p></div><div class="nc"></div></aside>
</section>
<section class="slide" data-slide-id="test-003" data-title="Legacy marker" data-part="Steps" data-outline="Legacy marker">
  <div class="canvas" data-steps="1" data-step="0" data-manualstep="1"><p>Manual</p></div>
  <aside><div class="ns"><p>Manual</p></div><div class="nc"></div></aside>
</section>
""" + "".join(
    f"""<section class="slide" data-slide-id="test-{i:03d}" data-title="Short {i}" data-part="Details" data-outline="Short {i}">
  <div class="canvas"><p>Short {i}</p></div>
  <aside><div class="ns"><p>Short {i}</p></div><div class="nc"></div></aside>
</section>
"""
    for i in range(4, 11)
) + "</template>"


class DeckStepNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.deck = pathlib.Path(cls.temp.name) / "deck"
        create(cls.deck)
        index = cls.deck / "index.html"
        html = index.read_text(encoding="utf-8")
        html, count = re.subn(r'<template id="slides">[\s\S]*?</template>', SLIDES, html, count=1)
        if count != 1:
            raise AssertionError("slides template not found")
        index.write_text(html, encoding="utf-8")
        cls.url = "file://" + quote(str(index), safe="/~")
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.temp.cleanup()

    def new_page(self, page_number, viewport=None, without_resize_observer=False):
        page = self.browser.new_page(viewport=viewport or {"width": 1280, "height": 800})
        if without_resize_observer:
            page.add_init_script(
                "Object.defineProperty(window, 'ResizeObserver', {value: undefined, configurable: true})"
            )
        page.goto(f"{self.url}#p{page_number}", wait_until="load")
        return page

    def test_timeline_clamps_short_pages_to_32px(self):
        page = self.new_page(1, {"width": 1920, "height": 1080})
        page.wait_for_timeout(620)
        width = page.locator(".tl-page.current").evaluate("el => el.getBoundingClientRect().width")
        self.assertAlmostEqual(width, 32, delta=0.5)
        page.close()

    def test_timeline_degrades_without_overlap_when_track_is_too_narrow(self):
        page = self.new_page(1, {"width": 520, "height": 800})
        page.wait_for_timeout(620)
        widths = page.evaluate(
            """() => ({
              current: document.querySelector('.tl-page.current').getBoundingClientRect().width,
              track: document.querySelector('#tlIn').getBoundingClientRect().width
            })"""
        )
        self.assertLess(widths["current"], 32)
        self.assertAlmostEqual(widths["current"], widths["track"] / 10, delta=0.5)
        page.close()

    def test_timeline_recovers_after_resize_while_raw_view_hides_the_panel(self):
        page = self.new_page(1, {"width": 1920, "height": 1080})
        page.wait_for_timeout(620)
        page.keyboard.press("r")
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(80)
        page.keyboard.press("r")
        page.wait_for_timeout(620)
        width = page.locator(".tl-page.current").evaluate("el => el.getBoundingClientRect().width")
        self.assertAlmostEqual(width, 32, delta=0.5)
        page.close()

    def test_timeline_resize_fallback_recovers_after_raw_view(self):
        page = self.new_page(
            1, {"width": 1920, "height": 1080}, without_resize_observer=True
        )
        page.wait_for_timeout(620)
        page.keyboard.press("r")
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(80)
        page.keyboard.press("r")
        page.wait_for_timeout(620)
        width = page.locator(".tl-page.current").evaluate("el => el.getBoundingClientRect().width")
        self.assertAlmostEqual(width, 32, delta=0.5)
        page.close()

    def test_timeline_reports_zero_total_for_empty_scripts(self):
        page = self.new_page(1)
        page.evaluate(
            """() => {
              for (let i = 1; i <= 10; i += 1) {
                localStorage.setItem('hanyu-html-deck.v2.s.' + i, '<p><br></p>');
              }
              location.reload();
            }"""
        )
        page.wait_for_load_state("load")
        self.assertEqual(page.locator("#tlSec").inner_text(), "0:00")
        self.assertEqual(page.locator("#tlTot").inner_text(), "0:00")
        page.close()

    def test_unmarked_steps_auto_advance_and_arrows_change_pages(self):
        page = self.new_page(2)
        page.wait_for_timeout(520)
        self.assertEqual(page.locator(".slide.current").get_attribute("data-page"), "2")
        self.assertEqual(page.locator(".slide.current .canvas").get_attribute("data-step"), "1")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(80)
        self.assertEqual(page.locator(".slide.current").get_attribute("data-page"), "3")
        self.assertEqual(page.evaluate("location.hash"), "#p3")
        page.close()

    def test_arrow_does_not_wait_for_default_auto_step(self):
        page = self.new_page(2)
        page.wait_for_timeout(40)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(80)
        self.assertEqual(page.locator(".slide.current").get_attribute("data-page"), "3")
        page.close()

    def test_legacy_manual_marker_does_not_consume_arrows(self):
        page = self.new_page(3)
        page.wait_for_timeout(520)
        self.assertEqual(page.locator(".slide.current .canvas").get_attribute("data-step"), "1")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(80)
        self.assertEqual(page.evaluate("location.hash"), "#p4")
        page.close()

    def test_step_export_freeze_stops_default_auto_timer(self):
        page = self.new_page(2)
        page.wait_for_timeout(40)
        page.evaluate("window.hanyuFreezeStepsForExport(); document.querySelector('.slide.current .canvas').dataset.step = '0'")
        page.wait_for_timeout(520)
        canvas = page.locator(".slide.current .canvas")
        self.assertEqual(canvas.get_attribute("data-stepfreeze"), "1")
        self.assertEqual(canvas.get_attribute("data-step"), "0")
        page.close()

    def test_server_export_waits_for_latest_script_patch(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 800})
        store = json.loads((self.deck / "deck-content.json").read_text(encoding="utf-8"))
        page.add_init_script(
            """
            window.__requests = [];
            window.__alerts = [];
            window.alert = message => window.__alerts.push(message);
            window.EventSource = class { addEventListener() {} };
            const store = %s;
            const response = body => Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(body)});
            window.fetch = (url, options = {}) => {
              const target = String(url);
              if (target.includes('/content/patch')) {
                window.__requests.push('patch');
                return response({ok: true, fieldRevision: 1, storeRevision: 1});
              }
              if (target.includes('/content')) return response(store);
              if (target.includes('/export')) {
                window.__requests.push('export');
                return response({ok: true});
              }
              return response({ok: true});
            };
            """ % json.dumps(store, ensure_ascii=False)
        )
        page.goto(f"{self.url}#p1", wait_until="load")
        page.locator("#edScript").evaluate(
            "el => { el.innerHTML += '<p>latest</p>'; el.dispatchEvent(new InputEvent('input', {bubbles: true})); }"
        )
        page.locator('#exWrap > button[data-act="export"]').evaluate("el => el.click()")
        page.locator('#exMenu button[data-ex="send"]').evaluate("el => el.click()")
        page.wait_for_function("window.__requests.includes('export')")
        self.assertEqual(page.evaluate("window.__requests.slice(-2)"), ["patch", "export"])
        page.close()

    def test_browser_blocks_editing_when_a_slide_id_is_missing(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        source = (SKILL / "assets" / "hanyu-html-deck" / "index.html").read_text(encoding="utf-8")
        source = source.replace(' data-slide-id="slide-001"', "", 1)
        page.set_content(source, wait_until="load")
        self.assertIn("Deck structure error", page.locator("body").inner_text())
        self.assertIn("Page 1 is missing data-slide-id.", page.locator("body").inner_text())
        self.assertTrue(any("missing data-slide-id" in error for error in errors))
        self.assertEqual(page.locator("#edScript").count(), 0)
        page.close()


if __name__ == "__main__":
    unittest.main()

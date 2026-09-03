import importlib.util
import json
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "assets" / "hanyu-html-deck" / "index.html"
SERVER = ROOT / "assets" / "hanyu-html-deck" / "scripts" / "prompter_server.py"
PHONE = ROOT / "assets" / "hanyu-html-deck" / "scripts" / "prompter-phone.html"


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_slide_structure_is_writeback_safe(self):
        self.assertEqual(self.html.count('<section class="slide"'), 6)
        self.assertEqual(
            self.html.count('<section class="slide"'),
            self.html.count('<div class="ns">'),
        )
        self.assertEqual(
            self.html.count('<section class="slide"'),
            self.html.count('<div class="nc">'),
        )
        self.assertNotIn("</div>\n  \n  <aside>", self.html)

    def test_product_video_story_order(self):
        titles = re.findall(r'<section class="slide"[^>]*data-title="([^"]+)"', self.html)
        self.assertEqual(
            titles,
            [
                "本地演示台",
                "AI 生成整场演示",
                "在页面上直接改",
                "手机提词与遥控",
                "讲完立即交付",
                "从第一版到正式上台",
            ],
        )

    def test_agreed_product_labels(self):
        for label in (
            "Export script",
            "Export page images",
            "Export PDF",
            "Export standalone HTML",
            "Use 1:1 pixels",
            "Add revision notes, context, or personal reminders…",
            "chars/min",
        ):
            self.assertIn(label, self.html)
        self.assertNotIn("Copy changed notes", self.html)
        self.assertNotIn('data-ex="diff-notes"', self.html)
        self.assertNotIn("function exportChangedNotes()", self.html)
        self.assertNotIn("function copyOut(", self.html)
        self.assertNotIn(">改动的批注<", self.html)
        self.assertNotIn(">全部批注<", self.html)

    def test_export_menu_items_all_explained(self):
        menu = self.html.split('<div id="exMenu">', 1)[1].split("</div>", 1)[0]
        items = [line for line in menu.splitlines() if "<button" in line]
        self.assertEqual(len(items), 5)
        for item in items:
            self.assertIn("data-tip=", item)

    def test_non_content_tooltips_default_to_english(self):
        phone = PHONE.read_text(encoding="utf-8")
        attributes = []
        for source in (self.html, phone):
            attributes.extend(
                re.findall(
                    r'(?:data-tip|aria-label|(?<!data-)title)="([^"]*)"',
                    source,
                )
            )
        for value in attributes:
            self.assertIsNone(re.search(r"[\u4e00-\u9fff]", value), value)

    def test_speaker_scripts_are_bilingual(self):
        scripts = re.findall(r'<div class="ns">(.*?)</div>', self.html, re.S)
        self.assertEqual(len(scripts), 6)
        for script in scripts:
            self.assertRegex(script, r"[\u4e00-\u9fff]")
            self.assertRegex(script, r"[A-Za-z]{3,}")

    def test_key_slide_content_is_bilingual(self):
        cover = self.html.split('<div class="cover-features">', 1)[1].split(
            "</div>\n    </div>", 1
        )[0]
        self.assertEqual(cover.count("<small>"), 4)
        self.assertGreaterEqual(self.html.count('<div class="v-caption"><span>'), 4)
        for translation in (
            "AI-made decks, ready to present.",
            "One prompt. A complete presentation.",
            "Edit directly on the canvas.",
            "Your phone becomes the prompter.",
            "Ready to deliver.",
            "Make AI presentations work better.",
        ):
            self.assertIn(translation, self.html)

    def test_cover_has_no_vertical_divider(self):
        self.assertNotIn('<div class="v-signal"></div>', self.html)
        self.assertNotIn(".v-cover .v-signal", self.html)

    def test_cover_product_name_is_bold(self):
        self.assertIn('<span class="cover-product">HTML&nbsp;Deck</span>', self.html)
        rule = self.html.split(".v-cover .cover-product {", 1)[1].split("}", 1)[0]
        self.assertRegex(rule, r"font-weight:\s*600\b")

    def test_cover_features_do_not_rise_above_title(self):
        title = self.html.split(".v-cover .cover-thesis {", 1)[1].split("}", 1)[0]
        features = self.html.split(".v-cover .cover-features {", 1)[1].split("}", 1)[0]
        title_top = int(re.search(r"top:\s*(\d+)px", title).group(1))
        features_top = int(re.search(r"top:\s*(\d+)px", features).group(1))
        self.assertGreaterEqual(features_top, title_top)

    def test_english_slide_content_uses_light_weight(self):
        selectors = (
            ".v-kicker",
            ".v-title::after",
            ".v-caption small",
            ".v-cover .cover-thesis::after",
            ".v-cover .cover-feature span small",
            ".v-sheet .sheet-type",
            ".v-phone-body .phone-page",
            ".v-output",
            ".v-end .end-line::after",
            ".v-end .end-name",
        )
        for selector in selectors:
            rules = re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", self.html)
            self.assertTrue(
                any(re.search(r"font(?::-weight)?:\s*200\b", rule) for rule in rules),
                selector,
            )

    def test_reusable_content_patterns_use_two_weights(self):
        patterns = self.html.split("示例页样式", 1)[1].split("产品短片版式", 1)[0]
        self.assertNotRegex(patterns, r"font(?:-weight)?:\s*300")

    def test_state_is_separate_and_deck_scoped(self):
        self.assertIn("DECK.key + '.ui.panelExpanded'", self.html)
        self.assertIn("DECK.key + '.ui.notesDrawerOpen'", self.html)
        self.assertIn("localStorage.setItem(PANEL_KEY", self.html)
        self.assertIn("localStorage.setItem(DRAWER_KEY", self.html)

    def test_bottom_panel_controls(self):
        toolbar = self.html.split('<div id="toolbar">', 1)[1].split(
            '<div id="stage">', 1
        )[0]
        notes_head = self.html.split('<div id="notesHead">', 1)[1].split(
            '<div id="nsCols">', 1
        )[0]
        script_col = self.html.split('<div class="col script">', 1)[1].split(
            '<div class="col comm">', 1
        )[0]
        comm_col = self.html.split('<div class="col comm">', 1)[1].split(
            "</div>\n  </div>", 1
        )[0]

        self.assertNotIn('data-act="drawer"', toolbar)
        self.assertIn('id="rateBtn"', notes_head)
        self.assertIn('id="saveState"', notes_head)
        self.assertIn('id="syncLed"', notes_head)
        self.assertIn('id="syncText"', notes_head)
        self.assertNotIn('class="rt tip-up"', notes_head)
        for moved in ('id="btnHist"', 'id="btnDrawer"'):
            self.assertNotIn(moved, notes_head)
            self.assertIn(moved, script_col)
        self.assertNotIn('id="syncLed"', script_col)
        self.assertIn('id="btnHistComm"', comm_col)
        self.assertNotIn("btnSeed", self.html)

    def test_write_back_is_automatic_with_status_led(self):
        self.assertIn("function seedNow()", self.html)
        self.assertIn("function scheduleSeed()", self.html)
        self.assertIn("var WRITEBACK_DELAY = 3000;", self.html)
        self.assertIn("setTimeout(seedNow, WRITEBACK_DELAY)", self.html)
        self.assertIn("syncText.textContent", self.html)
        self.assertIn("Saved in this browser", self.html)
        self.assertIn("var writeFlights = {};", self.html)
        self.assertIn("!writeFlights[key]", self.html)
        self.assertIn("fragOfPage(c.i, c.ed) === frag", self.html)
        self.assertNotIn("saveTimer = setTimeout", self.html)
        self.assertIn("syncLed", self.html)
        self.assertNotIn("saveAsDefault", self.html)

    def test_empty_edits_and_rejections_reach_terminal_states(self):
        self.assertIn("return ed.canon(stored) || '<p><br></p>';", self.html)
        self.assertIn("failed ? 'Error'", self.html)
        self.assertIn("rejected = d.err || 'Unknown write-back error'", self.html)
        self.assertIn("else if (rejected) setLed(false, rejected, false, false, true)", self.html)

    def test_pasted_note_markup_is_sanitized_before_writeback(self):
        self.assertIn("function cleanNoteHtml(html)", self.html)
        self.assertIn("if (!NOTE_TAGS[n.tagName])", self.html)
        self.assertIn("if (a.name !== 'class') n.removeAttribute(a.name)", self.html)

    def test_view_and_panel_changes_have_motion(self):
        self.assertIn("body.notes-anim #stage", self.html)
        self.assertIn("new ResizeObserver", self.html)
        self.assertIn("#overview.open", self.html)
        self.assertIn("--ease-view: cubic-bezier(.65,0,.35,1)", self.html)
        self.assertIn("body.ov #stage .slide.current", self.html)
        self.assertIn("function beginViewAnim()", self.html)
        self.assertIn("}, 560);", self.html)
        self.assertIn("go(i, false, true)", self.html)
        self.assertIn("requestAnimationFrame(function () { setView('default'); })", self.html)
        self.assertIn("prefers-reduced-motion: reduce", self.html)

    def test_overview_thumbnail_scale_ignores_entrance_transform(self):
        overview = self.html.split("function buildOverview()", 1)[1].split(
            "// ===== 讲稿与备注导出 =====", 1
        )[0]
        self.assertIn("tw.clientWidth / 1920", overview)
        self.assertNotRegex(overview, r"tw\.getBoundingClientRect\s*\(")

    def test_timeline_preview_uses_the_live_canvas(self):
        timeline = self.html.split("// ===== 时间轴悬停预览", 1)[1].split(
            "// ===== 画布就地编辑", 1
        )[0]
        self.assertIn('class="previewCanvas"', self.html)
        self.assertIn("querySelector('.canvas').cloneNode(true)", timeline)
        self.assertIn("tlPvCanvas.clientWidth / 1920", timeline)
        self.assertNotIn("/thumbs/", timeline)

    def test_server_exports_flush_content_store_before_starting(self):
        export = self.html.split("function exportServer(kind)", 1)[1].split(
            "document.addEventListener('click'", 1
        )[0]
        self.assertLess(export.index("saveNote();"), export.index("fetch(api('/export')"))
        self.assertLess(export.index("seedNow();"), export.index("fetch(api('/export')"))
        self.assertLess(export.index("return seedChain;"), export.index("fetch(api('/export')"))
        self.assertIn("if (dirtyPages().length) throw new Error", export)
        self.assertIn("Export stopped:", export)

    def test_rate_button_uses_the_shared_muted_background(self):
        rule = re.search(r"#rateBtn\s*\{([^}]*)\}", self.html)
        self.assertIsNotNone(rule)
        self.assertIn("background: var(--muted-bg)", rule.group(1))

    def test_fixed_menus_are_not_trapped_by_the_notes_panel(self):
        rule = re.search(r"#notesPanel\s*\{([^}]*)\}", self.html)
        self.assertIsNotNone(rule)
        self.assertIn("transform: none", rule.group(1))
        self.assertNotIn("transform: translateY(0)", rule.group(1))

    def test_history_is_separate_per_column(self):
        self.assertIn("hkey: DECK.key + '.h.'", self.html)
        self.assertIn("hkey: DECK.key + '.hc.'", self.html)
        self.assertIn("function snapHist(i, ed)", self.html)

    def test_rate_is_a_five_step_multiplier_menu(self):
        self.assertIn("var RATE_BASE = 210;", self.html)
        mults = re.search(r"var RATE_MULTS = \[([^\]]+)\];", self.html)
        self.assertIsNotNone(mults)
        self.assertEqual(mults.group(1), "0.6, 0.8, 1.0, 1.3, 1.6")
        self.assertIn("Math.max(s * rate / RATE_BASE, 4)", self.html)
        self.assertIn("function timelineWidths(weights, trackWidth)", self.html)
        self.assertNotIn("180 / rate", self.html)

    def test_outline_and_timeline_use_structural_slide_metadata(self):
        self.assertIn('id="outlineDrawer"', self.html)
        self.assertIn("function buildOutline()", self.html)
        self.assertIn("slides[source].dataset.part || 'Pages'", self.html)
        self.assertEqual(self.html.count('data-slide-id="'), 6)
        self.assertEqual(self.html.count('data-part="'), 6)
        self.assertEqual(self.html.count('data-outline="'), 6)
        self.assertIn("var TL_PAGE_MIN_PX = 32", self.html)

    def test_browser_refuses_missing_or_duplicate_stable_ids(self):
        self.assertIn("function assertStableSlideIds()", self.html)
        self.assertIn("Page ' + (i + 1) + ' is missing data-slide-id.", self.html)
        self.assertIn("Duplicate data-slide-id: ' + id", self.html)
        self.assertIn("assertStableSlideIds();", self.html)
        self.assertIn("function slideId(i) { return slides[i].dataset.slideId; }", self.html)
        self.assertNotIn("slides[i].dataset.slideId || ('slide-'", self.html)

    def test_no_public_transport(self):
        lowered = self.html.lower()
        self.assertNotIn("mqtt", lowered)
        self.assertNotIn("broker.emqx.io", lowered)
        phone = (
            ROOT
            / "assets"
            / "hanyu-html-deck"
            / "scripts"
            / "prompter-phone.html"
        ).read_text(encoding="utf-8").lower()
        self.assertNotIn("mqtt", phone)
        self.assertNotIn("wss://", phone)

    def test_every_referenced_id_exists(self):
        """JS 取的 id 必须真实存在：少一个就整页白屏，而字符串断言查不出来。"""
        declared = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', self.html))
        used = set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", self.html))
        self.assertTrue(used)
        self.assertEqual(used - declared, set())


class GeneratorTests(unittest.TestCase):
    def test_create_deck(self):
        spec = importlib.util.spec_from_file_location(
            "create_deck", ROOT / "scripts" / "create_deck.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / "demo"
            module.create(target)
            for name in ("index.html", "启动本地演示台.command", "deck-content.json", "LICENSE"):
                self.assertTrue((target / name).exists(), name)
            self.assertTrue((target / "scripts" / "prompter_server.py").exists())
            self.assertTrue((target / "scripts" / "deck_content.py").exists())
            self.assertTrue((target / "fonts" / "NotoSansSC.woff2").exists())
            for internal in ("AGENTS.md", "README.md", "THIRD_PARTY_NOTICES.md"):
                self.assertFalse((target / internal).exists(), internal)
            junk = [
                str(p.relative_to(target))
                for p in target.rglob("*")
                if p.name == "__pycache__" or p.suffix == ".pyc"
            ]
            self.assertEqual(junk, [])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SERVER.parent))
        spec = importlib.util.spec_from_file_location("prompter_server", SERVER)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_qr_svg_is_generated_offline(self):
        image = self.module.qrcode.make(
            "http://192.168.1.2:8123/p",
            image_factory=self.module.qrcode.image.svg.SvgPathImage,
        )
        import io

        output = io.BytesIO()
        image.save(output)
        self.assertIn(b"<svg", output.getvalue())

    def test_local_ip_filter(self):
        for ip in self.module.local_ips():
            self.assertFalse(ip.startswith("127."))
            self.assertFalse(ip.startswith("198.18."))

    def test_note_markup_whitelist_rejects_injection(self):
        mod = self.module
        for payload in (
            '<p><img src=x onerror="fetch(1)"></p>',
            '<p><iframe src="http://evil"></iframe></p>',
            "<p><svg onload=alert(1)></svg></p>",
            '</section><section class="slide"><p>x</p>',
            '<p contenteditable="true">x</p>',
            "<p>x</p><!-- c -->",
            "<p><script>alert(1)</script></p>",
            # 属性值里塞 > 夹带事件属性:正则式校验会漏,浏览器当真属性执行
            '<p class="class>" onclick=alert(1)>hi</p>',
            # 未闭合标签:分词器看不到就等于白名单失效,落盘后会把区块定位算坏
            '<p>ok</p><div class="x"',
            # 区块边界标记落进属性值,会让写回时的区间计算错位
            '<p class="a</div>">x</p>',
        ):
            ok, _ = mod.check_markup(payload, mod.NOTE_TAGS, mod.NOTE_ATTRS)
            self.assertFalse(ok, payload)
        for payload in (
            '<p class="o-main">正常<b>加粗</b><br>换行</p>',
            '<p><br></p>',
            "<p>讲到 a &lt; b 这种写法</p>",
        ):
            ok, why = mod.check_markup(payload, mod.NOTE_TAGS, mod.NOTE_ATTRS)
            self.assertTrue(ok, payload + " → " + why)

    def test_template_note_markup_is_writeback_safe(self):
        mod = self.module
        html = TEMPLATE.read_text(encoding="utf-8")
        fragments = re.findall(r'<div class="n[sc]">(.*?)</div>', html, re.S)
        self.assertEqual(len(fragments), 12)
        for fragment in fragments:
            ok, why = mod.check_markup(fragment, mod.NOTE_TAGS, mod.NOTE_ATTRS)
            self.assertTrue(ok, fragment + " → " + why)

    def test_export_notifications_are_english(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('notify("Hanyu HTML Deck", "Export complete")', source)
        self.assertIn('notify("Hanyu HTML Deck · Export failed"', source)

    def test_preview_export_refreshes_pages_and_steps_without_notification(self):
        mod = self.module
        completed = mod.subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(mod.subprocess, "run", return_value=completed) as run, \
             mock.patch.object(mod, "broadcast") as broadcast, \
             mock.patch.object(mod, "notify") as notify:
            mod.export_busy = True
            mod.run_export("previews")
        scripts = [pathlib.Path(call.args[0][1]).name for call in run.call_args_list]
        self.assertEqual(scripts, ["export_pages.py", "export_steps.py"])
        self.assertEqual(broadcast.call_args.args[0], "preview")
        self.assertGreater(broadcast.call_args.args[1]["rev"], 0)
        notify.assert_not_called()
        self.assertFalse(mod.export_busy)

    def test_phone_preview_reloads_and_falls_back_from_missing_step_frame(self):
        phone = PHONE.read_text(encoding="utf-8")
        html = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("events.addEventListener('preview'", phone)
        self.assertIn("previewRev = Math.max", phone)
        self.assertIn("this.dataset.fallback", phone)
        self.assertIn("this.src = fallback", phone)
        self.assertIn("body: JSON.stringify({ what: 'previews' })", html)

    def test_canvas_markup_whitelist(self):
        mod = self.module
        ok, why = mod.check_markup(
            '<div class="x"><img src="a.png" alt=""><svg viewBox="0 0 24 24">'
            '<path d="M0 0" stroke-width="1.5"/></svg></div>',
            mod.CANVAS_TAGS,
            mod.CANVAS_ATTRS,
        )
        self.assertTrue(ok, why)
        for payload in (
            '<div onclick="x()"></div>',
            '<a href="javascript:alert(1)">x</a>',
            "<object data=x></object>",
            '<img src="data:text/html,<script>1</script>">',
            '<img src="a.png" alt="class>" onerror=alert(1)>',
            '<div style="x>" onmouseover=alert(1)>x</div>',
            '<a href="javascript&#58;alert(1)">x</a>',
            "<a href='java\tscript:alert(1)'>x</a>",
        ):
            ok, _ = mod.check_markup(payload, mod.CANVAS_TAGS, mod.CANVAS_ATTRS)
            self.assertFalse(ok, payload)

    def test_access_control_defaults_to_deny(self):
        mod = self.module
        source = SERVER.read_text(encoding="utf-8")
        allow_body = source.split("def allow(self, path):", 1)[1].split("def guard", 1)[0]
        self.assertIn('return False, "未知的请求路径"', allow_body)
        self.assertNotIn('return True, ""\n\n    def', allow_body)
        self.assertTrue(mod.MAX_SSE_CLIENTS <= 16)

    def test_local_boundaries_are_declared(self):
        mod = self.module
        for path in ("/canvas", "/seed", "/export", "/notes", "/flip", "/info"):
            self.assertIn(path, mod.LOCAL_ONLY)
        hosts = mod.allowed_hosts()
        self.assertIn("127.0.0.1:%d" % mod.PORT, hosts)
        self.assertNotIn("evil.example:%d" % mod.PORT, hosts)
        origins = mod.allowed_origins()
        self.assertIn("null", origins)
        self.assertNotIn("https://evil.example", origins)
        self.assertGreaterEqual(len(mod.TOKEN), 16)

    def test_write_side_requires_token(self):
        """只看回环挡不住浏览器里伪装成 Origin: null 的网页,写侧必须要凭据。"""
        source = SERVER.read_text(encoding="utf-8")
        allow_body = source.split("def allow(self, path):", 1)[1].split("def guard", 1)[0]
        local_branch = allow_body.split("if path in LOCAL_ONLY:", 1)[1].split("if path in PHONE_PATHS", 1)[0]
        self.assertIn("token_ok()", local_branch)

    def test_token_anchor_exists_and_not_read_from_url(self):
        """凭据靠服务写进文件:macOS 的 open 会丢掉 file:// URL 的 query,不能从地址取。

        不断言锚点为空——服务运行期间工作副本里本就带着本次运行的凭据。
        """
        html = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(html, r"var TOKEN = '[^']*'; /\* HANYU_TOKEN \*/")
        self.assertNotIn("location.search.match", html)

    def test_stamp_token_writes_and_clears(self):
        mod = self.module
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "index.html"
            path.write_text("var TOKEN = ''; /* HANYU_TOKEN */\n", encoding="utf-8")
            original = mod.INDEX_FILE
            mod.INDEX_FILE = str(path)
            try:
                self.assertTrue(mod.stamp_token("abc-123_XY"))
                self.assertIn("var TOKEN = 'abc-123_XY'; /* HANYU_TOKEN */", path.read_text(encoding="utf-8"))
                self.assertTrue(mod.stamp_token(""))
                self.assertIn("var TOKEN = ''; /* HANYU_TOKEN */", path.read_text(encoding="utf-8"))
                path.write_text("var TOKEN = '';\n", encoding="utf-8")
                self.assertFalse(mod.stamp_token("abc"))
            finally:
                mod.INDEX_FILE = original

    def test_launcher_opens_deck_after_service_answers(self):
        """凭据在文件里:必须等服务写好凭据、开始应答,再打开页面。"""
        launcher = (ROOT / "assets" / "hanyu-html-deck" / "启动本地演示台.command").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("?t=", launcher)
        self.assertIn("curl", launcher)
        self.assertIn("--noproxy", launcher)
        self.assertIn('/usr/bin/open "$PWD/index.html"', launcher)

    def test_send_version_clears_token(self):
        """发送版可能在服务运行时导出,那时源文件里带着本机凭据。"""
        source = (ROOT / "assets" / "hanyu-html-deck" / "scripts" / "build_send.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("HANYU_TOKEN", source)
        self.assertIn("写回凭据没清空", source)

    def test_service_does_not_hand_out_token_bearing_urls(self):
        mod = self.module
        self.assertTrue(all(mod.TOKEN not in url for url in mod.display_urls()))
        self.assertTrue(all("t=" + mod.TOKEN in url for url in mod.phone_urls()))
        source = SERVER.read_text(encoding="utf-8")
        info_branch = source.split('elif path == "/info":', 1)[1].split('elif path == "/qr.svg"', 1)[0]
        self.assertIn("display_urls()", info_branch)
        self.assertNotIn("phone_urls()", info_branch)

    def test_find_block_is_balanced(self):
        mod = self.module
        doc = '<aside><div class="nc"><div class="x">内层</div><p>正文</p></div></aside>'
        start, end, _ = mod.find_block(doc, "nc", 1)
        self.assertEqual(doc[start:end], '<div class="x">内层</div><p>正文</p>')

    def test_save_seed_rejects_page_count_mismatch(self):
        mod = self.module
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "index.html"
            path.write_text(
                '<section class="slide"><aside><div class="ns"><p>a</p></div></aside></section>',
                encoding="utf-8",
            )
            original = mod.INDEX_FILE
            mod.INDEX_FILE = str(path)
            try:
                ok, _ = mod.save_seed(1, "<p>b</p>", "ns", 5)
                self.assertFalse(ok)
                self.assertIn("<p>a</p>", path.read_text(encoding="utf-8"))
                ok, why = mod.save_seed(1, "<p>b</p>", "ns", 1)
                self.assertTrue(ok, why)
                self.assertIn("<p>b</p>", path.read_text(encoding="utf-8"))
            finally:
                mod.INDEX_FILE = original


class SkillEvalSchemaTests(unittest.TestCase):
    def test_eval_schema(self):
        data = json.loads(
            (ROOT / "support" / "evals" / "evals.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(data["evals"]), 3)
        for item in data["evals"]:
            self.assertIn("prompt", item)
            self.assertIn("expected_output", item)


if __name__ == "__main__":
    unittest.main()

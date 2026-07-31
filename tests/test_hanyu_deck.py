import importlib.util
import json
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "hanyu-html-deck" / "index.html"
SERVER = ROOT / "assets" / "hanyu-html-deck" / "scripts" / "prompter_server.py"


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
        titles = re.findall(r'<section class="slide" data-title="([^"]+)">', self.html)
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
            "导出讲稿",
            "复制改动的备注",
            "导出每页图片",
            "导出 PDF",
            "导出单独发送版",
            "切换为 1:1 像素",
            "写下本页的修改意见、补充说明或个人备注……",
        ):
            self.assertIn(label, self.html)
        self.assertNotIn(">改动的批注<", self.html)
        self.assertNotIn(">全部批注<", self.html)

    def test_export_menu_items_all_explained(self):
        menu = self.html.split('<div id="exMenu">', 1)[1].split("</div>", 1)[0]
        items = [line for line in menu.splitlines() if "<button" in line]
        self.assertEqual(len(items), 6)
        for item in items:
            self.assertIn("data-tip=", item)

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
        self.assertNotIn('class="rt tip-up"', notes_head)
        for moved in ('id="btnHist"', 'id="btnDrawer"', 'id="syncLed"'):
            self.assertNotIn(moved, notes_head)
            self.assertIn(moved, script_col)
        self.assertIn('id="btnHistComm"', comm_col)
        self.assertNotIn("btnSeed", self.html)

    def test_write_back_is_automatic_with_status_led(self):
        self.assertIn("function seedNow()", self.html)
        self.assertIn("function scheduleSeed()", self.html)
        self.assertIn("syncLed", self.html)
        self.assertNotIn("saveAsDefault", self.html)

    def test_history_is_separate_per_column(self):
        self.assertIn("hkey: DECK.key + '.h.'", self.html)
        self.assertIn("hkey: DECK.key + '.hc.'", self.html)
        self.assertIn("function snapHist(i, ed)", self.html)

    def test_rate_is_a_five_step_multiplier_menu(self):
        self.assertIn("var RATE_BASE = 210;", self.html)
        mults = re.search(r"var RATE_MULTS = \[([^\]]+)\];", self.html)
        self.assertIsNotNone(mults)
        self.assertEqual(mults.group(1), "0.6, 0.8, 1.0, 1.3, 1.6")
        self.assertIn("RATE_MIN / rate * 100", self.html)
        self.assertNotIn("180 / rate", self.html)

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
            for name in (
                "index.html",
                "启动本地演示台.command",
                "README.md",
                "LICENSE",
                "THIRD_PARTY_NOTICES.md",
            ):
                self.assertTrue((target / name).exists(), name)
            self.assertTrue((target / "scripts" / "prompter_server.py").exists())
            self.assertTrue((target / "fonts" / "NotoSansSC.woff2").exists())
            junk = [
                str(p.relative_to(target))
                for p in target.rglob("*")
                if p.name == "__pycache__" or p.suffix == ".pyc"
            ]
            self.assertEqual(junk, [])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
            "<p>讲到 a &lt; b 这种写法</p>",
        ):
            ok, why = mod.check_markup(payload, mod.NOTE_TAGS, mod.NOTE_ATTRS)
            self.assertTrue(ok, payload + " → " + why)

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
        data = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["evals"]), 3)
        for item in data["evals"]:
            self.assertIn("prompt", item)
            self.assertIn("expected_output", item)


if __name__ == "__main__":
    unittest.main()

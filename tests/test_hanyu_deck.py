import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "hanyu-deck" / "template.html"
SERVER = ROOT / "assets" / "hanyu-deck" / "scripts" / "prompter_server.py"


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_slide_structure_is_writeback_safe(self):
        self.assertGreaterEqual(self.html.count('<section class="slide"'), 8)
        self.assertEqual(
            self.html.count('<section class="slide"'),
            self.html.count('<div class="ns">'),
        )
        self.assertEqual(
            self.html.count('<section class="slide"'),
            self.html.count('<div class="nc">'),
        )
        self.assertNotIn("</div>\n  \n  <aside>", self.html)

    def test_agreed_product_labels(self):
        for label in (
            "导出讲稿",
            "复制改动的备注",
            "原尺寸（1:1）",
            "写下本页的修改意见、补充说明或个人备注……",
        ):
            self.assertIn(label, self.html)
        self.assertNotIn(">改动的批注<", self.html)
        self.assertNotIn(">全部批注<", self.html)

    def test_state_is_separate_and_deck_scoped(self):
        self.assertIn("DECK.key + '.ui.panelExpanded'", self.html)
        self.assertIn("DECK.key + '.ui.notesDrawerOpen'", self.html)
        self.assertIn("localStorage.setItem(PANEL_KEY", self.html)
        self.assertIn("localStorage.setItem(DRAWER_KEY", self.html)

    def test_bottom_header_controls(self):
        toolbar = self.html.split('<div id="toolbar">', 1)[1].split(
            '<div id="stage">', 1
        )[0]
        notes_head = self.html.split('<div id="notesHead">', 1)[1].split(
            '<div id="nsCols">', 1
        )[0]
        self.assertNotIn('data-act="drawer"', toolbar)
        self.assertIn('id="btnDrawer"', notes_head)
        self.assertLess(notes_head.index('id="btnSeed"'), notes_head.index('id="btnHist"'))
        self.assertLess(notes_head.index('id="btnHist"'), notes_head.index('id="btnDrawer"'))
        self.assertEqual(notes_head.count('class="rt tip-up"'), 3)

    def test_no_public_transport(self):
        lowered = self.html.lower()
        self.assertNotIn("mqtt", lowered)
        self.assertNotIn("broker.emqx.io", lowered)
        phone = (
            ROOT
            / "assets"
            / "hanyu-deck"
            / "scripts"
            / "prompter-phone.html"
        ).read_text(encoding="utf-8").lower()
        self.assertNotIn("mqtt", phone)
        self.assertNotIn("wss://", phone)


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
            self.assertTrue((target / "index.html").exists())
            self.assertTrue((target / "启动 Hanyu Deck.command").exists())
            self.assertTrue((target / "scripts" / "prompter_server.py").exists())
            self.assertTrue((target / "README.md").exists())


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


class SkillEvalSchemaTests(unittest.TestCase):
    def test_eval_schema(self):
        data = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["evals"]), 3)
        for item in data["evals"]:
            self.assertIn("prompt", item)
            self.assertIn("expected_output", item)


if __name__ == "__main__":
    unittest.main()

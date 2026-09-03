import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
DECK = ROOT / "assets" / "hanyu-html-deck"
SERVER = DECK / "scripts" / "prompter_server.py"
sys.path.insert(0, str(DECK / "scripts"))

from deck_content import ensure_store, read_store  # noqa: E402


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SharedGeneratorContractTests(unittest.TestCase):
    def test_generated_deck_is_clean_and_licensed(self):
        generator = load_module("shared_create_deck", ROOT / "scripts" / "create_deck.py")
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / "deck"
            generator.create(target)
            for required in ("index.html", "deck-content.json", "LICENSE"):
                self.assertTrue((target / required).exists(), required)
            for internal in ("AGENTS.md", "发送版.html", "导出图片", "图片版.pdf", "图文讲稿.pdf"):
                self.assertFalse((target / internal).exists(), internal)

    def test_generator_ignore_set_covers_runtime_and_all_exports(self):
        generator = load_module("shared_create_deck_junk", ROOT / "scripts" / "create_deck.py")
        names = [
            "AGENTS.md", "deck-content.json", ".prompter-state.json", "发送版.html",
            "导出图片", "图片版.pdf", "图文讲稿.pdf", "index.html",
        ]
        ignored = generator.JUNK("unused", names)
        for generated in (".prompter-state.json", "发送版.html", "导出图片", "图片版.pdf", "图文讲稿.pdf"):
            self.assertIn(generated, ignored)
        self.assertNotIn("index.html", ignored)


class SharedServerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_module("shared_prompter_server", SERVER)

    def test_local_endpoints_require_token_and_unknown_paths_fail_closed(self):
        source = SERVER.read_text(encoding="utf-8")
        allow = source.split("def allow(self, path):", 1)[1].split("def guard", 1)[0]
        local = allow.split("if path in LOCAL_ONLY:", 1)[1].split("if path in PHONE_PATHS", 1)[0]
        self.assertIn("token_ok()", local)
        self.assertIn('return False, "未知的请求路径"', allow)
        for path in ("/content", "/content/lease", "/content/patch", "/canvas", "/export"):
            self.assertIn(path, self.server.LOCAL_ONLY)

    def test_markup_filters_reject_active_content(self):
        for payload in (
            '<p><img src=x onerror="fetch(1)"></p>',
            '<p><iframe src="http://evil"></iframe></p>',
            '<p class="class>" onclick=alert(1)>hi</p>',
            '<a href="javascript:alert(1)">x</a>',
        ):
            ok, _ = self.server.check_markup(payload, self.server.NOTE_TAGS, self.server.NOTE_ATTRS)
            self.assertFalse(ok, payload)

    def test_live_patch_revalidates_source_order(self):
        original = """<template id="slides">
<section class="slide" data-slide-id="a" data-title="A"><div class="canvas"></div><aside><div class="ns"><p>A</p></div><div class="nc"></div></aside></section>
<section class="slide" data-slide-id="b" data-title="B"><div class="canvas"></div><aside><div class="ns"><p>B</p></div><div class="nc"></div></aside></section>
</template>"""
        inserted = original.replace(
            '<section class="slide" data-slide-id="a"',
            '<section class="slide" data-slide-id="new" data-title="New"><div class="canvas"></div><aside><div class="ns"><p>New</p></div><div class="nc"></div></aside></section>\n<section class="slide" data-slide-id="a"',
            1,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            index = root / "index.html"
            content = root / "deck-content.json"
            index.write_text(original, encoding="utf-8")
            ensure_store(index, content)
            index.write_text(inserted, encoding="utf-8")
            handler = object.__new__(self.server.Handler)
            responses = []
            handler.send_json = lambda value, code=200: responses.append((value, code))
            with mock.patch.object(self.server, "INDEX_FILE", str(index)), \
                 mock.patch.object(self.server, "CONTENT_FILE", str(content)), \
                 mock.patch.object(self.server, "sync_notes_page") as sync_notes, \
                 mock.patch.object(self.server, "broadcast"):
                self.server.content_leases.clear()
                handler.handle_post(
                    "/content/patch",
                    {"slideId": "a", "field": "script", "html": "<p>A edited</p>", "baseRevision": 0, "owner": "test"},
                )
            self.assertEqual(read_store(content)["order"], ["new", "a", "b"])
            sync_notes.assert_called_once_with(2, "<p>A edited</p>", "ns")
            self.assertEqual(responses[-1][0]["ok"], 1)

    def test_content_reads_and_writes_revalidate_current_html(self):
        source = SERVER.read_text(encoding="utf-8")
        cli = (DECK / "scripts" / "deck_content.py").read_text(encoding="utf-8")
        get_content = source.split('elif path == "/content":', 1)[1].split("elif re.match", 1)[0]
        patch_content = source.split('elif path == "/content/patch":', 1)[1].split('elif path == "/flip":', 1)[0]
        self.assertIn("ensure_store(INDEX_FILE, CONTENT_FILE)", get_content)
        self.assertIn("ensure_store(INDEX_FILE, CONTENT_FILE)", patch_content)
        show = cli.split('elif args.command == "show":', 1)[1].split("else:", 1)[0]
        self.assertIn("store = _server_show(args)", show)
        self.assertNotIn("ensure_store(", show)
        self.assertIn('_server_url(args, "/content")', cli)


if __name__ == "__main__":
    unittest.main()

import json
import pathlib
import sys
import tempfile
import unittest


SKILL = pathlib.Path(__file__).resolve().parents[2]
DECK = SKILL / "assets" / "hanyu-html-deck"
sys.path.insert(0, str(DECK / "scripts"))

from deck_content import (  # noqa: E402
    ContentConflict,
    ensure_store,
    hydrate_html,
    patch_store,
    read_store,
)


SAMPLE = """<template id="slides">
<section class="slide" data-slide-id="alpha" data-title="One">
  <div class="canvas"></div><aside><div class="ns"><p>Script one</p></div><div class="nc"><p>Note one</p></div></aside>
</section>
<section class="slide" data-slide-id="beta" data-title="Two">
  <div class="canvas"></div><aside><div class="ns"><p>Script two</p></div><div class="nc"></div></aside>
</section>
</template>"""


class DeckContentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.index = self.root / "index.html"
        self.content = self.root / "deck-content.json"
        self.index.write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_initializes_stable_ids_and_both_fields(self):
        store = ensure_store(self.index, self.content)
        self.assertEqual(store["order"], ["alpha", "beta"])
        self.assertEqual(store["slides"]["alpha"]["script"]["html"], "<p>Script one</p>")
        self.assertEqual(store["slides"]["alpha"]["note"]["html"], "<p>Note one</p>")

    def test_duplicate_slide_ids_are_rejected(self):
        self.index.write_text(SAMPLE.replace('data-slide-id="beta"', 'data-slide-id="alpha"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "必须唯一"):
            ensure_store(self.index, self.content)

    def test_missing_slide_ids_are_rejected_before_content_can_shift(self):
        self.index.write_text(SAMPLE.replace(' data-slide-id="alpha"', "", 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "每页必须设置 data-slide-id"):
            ensure_store(self.index, self.content)

    def test_revision_conflict_never_overwrites_latest_content(self):
        ensure_store(self.index, self.content)
        store, field = patch_store(self.content, "alpha", "script", "<p>User edit</p>", 0)
        self.assertEqual(field["revision"], 1)
        with self.assertRaises(ContentConflict):
            patch_store(self.content, "alpha", "script", "<p>Stale AI edit</p>", 0)
        self.assertEqual(read_store(self.content)["slides"]["alpha"]["script"]["html"], "<p>User edit</p>")

    def test_unedited_seed_updates_but_collaborative_edit_is_preserved(self):
        ensure_store(self.index, self.content)
        updated = SAMPLE.replace("Script one", "Generated first draft")
        self.index.write_text(updated, encoding="utf-8")
        self.assertIn("Generated first draft", ensure_store(self.index, self.content)["slides"]["alpha"]["script"]["html"])
        patch_store(self.content, "alpha", "script", "<p>Browser edit</p>", 0)
        self.index.write_text(SAMPLE.replace("Script one", "Later direct edit"), encoding="utf-8")
        self.assertEqual(ensure_store(self.index, self.content)["slides"]["alpha"]["script"]["html"], "<p>Browser edit</p>")

    def test_hydration_keeps_canvas_and_replaces_script_and_note(self):
        store = ensure_store(self.index, self.content)
        store["slides"]["beta"]["script"]["html"] = "<p>Hydrated</p>"
        store["slides"]["beta"]["note"]["html"] = "<p>Private</p>"
        hydrated = hydrate_html(SAMPLE, store)
        self.assertIn('<div class="canvas"></div>', hydrated)
        self.assertIn("<p>Hydrated</p>", hydrated)
        self.assertIn("<p>Private</p>", hydrated)

    def test_hydration_rejects_position_based_fallback(self):
        store = ensure_store(self.index, self.content)
        missing_id = SAMPLE.replace(' data-slide-id="alpha"', "", 1)
        with self.assertRaisesRegex(ValueError, "每页必须设置 data-slide-id"):
            hydrate_html(missing_id, store)


class DeckContentBrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DECK / "index.html").read_text(encoding="utf-8")
        cls.server = (DECK / "scripts" / "prompter_server.py").read_text(encoding="utf-8")

    def test_browser_uses_stable_drafts_and_shared_patch_endpoint(self):
        self.assertIn("'.draft.' + TAB_ID + '.' + contentKey(i, ed)", self.html)
        self.assertIn("if (contentLoaded) dropDraft(cur, ed)", self.html)
        self.assertIn("fetch(api('/content/patch')", self.html)
        self.assertIn("baseRevision: contentRevision(c.i, c.ed)", self.html)
        self.assertIn("deckEvents.addEventListener('content'", self.html)

    def test_server_exposes_store_revision_and_short_lease(self):
        self.assertIn('elif path == "/content":', self.server)
        self.assertIn('if path == "/content/lease":', self.server)
        self.assertIn('elif path == "/content/patch":', self.server)
        self.assertIn("CONTENT_LEASE_SECONDS = 8", self.server)
        self.assertIn("except ContentConflict as error", self.server)

    def test_template_content_store_matches_slide_inventory(self):
        store = json.loads((DECK / "deck-content.json").read_text(encoding="utf-8"))
        self.assertEqual(len(store["order"]), self.html.count('data-slide-id="'))
        self.assertEqual(len(store["order"]), len(set(store["order"])))


if __name__ == "__main__":
    unittest.main()

import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SKILL = pathlib.Path(__file__).resolve().parents[2]
DECK = SKILL / "assets" / "hanyu-html-deck"
sys.path.insert(0, str(DECK / "scripts"))

from deck_source import archived_slide_pages, set_archived_slides, strip_archived_slides  # noqa: E402
import prompter_server  # noqa: E402


SAMPLE = """<template id="slides">
<section class="slide" data-title="One > zero"><div></div></section>
<section class="slide" data-title="Two"><div></div></section>
<section class="slide" data-title="Three"><div></div></section>
</template><script>keep()</script>"""


class DeckSourceArchiveTests(unittest.TestCase):
    def test_archive_state_round_trips_without_removing_slides(self):
        archived = set_archived_slides(SAMPLE, [2], 3)
        self.assertEqual(archived.count('class="slide"'), 3)
        self.assertEqual(archived.count('data-archived="1"'), 1)

        restored = set_archived_slides(archived, [], 3)
        self.assertEqual(restored, SAMPLE)

    def test_archive_attribute_parser_does_not_touch_titles_or_other_templates(self):
        tricky = SAMPLE.replace('data-title="Two"', 'data-title=\'keep data-archived="1" literal\'')
        tricky = '<section class="slide" data-archived="1"></section>' + tricky
        archived = set_archived_slides(tricky, [2], 3)
        self.assertIn('data-title=\'keep data-archived="1" literal\'', archived)
        self.assertEqual(archived_slide_pages(archived), [2])
        self.assertTrue(archived.startswith('<section class="slide" data-archived="1">'))

    def test_archive_rejects_stale_page_count_and_empty_deck(self):
        with self.assertRaisesRegex(ValueError, "页数已变化"):
            set_archived_slides(SAMPLE, [2], 4)
        with self.assertRaisesRegex(ValueError, "至少保留"):
            set_archived_slides(SAMPLE, [1, 2, 3], 3)

    def test_standalone_strip_keeps_template_and_scripts(self):
        archived = set_archived_slides(SAMPLE, [1, 3], 3)
        stripped, count = strip_archived_slides(archived)
        self.assertEqual(count, 2)
        self.assertEqual(stripped.count('class="slide"'), 1)
        self.assertIn('data-title="Two"', stripped)
        self.assertIn("</template><script>keep()</script>", stripped)

    def test_archived_page_list_uses_source_page_numbers(self):
        archived = set_archived_slides(SAMPLE, [1, 3], 3)
        self.assertEqual(archived_slide_pages(archived), [1, 3])

    def test_note_writeback_finds_active_entry_by_source_page(self):
        payload = {
            "pages": [
                {"n": 1, "source": 1, "html": "one", "comm": ""},
                {"n": 2, "source": 3, "html": "three", "comm": ""},
            ]
        }
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(prompter_server, "notes", payload), \
             mock.patch.object(prompter_server, "NOTES_FILE", str(pathlib.Path(temp) / "notes.json")), \
             mock.patch.object(prompter_server, "sse_clients", []), \
             mock.patch.object(prompter_server, "state", {"nv": "", "seq": 1}):
            prompter_server.sync_notes_page(3, "updated", "ns")
        self.assertEqual(payload["pages"][0]["html"], "one")
        self.assertEqual(payload["pages"][1]["html"], "updated")


class DeckArchiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DECK / "index.html").read_text(encoding="utf-8")

    def test_overview_has_archive_and_restore_controls(self):
        self.assertIn('id="ovArchiveToggle"', self.html)
        self.assertIn("function setArchived(i, on, item, fromUndo)", self.html)
        self.assertIn("archiveIcon(isArchived(i))", self.html)
        self.assertIn('id="archiveToast" role="status" aria-live="polite"', self.html)
        self.assertIn("action.dataset.sourcePage = String(i + 1)", self.html)
        self.assertIn("(focusTarget || ovArchiveToggle).focus()", self.html)

    def test_archive_cache_tracks_the_source_revision(self):
        self.assertIn("var ARCHIVE_SOURCE_KEY = ARCHIVE_KEY + '.source'", self.html)
        self.assertIn("JSON.stringify(baseline) === sourceJSON", self.html)
        self.assertIn("if (archiveNeedsWrite) persistArchiveState()", self.html)

    def test_navigation_and_prompter_use_active_sequence(self):
        self.assertIn("function activeIndices()", self.html)
        self.assertIn("page: activePosition(cur) + 1", self.html)
        self.assertIn("pages: active.map(function (i, pos)", self.html)
        self.assertIn("go(active[pos + 1])", self.html)

    def test_export_scripts_filter_archived_pages(self):
        for name in ("export_pages.py", "export_steps.py"):
            text = (DECK / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("s.dataset.archived !== '1'", text)
        send = (DECK / "scripts" / "build_send.py").read_text(encoding="utf-8")
        self.assertIn("strip_archived_slides(html)", send)

    def test_archive_writeback_is_protected_local_endpoint(self):
        server = (DECK / "scripts" / "prompter_server.py").read_text(encoding="utf-8")
        self.assertIn('"/archive", "/canvas", "/seed", "/export"', server)
        self.assertIn('elif path == "/archive":', server)
        self.assertIn("save_archive(archived, dom_total)", server)

    def test_cached_previews_require_matching_archive_state(self):
        source = set_archived_slides(SAMPLE, [2], 3)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            index = temp_path / "index.html"
            manifest = temp_path / "state.json"
            index.write_text(source, encoding="utf-8")
            with mock.patch.object(prompter_server, "INDEX_FILE", str(index)):
                self.assertFalse(prompter_server.export_state_matches(str(manifest)))
                manifest.write_text('{"archived":[2]}', encoding="utf-8")
                self.assertTrue(prompter_server.export_state_matches(str(manifest)))
                manifest.write_text('{"archived":[]}', encoding="utf-8")
                self.assertFalse(prompter_server.export_state_matches(str(manifest)))

    def test_exporters_record_preview_state_and_phone_hides_stale_images(self):
        pages = (DECK / "scripts" / "export_pages.py").read_text(encoding="utf-8")
        steps = (DECK / "scripts" / "export_steps.py").read_text(encoding="utf-8")
        phone = (DECK / "scripts" / "prompter-phone.html").read_text(encoding="utf-8")
        self.assertIn('.prompter-thumb-state.json', pages)
        self.assertIn('.prompter-step-state.json', steps)
        self.assertIn("this.style.visibility = 'hidden'", phone)
        self.assertIn("img.addEventListener('error'", phone)

    def test_autostep_runs_continuously_and_step_export_disables_it(self):
        self.assertIn("function scheduleAutoSteps(i, interval)", self.html)
        self.assertIn("autoTimer = setTimeout(advance, delay)", self.html)
        self.assertIn("function frozenStepsOf(i)", self.html)
        self.assertIn("function autoStepsOf(i)", self.html)
        self.assertIn("return stepsOf(i) > 0 && !frozenStepsOf(i)", self.html)
        self.assertIn("if (ac && autoStepsOf(cur)) scheduleAutoSteps(cur, ac.dataset.autostep)", self.html)
        self.assertNotIn("function manualStepsOf(i)", self.html)
        self.assertIn("case 'ArrowRight': case 'ArrowDown': case ' ': case 'PageDown':", self.html)
        self.assertIn("e.preventDefault(); next(); break;", self.html)
        steps = (DECK / "scripts" / "export_steps.py").read_text(encoding="utf-8")
        self.assertIn("window.hanyuFreezeStepsForExport = function ()", self.html)
        self.assertIn("clearTimeout(autoTimer)", self.html)
        self.assertIn("canvas.dataset.stepfreeze = '1'", self.html)
        self.assertIn("window.hanyuFreezeStepsForExport()", steps)


if __name__ == "__main__":
    unittest.main()

import base64
import io
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'assets' / 'hanyu-html-deck' / 'scripts'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==')
SOURCE = '''<html><head></head><body><template id="slides">
<section class="slide" data-slide-id="one" data-title="一"><div class="canvas">{assets}</div>
<aside><div class="ns"><p>种子讲稿</p></div><div class="nc"><div>PRIVATE_NESTED_NOTE</div></div></aside></section>
<section class="slide" data-slide-id="two" data-title="二" data-archived="1"><div class="canvas">ARCHIVED_PRIVATE</div>
<aside><div class="ns">old</div><div class="nc">private</div></aside></section>
</template><script>
var SEND_VERSION = false;
var TOKEN = 'test-secret'; /* HANYU_TOKEN */
// ===== CVEDIT-START =====
var privateEditor = true;
// ===== CVEDIT-END =====
</script></body></html>'''


class SendExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.deck = pathlib.Path(self.temp.name)
        (self.deck / 'assets' / '研究').mkdir(parents=True)
        self.image = self.deck / 'assets' / '研究' / "sawada-kyoichi's war photography.png"
        self.image.write_bytes(PNG)
        self.index = self.deck / 'index.html'
        self.index.write_text(SOURCE.replace('{assets}', '<img src="assets/研究/sawada-kyoichi\'s war photography.png">'))
        self.out = self.deck / '发送版.html'

    def export(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'build_send.py'), '--root', str(self.deck), *args],
                              text=True, capture_output=True)

    def test_assets_notes_archive_and_readonly_latest_content(self):
        store = {'version': 1, 'revision': 2, 'order': ['two', 'one'], 'slides': {
            'one': {'title': 'old title', 'script': {'html': '<p>LATEST_SAVED_SCRIPT</p>', 'revision': 2},
                    'note': {'html': '<p>STORE_PRIVATE_NOTE</p>', 'revision': 1}}}}
        content = self.deck / 'deck-content.json'
        content.write_text(json.dumps(store))
        before = (self.index.read_bytes(), content.read_bytes())
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.out.read_text()
        for secret in ('test-secret', 'PRIVATE_NESTED_NOTE', 'STORE_PRIVATE_NOTE', 'ARCHIVED_PRIVATE', 'CVEDIT-START', '种子讲稿'):
            self.assertNotIn(secret, text)
        self.assertIn('LATEST_SAVED_SCRIPT', text)
        self.assertIn('data:image/png;base64,' + base64.b64encode(PNG).decode(), text)
        self.assertEqual((self.index.read_bytes(), content.read_bytes()), before)

    def test_missing_store_and_zero_revision_keep_html_seed(self):
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.deck / 'deck-content.json').exists())
        store = {'version': 1, 'slides': {'one': {'script': {'html': 'STALE_ZERO_REVISION', 'revision': 0}}}}
        (self.deck / 'deck-content.json').write_text(json.dumps(store))
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('种子讲稿', self.out.read_text())
        self.assertNotIn('STALE_ZERO_REVISION', self.out.read_text())

    def test_nested_stylesheet_resolves_its_own_relative_urls(self):
        (self.deck / 'css').mkdir()
        (self.deck / 'css' / 'deck.css').write_text('body { background: url("../assets/研究/sawada-kyoichi\'s war photography.png"); }')
        self.index.write_text(self.index.read_text().replace('<head>', '<head><link href="css/deck.css" rel="stylesheet" media="print">'))
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('<link', self.out.read_text())
        self.assertIn('<style media="print">', self.out.read_text())
        self.assertIn('background: url("data:image/png;base64,', self.out.read_text())

    def test_js_filename_key_is_not_mistaken_for_a_resource(self):
        self.index.write_text(self.index.read_text().replace('</script>', "const labels = {'photo.jpg':'cover'};</script>"))
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'photo.jpg':'cover'", self.out.read_text())

    def test_bare_image_path_is_inlined(self):
        (self.deck / 'picture.png').write_bytes(PNG)
        self.index.write_text(self.index.read_text().replace('assets/研究/sawada-kyoichi\'s war photography.png', 'picture.png'))
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('src="picture.png"', self.out.read_text())

    def test_missing_asset_fails_without_overwriting_existing_output(self):
        self.image.unlink()
        self.out.write_text('previous good export')
        result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.out.read_text(), 'previous good export')

    def test_invalid_store_and_source_overwrite_are_rejected(self):
        (self.deck / 'deck-content.json').write_text('{broken')
        self.assertNotEqual(self.export().returncode, 0)
        before = self.index.read_bytes()
        self.assertNotEqual(self.export('--output', str(self.index)).returncode, 0)
        self.assertEqual(self.index.read_bytes(), before)

    def test_output_alias_cannot_overwrite_source(self):
        source = self.deck / 'source.html'
        self.index.rename(source)
        self.index.symlink_to(source)
        before = source.read_bytes()
        self.assertNotEqual(self.export('--output', str(self.index)).returncode, 0)
        alias = self.deck / 'hardlink.html'
        alias.hardlink_to(source)
        self.assertNotEqual(self.export('--output', str(alias)).returncode, 0)
        self.assertEqual(source.read_bytes(), before)

    def test_full_template_exports_without_treating_service_urls_as_assets(self):
        template = ROOT / 'assets' / 'hanyu-html-deck'
        self.index.write_bytes((template / 'index.html').read_bytes())
        shutil.copytree(template / 'fonts', self.deck / 'fonts')
        result = self.export('--no-subset')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('var SEND_VERSION = true;', self.out.read_text())

    def test_external_runtime_dependency_is_rejected(self):
        self.index.write_text(self.index.read_text().replace('</head>', '<script src="https://example.com/app.js"></script></head>'))
        self.assertNotEqual(self.export().returncode, 0)
        self.assertFalse(self.out.exists())

    @unittest.skipUnless(importlib.util.find_spec("fontTools"), "optional font dependency")
    def test_missing_brotli_while_loading_preserves_complete_font(self):
        from unittest import mock
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.pop, 0)
        import build_send
        font = ROOT / 'assets' / 'hanyu-html-deck' / 'fonts' / 'NotoSansSC.woff2'
        with mock.patch('fontTools.subset.load_font', side_effect=ImportError('brotli unavailable')):
            data, mime = build_send.subset_font(font, '字体')
        self.assertEqual(data, font.read_bytes())
        self.assertEqual(mime, 'font/woff2')

    @unittest.skipUnless(importlib.util.find_spec("fontTools") and importlib.util.find_spec("brotli"), "optional font subsetting dependencies")
    def test_font_subset_is_woff2_and_contains_visible_characters(self):
        from fontTools.ttLib import TTFont
        font = ROOT / 'assets' / 'hanyu-html-deck' / 'fonts' / 'NotoSansSC.woff2'
        (self.deck / 'fonts').mkdir()
        shutil.copy2(font, self.deck / 'fonts' / 'text.woff2')
        (self.deck / 'css').mkdir()
        (self.deck / 'css' / 'font.css').write_text('@font-face {font-family: test; src: url("../fonts/text.woff2")} body::before {content: "龘"}')
        self.index.write_text(self.index.read_text().replace('</head>', '<link rel="stylesheet" href="css/font.css"></head>'))
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        import re
        encoded = re.search(r'data:font/woff2;base64,([A-Za-z0-9+/=]+)', self.out.read_text()).group(1)
        data = base64.b64decode(encoded)
        self.assertEqual(data[:4], b'wOF2')
        self.assertLess(len(data), font.stat().st_size)
        with TTFont(io.BytesIO(data)) as subset:
            self.assertTrue(set(map(ord, '一种子讲稿龘')).issubset(subset.getBestCmap()))


if __name__ == '__main__':
    unittest.main()

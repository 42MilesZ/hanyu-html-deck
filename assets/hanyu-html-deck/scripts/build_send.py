"""发送版单文件 HTML：只读内容仓，内联素材，剥除备注、归档与本地写回入口。"""
import argparse
import base64
import html as html_tools
import io
import mimetypes
import pathlib
import re
import subprocess
import tempfile
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from deck_content import ensure_store, hydrate_html
from deck_source import strip_archived_slides

BASE = pathlib.Path(__file__).resolve().parent.parent
URL_RE = re.compile(r'''(?<![\w-])url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"\s]+))\s*\)''', re.I)
ASSET_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|svg|woff2?|ttf|otf)(?:[?#][^\"'\s<>]*)?$", re.I)
RESOURCE_RE = re.compile(r'''\b(?:src|poster)\s*=\s*(?:"([^"]*)"|'([^']*)')''', re.I)
TOKEN_RE = re.compile(r"(var TOKEN = ')([^']*)('; /\* HANYU_TOKEN \*/)")


def fail(message):
    raise ValueError(message)


def decode_ref(value):
    return html_tools.unescape(re.sub(r'''\\(["'\\])''', r'\1', value))


def is_local(value):
    return bool(value) and not value.startswith(('#', '//')) and not urlsplit(value).scheme


def local_refs(document):
    refs = set()
    # Scan quote types separately so an apostrophe inside a double-quoted filename is preserved.
    for pattern in (r'"((?:\\.|[^"\\\n])*)"', r"'((?:\\.|[^'\\\n])*)'", URL_RE, RESOURCE_RE):
        for match in re.finditer(pattern, document):
            raw = next(group for group in match.groups() if group is not None)
            value = decode_ref(raw)
            if is_local(value) and not value.startswith('/') and ASSET_RE.search(value) and not re.search(r'[<>\n]', value):
                if pattern in (URL_RE, RESOURCE_RE) or '/' in value:
                    refs.add(raw)
    return refs


class ResourceTags(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.stylesheets = []
        self.dependencies = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split():
            self.stylesheets.append((self.get_starttag_text(), attrs))
            self.dependencies.append(attrs.get('href', ''))
        if tag in ('img', 'script', 'source', 'video', 'audio', 'iframe', 'embed', 'input'):
            for attr in ('src', 'poster', 'srcset'):
                if attrs.get(attr):
                    self.dependencies.append(attrs[attr])


def subset_font(path, text):
    try:
        from fontTools import subset
        options = subset.Options()
        options.flavor = 'woff2'
        options.layout_features = ['*']
        with subset.load_font(str(path), options) as font:
            worker = subset.Subsetter(options=options)
            worker.populate(text=text)
            worker.subset(font)
            output = io.BytesIO()
            subset.save_font(font, output, options)
            return output.getvalue(), 'font/woff2'
    except ImportError:
        print('字体子集未启用：fonttools/brotli 不可用；保留完整字体')
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or 'application/octet-stream'


def inline_assets(document, root, text, options, cache, temporary):
    refs = sorted(local_refs(document), key=len, reverse=True)
    paths = {raw: (root / unquote(urlsplit(decode_ref(raw)).path)).resolve() for raw in refs}
    missing = [raw for raw, path in paths.items() if not path.is_file()]
    if missing:
        fail('素材缺失：%s；若由脚本动态拼接路径，请先在临时副本中展开' % decode_ref(missing[0]))
    for raw in refs:
        url = urlsplit(decode_ref(raw))
        path = paths[raw]
        if path not in cache:
            suffix = path.suffix.lower()
            data = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            if suffix in ('.woff2', '.woff', '.ttf', '.otf') and not options.no_subset:
                data, mime = subset_font(path, text)
            elif suffix in ('.jpg', '.jpeg', '.png'):
                alpha = suffix == '.png'
                if alpha:
                    probe = subprocess.run(['sips', '-g', 'hasAlpha', str(path)], capture_output=True, text=True, check=True)
                    alpha = 'yes' in probe.stdout.lower()
                if not alpha:
                    out = temporary / 'image.jpg'
                    subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', str(options.quality),
                                    '-Z', str(options.max_edge), str(path), '--out', str(out)],
                                   capture_output=True, check=True)
                    data, mime = out.read_bytes(), 'image/jpeg'
            cache[path] = 'data:%s;base64,%s' % (mime, base64.b64encode(data).decode())
        document = document.replace(raw, cache[path] + ('#' + url.fragment if url.fragment else ''))
    return document


def strip_blocks(document, selector):
    """按 div 开闭配平剥除备注，保留嵌套 div 的完整边界。"""
    removed = []
    while True:
        opening = re.search(r'\s*<div class="%s">' % selector, document)
        if not opening:
            return document, len(removed), removed
        inner = opening.end()
        depth = 1
        end = None
        for match in re.finditer(r"<div\b|</div>", document[inner:]):
            depth += 1 if match.group(0).startswith('<div') else -1
            if depth == 0:
                end = inner + match.end()
                break
        if end is None:
            fail('.%s 区块的 div 开闭不配平' % selector)
        removed.append(document[inner:end - len('</div>')])
        document = document[:opening.start()] + document[end:]


def build(root, output, options):
    source = root / 'index.html'
    html = hydrate_html(source.read_text(encoding='utf-8'),
                        ensure_store(source, root / 'deck-content.json', persist=False))
    html, n_archived = strip_archived_slides(html)
    html, n_nc, notes = strip_blocks(html, 'nc')
    html, n_na, legacy = strip_blocks(html, 'na')
    html, n_cvedit = re.subn(r'\s*// ===== CVEDIT-START.*?// ===== CVEDIT-END =====', '', html, flags=re.S)
    html, n_flag = re.subn(r'var SEND_VERSION = false;', 'var SEND_VERSION = true;', html)
    html, n_token = TOKEN_RE.subn(r'\g<1>\g<3>', html)
    if 'class="nc"' in html or 'class="na"' in html:
        fail('备注区块没剥净')
    for note in notes + legacy:
        plain = re.sub(r'<[^>]+>', '', note).strip()
        if len(plain) >= 8 and plain in html:
            fail('备注正文仍残留在发送版中')
    if n_cvedit != 1 or 'CVEDIT-START' in html:
        fail('画布就地编辑没剥净')
    if n_flag != 1:
        fail('没能置上发送版标记')
    if n_token != 1 or not re.search(r"var TOKEN = ''; /\* HANYU_TOKEN \*/", html):
        fail('写回凭据没清空，不能外发')

    stylesheets = []
    for tag, attrs in ResourceTags(html).stylesheets:
        ref = attrs.get('href', '')
        if not is_local(ref):
            fail('请先将外部样式表保存到本地：%s' % ref)
        path = root / unquote(urlsplit(ref).path)
        css = path.read_text(encoding='utf-8')
        if re.search(r'@import\b', css, re.I):
            fail('请先展开样式表中的 @import：%s' % ref)
        stylesheets.append((tag, attrs, path, css))
    text = html_tools.unescape(re.sub(r'[A-Za-z0-9+/=]{200,}', '', html))
    text += ''.join(css for _, _, _, css in stylesheets)
    # Include CSS escaped glyphs, such as content: "\\9f98".
    text += ''.join(chr(int(m.group(1), 16)) for m in re.finditer(r'\\([0-9a-fA-F]{1,6})(?:\s|(?=[^0-9a-fA-F]|$))', text)
                    if 0 < int(m.group(1), 16) <= 0x10FFFF)
    cache = {}
    with tempfile.TemporaryDirectory(prefix='deck-send-') as tmp:
        temporary = pathlib.Path(tmp)
        for tag, attrs, path, css in stylesheets:
            css = inline_assets(css, path.parent, text, options, cache, temporary)
            media = html_tools.escape(attrs.get('media', 'all'), quote=True)
            html = html.replace(tag, '<style media="%s">\n%s\n</style>' % (media, css))
        html = inline_assets(html, root, text, options, cache, temporary)

    dependencies = ResourceTags(html).dependencies
    dependencies += [next(g for g in m.groups() if g is not None) for m in URL_RE.finditer(html)]
    if any(ref and not ref.startswith(('data:', '#')) for ref in dependencies) or local_refs(html):
        fail('仍有未内联的资源；请检查 src、srcset、样式和脚本引用')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding='utf-8')
    print('归档页剥除 %d 页｜备注剥除 %d 处｜内联资源 %d 个｜成品 %.1fMB' %
          (n_archived, n_nc + n_na, len(cache), output.stat().st_size / 1048576))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=pathlib.Path, default=BASE)
    parser.add_argument('--output', type=pathlib.Path)
    parser.add_argument('--no-subset', action='store_true', help='保留完整字体')
    parser.add_argument('--quality', type=int, default=70)
    parser.add_argument('--max-edge', type=int, default=1920)
    options = parser.parse_args()
    root = options.root.expanduser().resolve()
    output = options.output or root / '发送版.html'
    if not 1 <= options.quality <= 100 or options.max_edge < 1:
        parser.error('quality 必须为 1–100，max-edge 必须为正数')
    for source in (root / 'index.html', root / 'deck-content.json'):
        if output.resolve() == source.resolve() or (output.exists() and source.exists() and output.samefile(source)):
            parser.error('输出不能覆盖源稿或内容仓')
    try:
        build(root, output, options)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit('发送版导出中止：%s' % error)


if __name__ == '__main__':
    main()

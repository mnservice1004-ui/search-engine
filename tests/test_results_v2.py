"""Search-results presentation checks without credentials, HTTP or an operating DB."""

import json
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


class HtmlNode:
    """Small standard-library DOM for semantic footer assertions."""

    def __init__(self, tag, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.content = []

    @property
    def children(self):
        return [part for part in self.content if isinstance(part, HtmlNode)]

    @property
    def text(self):
        return ''.join(part.text if isinstance(part, HtmlNode) else part for part in self.content)

    def find_all(self, *, tag=None, class_name=None):
        matches = []
        for child in self.children:
            if (tag is None or child.tag == tag) and (
                class_name is None or class_name in child.attrs.get('class', '').split()
            ):
                matches.append(child)
            matches.extend(child.find_all(tag=tag, class_name=class_name))
        return matches


class HtmlTree(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
            'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode('document')
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = HtmlNode(tag, attrs)
        self.stack[-1].content.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].content.append(data)


def result_footer_actions(class_name):
    tree = HtmlTree((ROOT / 'public/index.html').read_text(encoding='utf-8'))
    sections = tree.root.find_all(class_name=class_name)
    assert len(sections) == 1, f'Expected one {class_name} section'
    return [child for child in sections[0].children if child.tag in {'button', 'a'}]


def home_footer():
    tree = HtmlTree((ROOT / 'public/index.html').read_text(encoding='utf-8'))
    footers = tree.root.find_all(tag='footer', class_name='home-footer')
    assert len(footers) == 1
    return footers[0]


def action_copy(action):
    titles = action.find_all(tag='strong')
    summaries = action.find_all(tag='small')
    assert len(titles) == len(summaries) == 1
    return titles[0].text.strip(), summaries[0].text.strip()


def test_results_v2_vm_presentation_contract():
    result = subprocess.run(
        ["node", str(ROOT / "tests/results_v2_view.cjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["passed"] == len(set(report["cases"])) == 30
    assert report["failed"] == 0
    assert report["realSmsSent"] == 0


def test_results_v2_is_scoped_and_reuses_the_existing_result_buttons():
    script = (ROOT / "public/js/results-v2.js").read_text(encoding="utf-8")
    assert "document.body.classList.contains('results-v2')" in script
    assert "const PAGE_SIZE = 4" in script
    assert "button.replaceChildren()" in script
    assert "button.dataset.taskId !== String(items[index].id)" in script
    assert "innerHTML" not in script and "fetch(" not in script
    assert "showDetail(" not in script and "/api/sms" not in script


def test_results_v2_assets_loaded_after_their_base_layers():
    html = (ROOT / "public/index.html").read_text(encoding="utf-8")
    assert html.index('/css/home-v2.css') < html.index('/css/results-v2.css')
    assert html.index('/js/app.js') < html.index('/js/results-v2.js')
    assert html.count('id="results-filters"') == 1
    assert html.count('id="results-count"') == 1
    assert html.count('id="results-pagination"') == 1
    assert html.count('id="results-extras"') == 1
    assert 'data-results-help' in html


def css_declarations(source, selector):
    """Read the first (desktop/base) declaration block of an exact selector."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    for selectors, declarations in re.findall(r'([^{}]+)\{([^{}]*)\}', source):
        if selector in [part.strip() for part in selectors.split(',')]:
            return dict(part.strip().split(':', 1) for part in declarations.split(';') if ':' in part)
    raise AssertionError(f"Missing CSS selector: {selector}")


def relative_luminance(color):
    color = color.lstrip('#')
    if len(color) == 3:
        color = ''.join(character * 2 for character in color)
    assert len(color) == 6, "Contrast tests require opaque RGB colors"
    components = [int(color[offset:offset + 2], 16) / 255 for offset in (0, 2, 4)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in components]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def test_results_footer_is_removed_from_layout_only_when_results_are_open():
    css = (ROOT / 'public/css/results-v2.css').read_text(encoding='utf-8')
    scoped = '.home-v2.results-v2.home-has-results .home-footer'
    assert css_declarations(css, scoped)['display'].strip() == 'none'
    footer_selectors = [selectors for selectors, _ in re.findall(r'([^{}]+)\{([^{}]*)\}', css)
                        if '.home-footer' in selectors]
    assert footer_selectors and all(scoped in selectors for selectors in footer_selectors)
    base_css = (ROOT / 'public/css/home-v2.css').read_text(encoding='utf-8')
    assert css_declarations(base_css, '.home-v2 .home-footer')['display'].strip() == 'flex'


def test_results_footer_refinement_keeps_home_footer_and_both_help_sections():
    html = (ROOT / 'public/index.html').read_text(encoding='utf-8')
    footer = re.search(r'<footer class="home-footer">(.*?)</footer>', html, re.S).group(1)
    assert '<svg ' not in footer
    assert '준비물·방문 장소·문의전화를 확인하고, 안내 내용을 문자로 받아보세요.' not in footer
    assert '화성시 민원안내콜센터' not in footer and 'roh kang woo' in footer
    related = result_footer_actions('results-related-grid')
    assert len(related) == 4
    assert [action_copy(action) for action in related] == [
        ('영유아 건강검진', '아이의 건강한 성장을 응원합니다.'),
        ('건강생활실천', '건강한 생활습관, 지금 시작하세요.'),
        ('보건소 오시는 길', '동탄구보건소 위치와 교통편을 안내합니다.'),
        ('온라인 챗봇', '궁금한 사항을 문의하세요.'),
    ]
    help_actions = result_footer_actions('results-help')
    assert len(help_actions) == 4
    assert [action_copy(action) for action in help_actions] == [
        ('대표전화', '031-5189-5175'),
        ('운영시간', '평일 09:00 ~ 18:00'),
        ('자주 묻는 질문', '빠른 답변을 확인하세요.'),
        ('민원 안내', '각종 민원서식을 확인하세요.'),
    ]
    assert any('data-results-help' in action.attrs for action in help_actions)


def test_home_footer_removes_the_entire_contact_area_and_its_links():
    footer = home_footer()
    for class_name in ('home-footer-contact', 'home-footer-phones', 'home-footer-hours', 'home-footer-links'):
        assert not footer.find_all(class_name=class_name)
    assert not footer.find_all(tag='section') and not footer.find_all(tag='nav')
    assert not footer.find_all(tag='h2')
    for removed in ('화성시 민원안내콜센터', '1577-4200', '031-370-3900', '유료',
                    '상담시간', '08:30~18:30', '보건소의 업무별 운영·접수시간'):
        assert removed not in footer.text
    links = footer.find_all(tag='a')
    assert all(not item.attrs.get('href', '').startswith('tel:') for item in links)
    assert all('hscityCllr.jsp' not in item.attrs.get('href', '') for item in links)
    inner = footer.find_all(class_name='home-footer-inner')
    assert len(inner) == 1 and len(inner[0].children) == 1
    assert 'home-footer-rights' in inner[0].children[0].attrs.get('class', '').split()


def test_home_footer_copyright_distinguishes_original_and_third_party_material():
    rights = home_footer().find_all(class_name='home-footer-rights')
    assert len(rights) == 1
    copyright_lines = rights[0].find_all(class_name='home-footer-copyright')
    assert len(copyright_lines) == 1
    assert copyright_lines[0].text == 'Copyright © roh kang woo. All rights reserved.'
    english = copyright_lines[0].find_all(tag='span')
    assert len(english) == 1 and english[0].attrs.get('lang') == 'en'
    notes = [item.text for item in rights[0].find_all(class_name='home-footer-note')]
    assert notes == [
        '자체 제작 콘텐츠 기준 · 개인 제작·비공식 평가용',
        '화성시 로고·공식 자료의 권리는 각 권리자에게 있습니다.',
    ]
    assert [child.tag for child in rights[0].children] == ['p', 'p', 'p']
    assert not home_footer().find_all(tag='svg')


def test_home_footer_policy_is_one_inline_safe_accessible_link_in_the_last_note():
    footer = home_footer()
    links = footer.find_all(tag='a')
    assert len(links) == 1
    link = links[0]
    assert link.attrs.get('href') == 'https://www.hscity.go.kr/agree/copyright_policy.jsp'
    assert link.text == '화성시 로고·공식 자료'
    assert link.attrs.get('aria-label') == '화성시 저작권정책 (새 창)'
    assert link.attrs.get('target') == '_blank'
    assert {'noopener', 'noreferrer'} <= set(link.attrs.get('rel', '').split())
    notes = footer.find_all(class_name='home-footer-note')
    assert len(notes) == 2 and notes[-1].find_all(tag='a') == [link]
    assert not footer.find_all(tag='nav')


def css_media_block(source, query):
    """Extract a balanced media block, including all its child rules."""
    match = re.search(r'@media\s*' + re.escape(query) + r'\s*\{', source)
    assert match, f'Missing media query: {query}'
    depth = 1
    for index in range(match.end(), len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[match.end():index]
    raise AssertionError('Unbalanced media block')


def test_home_footer_uses_compact_left_aligned_layout_without_column_dividers():
    css = (ROOT / 'public/css/home-v2.css').read_text(encoding='utf-8')
    base = css_declarations(css, '.home-footer-inner')
    assert base['display'].strip() == 'block'
    assert base['text-align'].strip() == 'left'
    assert 'grid-template-columns' not in base
    assert base['width'].strip() == 'min(1680px,calc(100% - 112px))'
    assert css_declarations(css, '.home-v2 .home-footer')['padding'].strip() == '20px 0'
    rights = css_declarations(css, '.home-footer-rights')
    assert all(rights[prop].strip() == '0' for prop in ('border', 'margin', 'padding'))
    rights_rules = [decl for selectors, decl in re.findall(r'([^{}]+)\{([^{}]*)\}', css)
                    if '.home-footer-rights' in selectors]
    assert len(rights_rules) == 1, 'Do not reintroduce desktop or mobile column dividers'
    tablet = css_media_block(css, '(max-width:1050px)')
    assert css_declarations(tablet, '.home-footer-inner')['width'].strip() == 'calc(100% - 56px)'
    mobile = css_media_block(css, '(max-width:620px)')
    assert css_declarations(mobile, '.home-footer-inner')['width'].strip() == 'calc(100% - 36px)'
    assert css_declarations(mobile, '.home-v2 .home-footer')['padding'].strip() == '18px 0'
    link = css_declarations(css, '.home-footer a')
    assert link['min-height'].strip() == '24px' and link['display'].strip() == 'inline-flex'
    assert css_declarations(css, '.home-footer .home-footer-copyright')['overflow-wrap'].strip() == 'anywhere'
    for removed in ('.home-footer svg', '.home-footer-contact', '.home-footer-phones', '.home-footer-links'):
        assert removed not in css


def test_home_footer_is_hidden_for_printing_without_changing_dialog_print_scope():
    css = (ROOT / 'public/css/home-v2.css').read_text(encoding='utf-8')
    print_css = css_media_block(css, 'print')
    assert css_declarations(print_css, '.home-footer')['display'].replace(' ', '') == 'none!important'
    detail_css = (ROOT / 'public/css/detail-v2.css').read_text(encoding='utf-8')
    assert 'body.detail-printing > :not(#detail-dialog)' in detail_css
    assert 'body.detail-printing #detail-dialog.detail-v2[open]' in detail_css


def test_results_related_and_help_icons_use_eight_decorative_inline_svgs():
    for section, icon_class in [('results-related-grid', 'related-icon'),
                                ('results-help', 'help-symbol')]:
        actions = result_footer_actions(section)
        assert len(actions) == 4
        for action in actions:
            icon = action.find_all(class_name=icon_class)
            assert len(icon) == 1
            svg = icon[0].find_all(tag='svg')
            assert len(svg) == 1, f'{action_copy(action)[0]} must retain its own SVG icon'
            assert svg[0].attrs.get('viewbox')
            assert svg[0].attrs.get('aria-hidden') == 'true' or icon[0].attrs.get('aria-hidden') == 'true'
            assert svg[0].find_all(tag='path'), 'Icons must contain visible vector geometry'
            assert not icon[0].text.strip(), 'Do not substitute OS-dependent text glyphs for icons'


def test_results_help_representative_phone_is_a_direct_telephone_link():
    telephone = result_footer_actions('results-help')[0]
    assert telephone.tag == 'a'
    assert telephone.attrs.get('href', '').replace('-', '') == 'tel:03151895175'
    assert telephone.attrs.get('target') != '_blank'


def test_results_related_and_help_links_have_real_targets_and_safe_new_tabs():
    actions = result_footer_actions('results-related-grid') + result_footer_actions('results-help')
    for action in actions:
        if action.tag == 'button':
            assert action.attrs.get('type') == 'button'
            assert any(name.startswith('data-') for name in action.attrs), 'Buttons need an existing action hook'
            continue
        target = action.attrs.get('href', '')
        assert target.startswith(('https://', 'tel:')), 'No placeholder or script navigation'
        if action.attrs.get('target') == '_blank':
            assert 'noopener' in action.attrs.get('rel', '').split()


def test_results_footer_refinement_compacts_the_workspace_bottom_margin():
    css = (ROOT / 'public/css/results-v2.css').read_text(encoding='utf-8')
    rule = css_declarations(css, '.home-v2.results-v2 #search-workspace')
    margin = rule.get('margin', '').split()
    bottom = rule.get('margin-bottom', margin[2] if len(margin) >= 3 else '')
    assert bottom.strip() == '12px'


def test_related_cards_have_opaque_surfaces_larger_text_and_readable_contrast():
    css = (ROOT / 'public/css/results-v2.css').read_text(encoding='utf-8')
    card = css_declarations(css, '.results-related-grid>button')
    title = css_declarations(css, '.results-related-grid strong')
    copy = css_declarations(css, '.results-related-grid small')
    assert card['background'].strip() in {'#fff', '#ffffff', 'white'}
    assert '#bdcedf' in card['border']
    assert title['font-size'].strip() == '17px'
    assert copy['font-size'].strip() == '14px'
    for foreground in (title.get('color', card['color']).strip(), copy['color'].strip()):
        assert 1.05 / (relative_luminance(foreground) + 0.05) >= 4.5


def test_help_strip_keeps_icons_with_larger_readable_labels():
    css = (ROOT / 'public/css/results-v2.css').read_text(encoding='utf-8')
    title = css_declarations(css, '.results-help strong')
    copy = css_declarations(css, '.results-help small')
    assert title['font-size'].strip() == '14px'
    assert copy['font-size'].strip() == '13px'
    assert relative_luminance(copy['color'].strip()) < relative_luminance('#657896')
    assert css_declarations(css, '.help-symbol')['display'].strip() == 'grid'

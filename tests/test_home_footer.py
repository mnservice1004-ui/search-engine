"""The preserved modified-A homepage keeps its hidden QA footer and animation hooks."""
from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


class FooterParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.footer = None
        self.in_footer = False
        self.motion_control_inside = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'footer' and 'site-footer' in attrs.get('class', '').split():
            self.footer = attrs
            self.in_footer = True
        if self.in_footer and attrs.get('id') == 'background-motion-toggle':
            self.motion_control_inside = True

    def handle_endtag(self, tag):
        if tag == 'footer':
            self.in_footer = False


def test_public_footer_hidden_but_background_controller_retained():
    parser = FooterParser()
    parser.feed((ROOT / 'public/qa/home-modified-a.html').read_text(encoding='utf-8'))
    assert parser.footer is not None and 'hidden' in parser.footer
    assert parser.motion_control_inside


def test_hidden_footer_has_no_layout_box_even_at_mobile_breakpoints():
    css = (ROOT / 'public/css/style.css').read_text(encoding='utf-8')
    rule = re.search(r'\.site-footer\[hidden\]\s*\{([^}]+)\}', css)
    assert rule is not None
    assert re.search(r'display\s*:\s*none\s*!important\s*;?', rule[1])

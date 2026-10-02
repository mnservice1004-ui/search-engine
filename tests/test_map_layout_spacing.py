from pathlib import Path
import hashlib


def test_shared_floor_spacing_uses_second_floor_size_and_hides_caption():
    css = (Path(__file__).resolve().parents[1] / 'public/css/style.css').read_text(encoding='utf-8')
    assert '.map-panel{--map-frame-gap:26px;padding-bottom:var(--map-frame-gap)}' in css
    assert '.map-stage.map-cropped{--map-image-gap:19px;margin:0 var(--map-frame-gap);padding:var(--map-image-gap);min-height:0}' in css
    assert '.map-panel #route-text{display:none!important;margin:0;padding:0}' in css
    assert '.map-panel{--map-frame-gap:16px}' in css
    assert '.map-stage.map-cropped{--map-image-gap:16px}' in css
    assert '.map-stage.map-cropped #floor-image{aspect-ratio:2560/2000;object-fit:fill}' in css
    original = css.split('\n/* Shared floor layout:')[0]
    assert hashlib.sha256(original.encode('utf-8')).hexdigest() == 'd1aaefcb5cda35c7e3c8ef620b5b1786e530ae0728f3c9aef16c3baea25d7afd'


def test_routes_and_markers_follow_live_image_not_natural_ratio():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'public/js/app.js').read_text(encoding='utf-8')
    html = (root / 'public/index.html').read_text(encoding='utf-8')
    assert 'box.top * image.height / naturalHeight - 6' in js
    assert '(box.left + box.width / 2) * image.width / naturalWidth' in js
    assert 'routeEl.style.height = `${imageRect.height}px`;' in js
    assert 'routeEl.style.width = `${imageRect.width}px`;' in js
    assert 'preserveAspectRatio="none"' in html
    assert 'observer.observe(floorImageEl)' in js

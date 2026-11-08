"""S1-10 remaining advisories: pyasn1 0.6.5 and pypdf 6.21.4 keep the API's
own uses working. Offline: synthetic PDFs and certificates, no network."""
import importlib.metadata as metadata
import io
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def test_patched_versions_are_installed():
    assert metadata.version("pyasn1") == "0.6.5"
    assert metadata.version("pypdf") == "6.21.4"


def _pdf(pages):
    from reportlab.pdfgen import canvas
    out = io.BytesIO()
    doc = canvas.Canvas(out)
    for text in pages:
        doc.drawString(72, 720, text)
        doc.showPage()
    doc.save()
    return out.getvalue()


def test_document_translation_reads_every_pdf_page(tmp_path):
    from services.audio_router import _extract_document_text
    path = tmp_path / "script.pdf"
    path.write_bytes(_pdf(["Speaker A: hello", "Speaker B: goodbye"]))
    text = _extract_document_text(path)
    assert "Speaker A: hello" in text and "Speaker B: goodbye" in text


class _Response:
    status_code = 200

    def __init__(self, content):
        self.content = content


def test_assistant_reads_a_pdf_attachment_and_ignores_a_broken_one(monkeypatch):
    import main
    pdf = _pdf(["Invoice 42"] + ["filler"] * 35)
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: _Response(pdf))
    text = main._assistant_document_text({"url": "https://api.example/a.pdf", "mime": "application/pdf"})
    assert text.startswith("Invoice 42") and text.count("filler") == 29  # the first 30 pages only
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: _Response(b"%PDF-1.7\n" + b"\x00" * 64))
    assert main._assistant_document_text({"url": "https://api.example/b.pdf", "mime": "application/pdf"}) == ""


def test_pyasn1_decodes_a_real_certificate_and_rejects_garbage():
    from pyasn1.codec.der import decoder
    from pyasn1.error import PyAsn1Error
    from pyasn1_modules import rfc5280
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic.invalid")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(424242).not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    decoded, rest = decoder.decode(cert.public_bytes(serialization.Encoding.DER), asn1Spec=rfc5280.Certificate())
    assert rest == b"" and int(decoded["tbsCertificate"]["serialNumber"]) == 424242
    with pytest.raises(PyAsn1Error):
        decoder.decode(b"\x30\x84\xff\xff\xff\xff", asn1Spec=rfc5280.Certificate())

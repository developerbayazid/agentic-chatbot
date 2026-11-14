"""Loading text files and PDFs into page-aware sections."""

import pytest

import agentic_chatbot.loaders as loaders
from agentic_chatbot.loaders import DocumentLoadError, load_file


def _text_file(tmp_path, name="doc.md", content="# Title\n\nHello"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_text_file_is_one_section_without_page(tmp_path):
    result = load_file(_text_file(tmp_path))

    assert result.truncated is False
    assert len(result.sections) == 1
    assert result.sections[0].page is None
    assert "Hello" in result.sections[0].text


@pytest.mark.parametrize("suffix", [".txt", ".rst", ".markdown"])
def test_other_text_suffixes_load(tmp_path, suffix):
    path = tmp_path / f"doc{suffix}"
    path.write_text("content", encoding="utf-8")

    assert load_file(path).sections[0].text == "content"


def test_text_normalization(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("a\x00\r\n\n\n\n\nb\r\n", encoding="utf-8")

    assert load_file(path).sections[0].text == "a\n\nb"


def test_empty_text_file_is_an_error(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("   \n\n", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="no text"):
        load_file(path)


def test_unsupported_suffix_is_an_error(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"not text")

    with pytest.raises(DocumentLoadError, match="unsupported"):
        load_file(path)


class FakePage:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error

    def extract_text(self):
        if self._error is not None:
            raise self._error
        return self._text


class FakeReader:
    def __init__(self, pages, encrypted=False, password_ok=True):
        self.pages = pages
        self.is_encrypted = encrypted
        self._password_ok = password_ok

    def decrypt(self, password):
        return self._password_ok


def _patch_pdf(monkeypatch, reader):
    monkeypatch.setattr(loaders, "PdfReader", lambda path: reader)


def test_pdf_sections_carry_one_based_page_numbers(tmp_path, monkeypatch):
    _patch_pdf(
        monkeypatch,
        FakeReader([FakePage("Page one"), FakePage(None), FakePage("Page three")]),
    )

    result = load_file(tmp_path / "doc.pdf")

    assert [(section.page, section.text) for section in result.sections] == [
        (1, "Page one"),
        (3, "Page three"),
    ]
    assert result.truncated is False


def test_pdf_without_text_layer_is_an_error(tmp_path, monkeypatch):
    _patch_pdf(monkeypatch, FakeReader([FakePage(None), FakePage("")]))

    with pytest.raises(DocumentLoadError, match="scanned"):
        load_file(tmp_path / "doc.pdf")


def test_encrypted_pdf_requires_a_decryptable_password(tmp_path, monkeypatch):
    _patch_pdf(
        monkeypatch,
        FakeReader([FakePage("secret")], encrypted=True, password_ok=False),
    )

    with pytest.raises(DocumentLoadError, match="encrypted"):
        load_file(tmp_path / "doc.pdf")


def test_encrypted_pdf_with_empty_password_loads(tmp_path, monkeypatch):
    _patch_pdf(
        monkeypatch,
        FakeReader([FakePage("secret")], encrypted=True, password_ok=True),
    )

    assert load_file(tmp_path / "doc.pdf").sections[0].text == "secret"


def test_pdf_page_limit_sets_truncated(tmp_path, monkeypatch):
    _patch_pdf(
        monkeypatch,
        FakeReader([FakePage(f"page {index}") for index in range(1, 4)]),
    )

    result = load_file(tmp_path / "doc.pdf", max_pdf_pages=2)

    assert [section.page for section in result.sections] == [1, 2]
    assert result.truncated is True


def test_pdf_page_extraction_failure_is_wrapped(tmp_path, monkeypatch):
    _patch_pdf(
        monkeypatch,
        FakeReader([FakePage("ok"), FakePage(error=ValueError("broken"))]),
    )

    with pytest.raises(DocumentLoadError, match="page 2"):
        load_file(tmp_path / "doc.pdf")


def test_real_pdf_is_read_by_pypdf(tmp_path):
    path = tmp_path / "real.pdf"
    path.write_bytes(_pdf_bytes("Hello RAG"))

    result = load_file(path)

    assert result.sections[0].page == 1
    assert "Hello RAG" in result.sections[0].text


def _pdf_bytes(text):
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        (
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets = []

    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    output += b"0000000000 65535 f \n"

    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode("ascii")

    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    ).encode("ascii")

    return bytes(output)

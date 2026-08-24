"""Upload sanitization: PDF first-page rendering, guards, and the image path.

decode_and_sanitize is sync/CPU-bound by design (the API layer runs it in a
thread); these tests pin its validation behavior directly.
"""

import base64

import pytest
from PIL import Image

from app.core.images import ImageValidationError, ProcessedImage, decode_and_sanitize
from tests.pdf_fixtures import one_page_pdf, oversized_page_pdf, two_page_pdf


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _png_b64(size=(40, 30), color=(200, 10, 10)) -> str:
    img = Image.new("RGB", size, color)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return _b64(buf.getvalue())


def test_png_still_sanitizes_to_jpeg():
    processed = decode_and_sanitize(_png_b64(), "image/png")
    assert isinstance(processed, ProcessedImage)
    assert processed.mime == "image/jpeg"
    assert processed.source_pages is None


def test_pdf_renders_first_page_with_page_count():
    processed = decode_and_sanitize(_b64(two_page_pdf()), "application/pdf")
    assert processed.mime == "image/jpeg"
    assert processed.source_pages == 2  # disclosed so callers can be honest


def test_single_page_pdf_has_count_one():
    processed = decode_and_sanitize(_b64(one_page_pdf()), "application/pdf")
    assert processed.source_pages == 1


def test_oversized_pdf_page_rejected_before_render():
    with pytest.raises(ImageValidationError):
        decode_and_sanitize(_b64(oversized_page_pdf()), "application/pdf")


def test_corrupt_pdf_degrades_to_validation_error():
    with pytest.raises(ImageValidationError):
        decode_and_sanitize(_b64(b"this is definitely not a pdf"), "application/pdf")


def test_mime_not_in_allowlist_rejected():
    with pytest.raises(ImageValidationError):
        decode_and_sanitize(_png_b64(), "image/gif")


def test_invalid_base64_rejected():
    with pytest.raises(ImageValidationError):
        decode_and_sanitize("!!!not-base64!!!")


def test_oversized_payload_rejected():
    big = b"x" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ImageValidationError):
        decode_and_sanitize(_b64(big), "image/png")

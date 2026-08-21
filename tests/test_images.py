import base64
import io

import pytest
from PIL import Image

from app.core.config import settings
from app.core.images import (
    ImageValidationError,
    ProcessedImage,
    decode_and_sanitize,
    persist_image,
)


def _jpeg_b64(size=(2000, 1000), color=(200, 30, 30), exif: Image.Exif | None = None) -> str:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    if exif is not None:
        img.save(buf, format="JPEG", exif=exif.tobytes())
    else:
        img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _png_rgba_b64(size=(300, 200)) -> str:
    img = Image.new("RGBA", size, (10, 200, 90, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_sanitize_downscales_to_max_dimension():
    processed = decode_and_sanitize(_jpeg_b64((2000, 1000)), "image/jpeg")
    out = Image.open(io.BytesIO(base64.b64decode(processed.b64)))
    assert max(out.size) == settings.image_max_dimension_px
    assert out.size == (1024, 512)


def test_sanitize_leaves_small_images_untouched():
    processed = decode_and_sanitize(_jpeg_b64((320, 240)), "image/jpeg")
    out = Image.open(io.BytesIO(base64.b64decode(processed.b64)))
    assert out.size == (320, 240)


def test_sanitize_strips_exif_metadata():
    exif = Image.Exif()
    exif[0x010F] = "TestCameraMaker"  # Make tag
    processed = decode_and_sanitize(_jpeg_b64(exif=exif), "image/jpeg")
    out = Image.open(io.BytesIO(base64.b64decode(processed.b64)))
    assert not out.getexif()


def test_sanitize_reencodes_to_jpeg_and_flattens_transparency():
    processed = decode_and_sanitize(_png_rgba_b64(), "image/png")
    assert processed.mime == "image/jpeg"
    out = Image.open(io.BytesIO(base64.b64decode(processed.b64)))
    assert out.format == "JPEG"
    assert out.mode == "RGB"


def test_sanitize_computes_sha256_and_size():
    processed = decode_and_sanitize(_jpeg_b64(), "image/jpeg")
    raw = base64.b64decode(processed.b64)
    import hashlib

    assert processed.sha256 == hashlib.sha256(raw).hexdigest()
    assert processed.size_bytes == len(raw)


def test_sanitize_accepts_data_url_prefix():
    data_url = "data:image/jpeg;base64," + _jpeg_b64((100, 100))
    processed = decode_and_sanitize(data_url, "image/jpeg")
    assert processed.size_bytes > 0


def test_rejects_non_base64_payload():
    with pytest.raises(ImageValidationError, match="base64"):
        decode_and_sanitize("!!!not-base64!!!", "image/jpeg")


def test_rejects_non_image_bytes():
    garbage = base64.b64encode(b"definitely not an image").decode()
    with pytest.raises(ImageValidationError, match="do not decode"):
        decode_and_sanitize(garbage, "image/jpeg")


def test_rejects_disallowed_mime():
    with pytest.raises(ImageValidationError, match="Unsupported image type"):
        decode_and_sanitize(_jpeg_b64(), "image/gif")


def test_reject_oversized_raw_upload(monkeypatch):
    monkeypatch.setattr(settings, "image_max_bytes", 100)
    with pytest.raises(ImageValidationError, match="too large"):
        decode_and_sanitize(_jpeg_b64(), "image/jpeg")


def test_persist_image_writes_file_and_sets_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "image_upload_dir", str(tmp_path / "uploads"))
    processed = decode_and_sanitize(_jpeg_b64((100, 100)), "image/jpeg")
    path = persist_image(processed, "turn-abc")

    assert path == f"{(tmp_path / 'uploads').name}/turn-abc.jpg"
    assert processed.path == path
    written = (tmp_path / "uploads" / "turn-abc.jpg").read_bytes()
    assert base64.b64decode(processed.b64) == written


def test_processed_image_defaults():
    image = ProcessedImage(b64="abc", mime="image/jpeg", size_bytes=3, sha256="h")
    assert image.path is None

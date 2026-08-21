import base64
import binascii
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import settings
from .logging import get_logger

logger = get_logger("app.core.images")

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# Re-encode target: uniform JPEG output strips EXIF/GPS metadata and any
# animation regardless of the input format.
_OUTPUT_FORMAT = "JPEG"
_OUTPUT_MIME = "image/jpeg"
_JPEG_QUALITY = 85


class ImageValidationError(ValueError):
    """Raised when an uploaded image fails validation."""


@dataclass
class ProcessedImage:
    """A validated, sanitized image ready for model calls and persistence."""

    b64: str  # sanitized base64 (re-encoded) sent to models / Celery
    mime: str  # always image/jpeg after re-encoding
    size_bytes: int
    sha256: str
    path: str | None = None  # relative upload path once persisted


def _decode_base64(image_b64: str) -> bytes:
    stripped = image_b64.strip()
    if stripped.startswith("data:"):
        _, _, stripped = stripped.partition(",")
    try:
        return base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError):
        raise ImageValidationError("image_b64 is not valid base64")


def decode_and_sanitize(image_b64: str, image_mime: str | None = None) -> ProcessedImage:
    """Validate and sanitize a base64-encoded upload.

    Checks size and mime allowlist, verifies the bytes decode as a real image,
    strips all metadata by re-encoding, and downscales to
    ``IMAGE_MAX_DIMENSION_PX`` to bound vision-token usage.
    """
    raw = _decode_base64(image_b64)
    if len(raw) > settings.image_max_bytes:
        raise ImageValidationError(
            f"Image too large: {len(raw)} bytes (max {settings.image_max_bytes})"
        )
    if image_mime is not None and image_mime not in settings.image_allowed_mime:
        raise ImageValidationError(
            f"Unsupported image type {image_mime!r} "
            f"(allowed: {', '.join(settings.image_allowed_mime)})"
        )

    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            width, height = img.size
            if width <= 0 or height <= 0:
                raise ImageValidationError("Image has no pixels")
            if img.mode in ("RGBA", "LA", "P", "PA"):
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                out = background
            elif img.mode != "RGB":
                out = img.convert("RGB")
            else:
                out = img.copy()

            max_dim = settings.image_max_dimension_px
            if max(out.size) > max_dim:
                out.thumbnail((max_dim, max_dim), Image.LANCZOS)

            buffer = io.BytesIO()
            out.save(buffer, format=_OUTPUT_FORMAT, quality=_JPEG_QUALITY)
    except UnidentifiedImageError:
        raise ImageValidationError("Bytes do not decode as a supported image")
    except OSError as exc:
        raise ImageValidationError(f"Image could not be processed: {exc}")

    encoded = buffer.getvalue()
    if len(encoded) > settings.image_max_bytes:
        raise ImageValidationError(
            f"Image too large after processing: {len(encoded)} bytes (max {settings.image_max_bytes})"
        )
    return ProcessedImage(
        b64=base64.b64encode(encoded).decode("ascii"),
        mime=_OUTPUT_MIME,
        size_bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


def persist_image(image: ProcessedImage, turn_id: str) -> str:
    """Write the sanitized bytes under IMAGE_UPLOAD_DIR; return the relative path.

    The path is relative to the upload dir's parent so it stays portable
    across store backends; audit events carry this path plus the hash.
    """
    upload_dir = Path(settings.image_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{turn_id}.jpg"
    (upload_dir / filename).write_bytes(base64.b64decode(image.b64))
    image.path = f"{upload_dir.name}/{filename}"
    logger.info("image.persisted", path=image.path, sha256=image.sha256, size_bytes=image.size_bytes)
    return image.path

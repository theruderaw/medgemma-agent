import base64
import binascii
import hashlib
import io
import re
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

PDF_MIME = "application/pdf"

# Re-encode target: uniform JPEG output strips EXIF/GPS metadata and any
# animation regardless of the input format.
_OUTPUT_FORMAT = "JPEG"
_OUTPUT_MIME = "image/jpeg"
_JPEG_QUALITY = 85

# PDF hardening: a page whose point dimensions exceed this bound is rejected
# before rendering — pdfium rasterizes at scale, so an absurd page size
# (or a crafted one) would allocate a huge bitmap.
_PDF_MAX_PAGE_DIM_PT = 20000
# Render scale ceiling: tiny pages are upscaled at most this much so dense
# prescription text survives the later longest-edge downscale.
_PDF_MAX_SCALE = 3.0


class ImageValidationError(ValueError):
    """Raised when an uploaded image (or PDF) fails validation."""


@dataclass
class ProcessedImage:
    """A validated, sanitized image ready for model calls and persistence."""

    b64: str  # sanitized base64 (re-encoded) sent to models / Celery
    mime: str  # always image/jpeg after re-encoding
    size_bytes: int
    sha256: str
    path: str | None = None  # relative upload path once persisted
    # Source document page count (PDF uploads only); None for plain images.
    # Lets callers disclose "first page of N" honestly downstream.
    source_pages: int | None = None


def _decode_base64(image_b64: str) -> bytes:
    stripped = image_b64.strip()
    if stripped.startswith("data:"):
        _, _, stripped = stripped.partition(",")
    try:
        return base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError):
        raise ImageValidationError("image_b64 is not valid base64")


def _sanitize_pil(img: Image.Image) -> bytes:
    """Metadata-stripping re-encode + longest-edge downscale. Shared by the
    image and PDF paths so every stored artifact is a uniform JPEG."""
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
    return buffer.getvalue()


def _render_pdf_first_page(raw: bytes) -> tuple[bytes, int]:
    """Render a PDF's first page to sanitized JPEG bytes; return (jpeg, pages).

    Only page 1 reaches models in v1; the total page count rides on the
    ProcessedImage so callers can disclose the truncation honestly. pypdfium2
    is imported lazily: it is only needed when someone actually uploads a PDF.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - packaging guard
        raise ImageValidationError(
            "PDF support is unavailable on this deployment (pypdfium2 missing)"
        ) from exc

    try:
        doc = pdfium.PdfDocument(io.BytesIO(raw))
    except Exception as exc:
        raise ImageValidationError(f"Bytes do not decode as a PDF document: {exc}") from exc

    try:
        page_count = len(doc)
        if page_count < 1:
            raise ImageValidationError("PDF contains no pages")
        page = doc[0]
        width_pt, height_pt = page.get_size()
        if max(width_pt, height_pt) > _PDF_MAX_PAGE_DIM_PT or min(width_pt, height_pt) <= 0:
            raise ImageValidationError("PDF page dimensions are out of bounds")

        target = float(settings.image_max_dimension_px)
        scale = min(target / max(width_pt, height_pt), _PDF_MAX_SCALE)
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
    finally:
        doc.close()

    return _sanitize_pil(pil_image), page_count


def decode_and_sanitize(image_b64: str, image_mime: str | None = None) -> ProcessedImage:
    """Validate and sanitize a base64-encoded upload.

    Checks size and mime allowlist, verifies the bytes decode as a real
    image (or renders the first page for PDFs), strips all metadata by
    re-encoding to JPEG, and downscales to ``IMAGE_MAX_DIMENSION_PX`` to
    bound vision-token usage.

    Synchronous and CPU-bound by design: async callers should run it via
    ``anyio.to_thread`` (see ``app/api/images.py``).
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

    source_pages: int | None = None
    try:
        if image_mime == PDF_MIME:
            encoded, source_pages = _render_pdf_first_page(raw)
        else:
            try:
                with Image.open(io.BytesIO(raw)) as img:
                    img.load()
                    encoded = _sanitize_pil(img)
            except UnidentifiedImageError:
                raise ImageValidationError("Bytes do not decode as a supported image")
            except OSError as exc:
                raise ImageValidationError(f"Image could not be processed: {exc}")
    except ImageValidationError:
        raise
    except Exception as exc:
        # pdfium render failures (corrupt xref, encryption, ...) degrade to a
        # validation error, never a 500.
        raise ImageValidationError(f"Upload could not be processed: {exc}") from exc

    if len(encoded) > settings.image_max_bytes:
        raise ImageValidationError(
            f"Image too large after processing: {len(encoded)} bytes (max {settings.image_max_bytes})"
        )
    return ProcessedImage(
        b64=base64.b64encode(encoded).decode("ascii"),
        mime=_OUTPUT_MIME,
        size_bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(),
        source_pages=source_pages,
    )


def persist_image(image: ProcessedImage, turn_id: str) -> str:
    """Write the sanitized bytes under IMAGE_UPLOAD_DIR; return the relative path.

    The path is relative to the upload dir's parent so it stays portable
    across store backends; audit events carry this path plus the hash. Every
    artifact — including rendered PDF pages — is stored as JPEG.
    """
    upload_dir = Path(settings.image_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{turn_id}.jpg"
    (upload_dir / filename).write_bytes(base64.b64decode(image.b64))
    image.path = f"{upload_dir.name}/{filename}"
    logger.info("image.persisted", path=image.path, sha256=image.sha256, size_bytes=image.size_bytes)
    return image.path


# Audit payloads only ever carry names minted by persist_image; anything else
# is rejected so a tampered audit row cannot delete outside the store.
_UPLOAD_NAME_RE = re.compile(r"^uploads/[0-9a-f]{32}\.jpg$")


def delete_upload(rel_path: str) -> bool:
    """Delete a stored upload by its audit-relative path (``uploads/<id>.jpg``).

    Returns True when a file was removed; False for malformed paths or
    already-missing files, so callers can sweep best-effort without failing.
    """
    if not _UPLOAD_NAME_RE.fullmatch(rel_path):
        return False
    target = Path(settings.image_upload_dir) / Path(rel_path).name
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("image.delete_failed", path=rel_path, error=str(exc))
        return False
    logger.info("image.deleted", path=rel_path)
    return True

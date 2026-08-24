"""Shared request-layer upload validation for the chat and triage endpoints.

``decode_and_sanitize`` is CPU-bound (Pillow re-encode, pdfium page render),
so it runs in a worker thread to keep the event loop responsive.
"""

import anyio.to_thread
from fastapi import HTTPException

from ..core.images import ImageValidationError, ProcessedImage, decode_and_sanitize
from .schemas import ImageMeta


async def prepare_image(image_b64: str | None, image_mime: str | None) -> ProcessedImage | None:
    """Validate an optional upload into a sanitized ProcessedImage.

    Raises 422 when validation fails or only one of the two fields is given.
    """
    if image_b64 is None and image_mime is None:
        return None
    if image_b64 is None or image_mime is None:
        raise HTTPException(
            status_code=422,
            detail="image_b64 and image_mime must be provided together",
        )
    try:
        return await anyio.to_thread.run_sync(decode_and_sanitize, image_b64, image_mime)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def image_meta(image: ProcessedImage) -> ImageMeta:
    return ImageMeta(
        path=image.path or "",
        sha256=image.sha256,
        mime=image.mime,
        size_bytes=image.size_bytes,
    )

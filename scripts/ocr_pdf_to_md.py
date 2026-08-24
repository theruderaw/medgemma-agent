"""OCR handwritten pages (PDF or images) into Markdown using PaddleOCR PP-StructureV3.

Basic smoke tool: every page/image is run through the document-parsing pipeline,
the recognized content is printed to stdout, and the full transcription is
written next to the input as `<name>.md` unless -o says otherwise.

Usage:
    .venv/bin/python scripts/ocr_pdf_to_md.py path/to/scanned.pdf [-o out.md]
    .venv/bin/python scripts/ocr_pdf_to_md.py img1.jpg img2.png ...
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

# paddle 3.3.x has a PIR+oneDNN CPU regression (ConvertPirAttribute2RuntimeAttribute
# crash); we pin 3.2.2, and this keeps MKLDNN off regardless of installed version.
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")

from paddlex import create_pipeline  # noqa: E402
from paddlex.inference.models.runners.paddle_static.config.pp_option import (  # noqa: E402
    PaddlePredictorOption,
)

# Vertical pixel cap for rendered pages. paddlex's own PDF rendering uses a fixed
# 2x scale and ignores smaller caps, which made its text-det model request a
# ~21 GB allocation (box has 14 GB) -> ResourceExhaustedError. So we render each
# page ourselves at <=1024 px tall and feed images, never the PDF path.
VERT_CAP_PX = 1024


def render_pages(pdf: Path):
    """Yield one RGB uint8/float numpy image per page, height <= VERT_CAP_PX."""
    doc = pdfium.PdfDocument(str(pdf))
    for page in doc:
        _, h_pt = page.get_size()
        img = page.render(scale=VERT_CAP_PX / h_pt).to_numpy()
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        if img.shape[2] == 4:
            img = img[:, :, :3]
        yield img


def page_markdown(res, tmp_dir: Path, idx: int) -> str:
    """Extract one page's markdown text, preferring the in-memory dict."""
    md = getattr(res, "markdown", None)
    if isinstance(md, dict):
        texts = md.get("markdown_texts")
        if isinstance(texts, str):
            return texts
        if isinstance(texts, list):
            return "\n".join(str(t) for t in texts)
    # Fallback: the official saver into an isolated dir (avoids name clashes).
    page_dir = tmp_dir / f"page_{idx}"
    res.save_to_markdown(str(page_dir))
    files = sorted(page_dir.rglob("*.md"))
    return files[0].read_text(encoding="utf-8") if files else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Handwritten PDF/images -> Markdown via PaddleOCR.")
    parser.add_argument("inputs", type=Path, nargs="+", help="Input PDF/image file(s)")
    parser.add_argument("-o", "--output", type=Path, help="Output .md path (default: <first-input>.md)")
    args = parser.parse_args()

    paths = [p.resolve() for p in args.inputs]
    for p in paths:
        if not p.is_file():
            print(f"error: {p} not found", file=sys.stderr)
            return 1

    # Doc orientation/unwarping off: scans of flat pages don't need them.
    # run_mode="paddle": plain interpreter, avoids the MKLDNN+PIR crash noted above.
    pipeline = create_pipeline(
        pipeline="PP-StructureV3",
        device="cpu",
        pp_option=PaddlePredictorOption(run_mode="paddle"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ocr_pdf_") as tmp:
        tmp_dir = Path(tmp)
        for p in paths:
            # PDFs: render ourselves at <=1024 px tall (paddlex's own PDF rendering
            # uses a fixed 2x scale and OOMs). Images: pass the path straight through.
            if p.suffix.lower() == ".pdf":
                inputs = list(render_pages(p))
            else:
                # Extensions in the wild lie (GIFs named .jpg etc.); PIL sniffs
                # the real format, so decode ourselves and hand over arrays.
                with Image.open(p) as im:
                    inputs = [np.asarray(im.convert("RGB"))]
            for i, res in enumerate(pipeline.predict(inputs), start=1):
                print(f"\n===== {p.name} page {i} =====")
                text = page_markdown(res, tmp_dir, i)
                print(text)
                parts.append(text)

    out = args.output or paths[0].with_suffix(".md")
    out.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Minimal valid single/multi-page PDFs built by hand (no PDF-writing dep).

The xref table is deliberately bogus; pypdfium2 rebuilds it when parsing
falls over, which keeps these tiny while still exercising real rendering.
"""

PAGE_1 = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count %d>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
EXTRA_PAGE = b"\n4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"


def _wrap(body: bytes) -> bytes:
    return (
        b"%PDF-1.4\n"
        + body
        + b"xref\n0 9\n0000000000 65535 f \ntrailer<</Size 9/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )


def one_page_pdf() -> bytes:
    return _wrap(PAGE_1 % 1)


def two_page_pdf() -> bytes:
    # %d fills Count=2; then extend the Kids array with the extra page object.
    kids = (PAGE_1 % 2)[:-1].decode().replace("[3 0 R]", "[3 0 R 4 0 R]").encode()
    return _wrap(kids + EXTRA_PAGE)


def oversized_page_pdf() -> bytes:
    body = (
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 99999 99999]>>endobj\n"
    )
    return _wrap(body)

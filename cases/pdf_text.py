"""Text extraction from an uploaded PDF. Only the text is used; the file itself is held in memory and then dropped.

PDFs are untrusted input, so this module is deliberately strict: size and page limits, no encrypted files, no OCR,
and any parser failure becomes one friendly message (never a stack trace, never the file's contents in a log).
"""
import io
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Everything below a space except tab and newline, plus DEL. Form feeds (page breaks) are turned into newlines first.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


class PdfProblem(Exception):
    """Carries a message that is safe to show the user."""


def clean_text(raw):
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(data):
    """Return (text, page_count) for the PDF bytes, or raise PdfProblem."""
    from pypdf import PdfReader  # imported here so the rest of the site works even if pypdf is missing

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise PdfProblem("That PDF is password-protected or encrypted. Remove the protection, or paste the text.")
        pages = len(reader.pages)
        if pages > settings.MAX_PDF_PAGES:
            raise PdfProblem(f"That PDF has {pages} pages (maximum {settings.MAX_PDF_PAGES}). "
                             "Upload the relevant pages, or paste the text.")
        chunks, total = [], 0
        for page in reader.pages:
            chunk = page.extract_text() or ""
            chunks.append(chunk)
            total += len(chunk)
            if total > settings.MAX_DOCUMENT_CHARS * 2:     # far past the limit already; stop reading
                break
    except PdfProblem:
        raise
    except Exception as e:      # pypdf raises many error types for damaged files; none of them is the user's problem
        logger.warning("PDF could not be read: %s", type(e).__name__)
        raise PdfProblem("That PDF could not be read. It may be damaged. Try another copy, or paste the text.") from e

    text = clean_text("\n\n".join(chunks))
    if not text:
        raise PdfProblem("That PDF has no selectable text (it may be a scan or a photo). Scanned PDFs are not "
                         "supported; paste the text instead.")
    return text, pages

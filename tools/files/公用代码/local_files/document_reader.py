"""Detect a local file's format and extract readable text for the read tools.

Text is decoded verbatim so callers keep the original bytes; PDF, Word,
PowerPoint, Excel, HTML, EPUB and notebook files are converted to Markdown by
document_converter (MarkItDown). Images are not transcribed: an image file
returns its dimensions and byte size, and embedded images are counted, so the
model knows they exist without inventing their content. The leading bytes decide
first and the extension only breaks ties, so renamed or extensionless files
still resolve, while unsupported binaries fail with an actionable message.
"""
import codecs
import io
import zipfile
from pathlib import Path

from PIL import Image

from .document_converter import convert_document

TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "utf-16", "utf-16-le", "utf-16-be")
HTML_SUFFIXES = {".html", ".htm", ".xhtml"}
# Suffixes that stay plain text even when their content looks like Markdown or HTML.
TEXT_SUFFIXES = {
    ".txt", ".text", ".md", ".markdown", ".mdx", ".rst", ".log", ".csv", ".tsv",
    ".json", ".jsonl", ".ndjson", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".properties", ".srt", ".vtt", ".sql",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
                  ".tif", ".tiff", ".heic", ".heif", ".avif", ".ico"}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"II*\x00", b"MM\x00*")
ZIP_DOCUMENTS = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
}
MEDIA_PREFIXES = {"docx": "word/media/", "xlsx": "xl/media/", "pptx": "ppt/media/"}
ODF_MIMES = ("application/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.spreadsheet",
             "application/vnd.oasis.opendocument.presentation")


class UnsupportedFormat(ValueError):
    """The path is readable but its format cannot be turned into text."""


def extract(path: Path, data: bytes, encoding: str | None = None):
    """Return (text, format, encoding, warnings) for one validated file."""
    kind = detect(path.suffix.casefold(), data)
    if kind == "text":
        text, used, warnings = decode_text(data, encoding)
        if not text:
            warnings.append("File is empty or contains no text.")
        return text, kind, used, warnings
    if kind == "image":
        text, warnings = image_text(data, path.suffix)
        return text, "image", None, warnings
    try:
        text = convert_document(str(path))
    except Exception as exc:  # MarkItDown reports its own exception hierarchy.
        raise UnsupportedFormat(f"Cannot parse {kind} file: {exc}") from exc
    warnings = [] if text.strip() else ["No extractable text; the file may be empty or contain only images or scans."]
    media = _media_count(data, kind)
    if media:
        warnings.append(f"{media} embedded image(s) were not transcribed (no OCR); alt text or placeholders remain in the content.")
    return text, kind, None, warnings


def detect(suffix: str, data: bytes) -> str:
    """Pick the reader from the file signature, falling back to the extension."""
    head = data[:8192]
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(ZIP_MAGIC):
        return _zip_kind(data)
    if head.startswith(OLE_MAGIC):
        return _ole_kind(suffix)
    if head.startswith(b"{\\rtf"):
        raise UnsupportedFormat("RTF is not supported; save the document as .docx or .pdf first")
    if head.startswith(b"%!PS"):
        raise UnsupportedFormat("PostScript is not supported; save the document as .pdf first")
    if head.startswith(IMAGE_MAGIC) or suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix == ".ipynb":
        return "ipynb"
    if suffix in HTML_SUFFIXES or (suffix not in TEXT_SUFFIXES and _looks_html(head)):
        return "html"
    if b"\x00" in head:
        raise UnsupportedFormat("Binary file is not a supported document format")
    return "text"


def _zip_kind(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            for entry, kind in ZIP_DOCUMENTS.items():
                if entry in names:
                    return kind
            if "mimetype" in names:
                mime = archive.read("mimetype").decode("ascii", "ignore").strip()
                if mime == "application/epub+zip":
                    return "epub"
                if mime.startswith(ODF_MIMES):
                    raise UnsupportedFormat("OpenDocument files are not supported; save as .docx, .xlsx or .pptx first")
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormat("Damaged ZIP container; the document cannot be parsed") from exc
    raise UnsupportedFormat("ZIP archives are not documents; list the directory or extract the file first")


def _ole_kind(suffix: str) -> str:
    if suffix == ".xls":
        return "xls"
    raise UnsupportedFormat("Legacy OLE documents (.doc/.ppt/.msg) are not supported; save as .docx, .pptx, .xlsx or .pdf first")


def _looks_html(head: bytes) -> bool:
    start = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return start.startswith(b"<!doctype html") or start.startswith(b"<html")


def image_text(data: bytes, suffix: str):
    """Describe an image instead of transcribing it, so the read never fails."""
    info = image_info(data, suffix)
    lines = ["Image metadata", f"Format: {info['format']}", f"Bytes: {len(data)}"]
    if info["width"] and info["height"]:
        lines.append(f"Dimensions: {info['width']} x {info['height']} px")
    if info["mode"]:
        lines.append(f"Mode: {info['mode']}")
    lines += ["", "OCR is not performed, so text inside the image is not available."]
    return "\n".join(lines) + "\n", ["OCR is not performed; only image metadata is available."]


def image_info(data: bytes, suffix: str) -> dict:
    try:
        with Image.open(io.BytesIO(data)) as image:
            return {"format": (image.format or suffix.lstrip(".")).upper(),
                    "width": image.width, "height": image.height, "mode": image.mode}
    except Exception:  # Truncated or unsupported image: metadata is best effort.
        return {"format": suffix.lstrip(".").upper() or "unknown", "width": None, "height": None, "mode": None}


def _media_count(data: bytes, kind: str) -> int:
    prefix = MEDIA_PREFIXES.get(kind)
    if not prefix:
        return 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return sum(1 for name in archive.namelist() if name.startswith(prefix) and not name.endswith("/"))
    except zipfile.BadZipFile:
        return 0


def decode_text(data: bytes, encoding: str | None = None):
    """Return (text, encoding used, warnings); auto-detects common Chinese encodings."""
    if encoding not in (None, "", "auto"):
        if encoding not in TEXT_ENCODINGS:
            raise ValueError(f"encoding must be auto or one of: {', '.join(TEXT_ENCODINGS)}")
        try:
            return data.decode(encoding), encoding, []
        except UnicodeError as exc:
            raise UnsupportedFormat(f"Cannot decode the file as {encoding}: {exc}") from exc
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig", []
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16"), "utf-16", []
    if b"\x00" in data[:8192]:
        raise UnsupportedFormat("Binary file, or UTF-16 without a BOM; pass encoding=utf-16-le or utf-16-be")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and _plausible(text):
        return text, "utf-8", []
    try:
        text = data.decode("gb18030")
    except UnicodeDecodeError as exc:
        raise UnsupportedFormat("Cannot decode as utf-8 or gb18030; pass encoding explicitly") from exc
    if not _plausible(text):
        raise UnsupportedFormat("Cannot decode as utf-8 or gb18030; pass encoding explicitly")
    return text, "gb18030", ["Decoded as gb18030; pass encoding to override."]


def _plausible(text: str) -> bool:
    """Reject binaries that happen to decode: allow a small rate of control characters."""
    sample = text[:4096]
    if not sample:
        return True
    bad = 0
    for char in sample:
        code = ord(char)
        if char in "\t\n\r\f\v":
            continue
        if code < 32 or 0x7F <= code < 0xA0 or 0xE000 <= code <= 0xF8FF or code in (0xFFFD, 0xFFFE, 0xFFFF):
            bad += 1
    return bad <= max(4, len(sample) // 100)

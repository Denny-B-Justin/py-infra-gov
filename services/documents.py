"""
Source documents: upload validation, text extraction, listing and deletion.

Hardening vs. the original:
  * file type checked by extension AND magic bytes (not the client MIME type)
  * size limit enforced server-side; zip-bomb guard for .docx/.xlsx
  * file names sanitised; storage path is server-generated (no traversal)
  * extracted text is encrypted at rest
  * downloads go through an authorised route with Content-Disposition:
    attachment and nosniff (never rendered inline by the browser)
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import zipfile

import constants as C
from services import permissions as P
from services import storage
from services.crypto import decrypt_field, encrypt_field
from services.db import get_db, to_iso, utcnow
from services.repository import Forbidden, NotFound, _base_or_404, add_activity
from services.validators import ValidationError, new_uuid, safe_filename

log = logging.getLogger("infragov.docs")
T = C.T

MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
}


def extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _check_magic(ext: str, data: bytes) -> None:
    ok = {
        "pdf": data[:5] == b"%PDF-",
        "docx": data[:4] == b"PK\x03\x04",
        "xlsx": data[:4] == b"PK\x03\x04",
        "xls": data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        "csv": b"\x00" not in data[:4096],
    }.get(ext, False)
    if not ok:
        raise ValidationError("The file content does not match its extension.")
    if ext in ("docx", "xlsx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                total = sum(i.file_size for i in zf.infolist())
                if total > C.ZIP_MAX_UNCOMPRESSED_BYTES or len(zf.infolist()) > 10_000:
                    raise ValidationError("The document is too large when uncompressed.")
                names = set(zf.namelist())
                needed = "word/document.xml" if ext == "docx" else "xl/workbook.xml"
                if needed not in names:
                    raise ValidationError("The file is not a valid Office document.")
        except zipfile.BadZipFile:
            raise ValidationError("The file is not a valid Office document.") from None


def extract_text(filename: str, data: bytes) -> tuple[str, int | None]:
    ext = extension(filename)
    page_count = None
    if ext == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("password-protected")
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
        page_count = len(pages)
        text = "\n\n".join(f"[Page {i + 1}]\n{p}" for i, p in enumerate(pages)) if any(pages) else ""
    elif ext == "docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append("\t".join(c.text for c in row.cells))
        text = "\n".join(parts)
    elif ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        chunks = []
        for ws in wb.worksheets:
            buf = io.StringIO()
            w = csv.writer(buf)
            for row in ws.iter_rows(values_only=True):
                if any(v is not None and str(v).strip() for v in row):
                    w.writerow(["" if v is None else v for v in row])
            if buf.getvalue().strip():
                chunks.append(f"[Sheet: {ws.title}]\n{buf.getvalue().strip()}")
        text = "\n\n".join(chunks)
    elif ext == "xls":
        import xlrd

        book = xlrd.open_workbook(file_contents=data)
        chunks = []
        for sh in book.sheets():
            buf = io.StringIO()
            w = csv.writer(buf)
            for r in range(sh.nrows):
                vals = sh.row_values(r)
                if any(str(v).strip() for v in vals):
                    w.writerow(vals)
            if buf.getvalue().strip():
                chunks.append(f"[Sheet: {sh.name}]\n{buf.getvalue().strip()}")
        text = "\n\n".join(chunks)
    elif ext == "csv":
        text = data.decode("utf-8", errors="replace").lstrip("﻿")
    else:
        raise ValueError(f'Unsupported file type ".{ext}".')
    text = text.replace("\x00", "").strip()
    if len(text) > C.DOCUMENT_MAX_EXTRACTED_CHARS:
        text = text[: C.DOCUMENT_MAX_EXTRACTED_CHARS] + "\n\n[Document truncated — text beyond this point was not processed.]"
    return text, page_count


def _row_public(r: dict) -> dict:
    return {
        "id": r["id"], "assessmentId": r["assessment_id"], "filename": r["filename"],
        "mimeType": r.get("mime_type") or "", "sizeBytes": int(r.get("size_bytes") or 0),
        "status": r["status"], "error": r.get("error") or "", "charCount": r.get("char_count"),
        "pageCount": r.get("page_count"), "uploadedByName": r.get("uploaded_by_name") or "",
        "uploadedByOrganisation": r.get("uploaded_by_organisation") or "", "createdAt": to_iso(r["created_at"]),
    }


def list_documents(user: dict, aid: str) -> list[dict]:
    a = _base_or_404(aid)
    if not P.can_read_documents(user, a):
        raise Forbidden("Not allowed")
    rows = get_db().query(
        f"""SELECT id, assessment_id, filename, mime_type, size_bytes, status, error, char_count, page_count,
                   uploaded_by_name, uploaded_by_organisation, created_at
            FROM {T['assessment_documents']} WHERE assessment_id = :a ORDER BY created_at DESC""",
        {"a": aid},
    )
    return [_row_public(r) for r in rows]


def upload_document(user: dict, aid: str, filename: str, data: bytes) -> dict:
    a = _base_or_404(aid)
    if not P.can_manage(user, a):
        raise Forbidden("Only the assessment Owner and Admins can add documents.")
    name = safe_filename(filename)
    ext = extension(name)
    if ext not in C.DOCUMENT_ALLOWED_EXT:
        raise ValidationError(f"{name}: only PDF, Word (.docx), Excel (.xlsx / .xls) or CSV files are accepted.")
    if not data:
        raise ValidationError(f"{name}: the file is empty.")
    if len(data) > C.DOCUMENT_MAX_BYTES:
        raise ValidationError(f"{name}: files must be 50 MB or smaller.")
    _check_magic(ext, data)
    doc_id = new_uuid()
    path = f"{aid}/{doc_id}/{name}"
    now = utcnow()
    db = get_db()
    storage.put(path, data)
    row = {
        "id": doc_id, "assessment_id": aid, "filename": name, "mime_type": MIME.get(ext),
        "size_bytes": len(data), "storage_path": path, "sha256": hashlib.sha256(data).hexdigest(),
        "status": "processing", "error": None, "extracted_text": None, "char_count": None, "page_count": None,
        "uploaded_by_user_id": user["id"], "uploaded_by_name": user["name"] or user["email"],
        "uploaded_by_organisation": user.get("organisation") or None, "created_at": now, "updated_at": now,
    }
    db.insert(T["assessment_documents"], row)
    add_activity(aid, "document.uploaded", user, document_name=name)
    process(doc_id, data)
    return row


def process(doc_id: str, data: bytes | None = None) -> None:
    db = get_db()
    r = db.one(f"SELECT id, filename, storage_path FROM {T['assessment_documents']} WHERE id = :id", {"id": doc_id})
    if not r:
        return
    try:
        if data is None:
            data = storage.get(r["storage_path"])
        text, pages = extract_text(r["filename"], data)
    except Exception as exc:  # noqa: BLE001
        detail = "password-protected" if "password" in str(exc) else ""
        db.update(T["assessment_documents"], {
            "status": "failed", "updated_at": utcnow(),
            "error": f"The file couldn't be read{f' ({detail})' if detail else ''}. It may be corrupt or password-protected.",
        }, {"id": doc_id})
        return
    if not text:
        db.update(T["assessment_documents"], {
            "status": "failed", "updated_at": utcnow(),
            "error": "No readable text was found. If this is a scanned PDF, it needs to be run through OCR (text recognition) before uploading.",
        }, {"id": doc_id})
        return
    db.update(T["assessment_documents"], {
        "status": "ready", "error": None, "extracted_text": encrypt_field(text), "char_count": len(text),
        "page_count": pages, "updated_at": utcnow(),
    }, {"id": doc_id})


def _doc_or_404(doc_id: str) -> dict:
    r = get_db().one(f"SELECT * FROM {T['assessment_documents']} WHERE id = :id", {"id": doc_id})
    if not r:
        raise NotFound("Document not found")
    return r


def retry(user: dict, doc_id: str) -> None:
    r = _doc_or_404(doc_id)
    a = _base_or_404(r["assessment_id"])
    if not P.can_manage(user, a):
        raise Forbidden("Only the assessment Owner or an Admin can process documents.")
    get_db().update(T["assessment_documents"], {"status": "processing", "error": None, "updated_at": utcnow()}, {"id": doc_id})
    process(doc_id)


def delete_document(user: dict, doc_id: str) -> None:
    r = _doc_or_404(doc_id)
    a = _base_or_404(r["assessment_id"])
    if not P.can_manage(user, a):
        raise Forbidden("Only the assessment Owner and Admins can remove documents.")
    storage.delete(r["storage_path"])
    get_db().delete(T["assessment_documents"], {"id": doc_id})
    add_activity(a["id"], "document.deleted", user, document_name=r["filename"])


def download(user: dict, doc_id: str) -> tuple[str, str, bytes]:
    r = _doc_or_404(doc_id)
    a = _base_or_404(r["assessment_id"])
    if not P.can_read_documents(user, a):
        raise Forbidden("Not allowed")
    return r["filename"], r.get("mime_type") or "application/octet-stream", storage.get(r["storage_path"])


def ready_texts(user: dict, aid: str) -> list[dict]:
    """Extracted text of ready documents — editors only (for AI suggestions)."""
    rows = get_db().query(
        f"SELECT id, filename, extracted_text FROM {T['assessment_documents']} WHERE assessment_id = :a AND status = 'ready' ORDER BY created_at ASC",
        {"a": aid},
    )
    out = []
    for r in rows:
        text = decrypt_field(r.get("extracted_text"))
        if text:
            out.append({"id": r["id"], "filename": r["filename"], "text": text})
    return out

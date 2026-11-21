"""
Exports (CSV, editable Word round-trip) and the Word round-trip import parser.

CSV cells are neutralised against spreadsheet formula injection and written
with a UTF-8 BOM (same as the original) so Excel keeps accented characters.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import datetime, timezone

from services.respondents import is_document_review  # noqa: F401  (kept for parity)
from services.validators import ValidationError, csv_safe
from utils import framework as F
from utils.countries import fy_range_display

ROUNDTRIP_DOC_MARKER = "InfraGov Round-Trip Document"
ROUNDTRIP_COLUMNS = ["MBI", "Indicator (do not edit)", "Key Respondents", "Data Source", "Result Summary", "Result Detail", "Maturity Level"]
MATURITY_WORD_TO_SCORE = {
    "incipient": 1, "incipiente": 1, "initial": 1, "nascent": 2, "naissant": 2, "naciente": 2, "nascente": 2,
    "emerging": 3, "emergent": 3, "emergente": 3, "advanced": 4, "avance": 4, "avanzado": 4, "avancado": 4,
}
SCORE_TO_LEVEL = {1: "Incipient", 2: "Nascent", 3: "Emerging", 4: "Advanced"}


def _csv(rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for r in rows:
        w.writerow([csv_safe(v) for v in r])
    return "﻿" + buf.getvalue()


def safe_title(s: str, fallback: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_") or fallback


def assessment_csv(a: dict) -> tuple[str, str]:
    rows: list[list] = [["InfraGov Assessment", a["title"]], ["Country", a["country"]]]
    if a.get("department"):
        rows.append(["Department", a["department"]])
    if a.get("fiscalYears"):
        rows.append(["Fiscal years", ", ".join(a["fiscalYears"])])
    rows.append(["Exported", datetime.now(timezone.utc).date().isoformat()])
    rows.append([])
    rows.append(["Dimension", "Status", "MBI", "Question", "Key Respondents", "Data Source", "Result Summary",
                 "Result Detail", "Score", "Maturity Level"])
    for d in a["dimensions"]:
        for m in d["mbis"]:
            e = m.get("entry") or {}
            score = e.get("score")
            rows.append([f"D{d['id']}: {d['name']}", d["status"], m["code"], m["question"],
                         "; ".join(x for x in e.get("keyRespondents", []) if x), e.get("dataSource", ""),
                         e.get("resultSummary", ""), e.get("resultDetail", ""), score or "",
                         e.get("maturityBenchmark") or (F.score_label(score) if score else "")])
    return _csv(rows), f"{safe_title(a['title'], 'InfraGov_Assessment')}.csv"


def country_csv(country: str, comparison: str, summary: list[dict], compare_by_dim: dict | None, locale: str) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date().isoformat()
    rows: list[list] = [["InfraGov Country Profile", country, "Exported", today]]
    if comparison:
        rows.append(["Comparison", comparison])
    rows.append([])
    headers = ["Dimension", "MBI", "Indicator", "Result Summary", f"{country} Score", f"{country} Maturity Level"]
    if comparison:
        headers += [f"{comparison} Score", f"{comparison} Maturity Level"]
    rows.append(headers)
    for item in summary:
        meta, latest = item["meta"], item["latest"]
        ce = (compare_by_dim or {}).get(meta["id"])
        has = bool(comparison) and ce is not None and len(ce["mbis"]) > 0
        for m in latest["mbis"]:
            row = [f"D{meta['id']}: {meta['name']}", m["code"], m["question"], m["summary"], m["score"] or "",
                   F.score_label(m["score"], locale) if m["score"] else ""]
            if comparison:
                if not has:
                    row += ["N/A", "N/A"]
                else:
                    cs = ce["mbis"].get(m["code"])
                    row += [cs or "", F.score_label(cs, locale) if cs else ""]
            rows.append(row)
    return _csv(rows), f"{re.sub(r'[^a-zA-Z0-9]+', '_', country)}_InfraGov_Profile.csv"


# ---------------------------------------------------------------- Word export

def _shade(cell, hex_fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def assessment_docx(a: dict, prepared_by: dict | None = None) -> tuple[bytes, str]:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    bg = {1: "64CBD6", 2: "599EC7", 3: "4E71B8", 4: "4345AA"}
    fg = {1: "1F2937", 2: "1F2937", 3: "FFFFFF", 4: "FFFFFF"}
    fw = "PAG-FA" if a["kind"] == "pagfa" else "InfraGov 2.0"
    prefix = F.display_prefix(a["kind"])
    doc = Document()

    def para(text: str, size: int = 11, bold: bool = False, color: str = "111827", center: bool = False, italic: bool = False):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        r.font.size = Pt(size)
        r.font.color.rgb = RGBColor.from_string(color)
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    for _ in range(6):
        doc.add_paragraph()
    para(fw.upper(), 11, True, "4F46E5", True)
    para("ASSESSMENT REPORT", 10, False, "6B7280", True)
    para(a["title"], 22, True, "111827", True)
    para(" · ".join(x for x in (a["country"], a.get("department")) if x), 12, False, "374151", True)
    if a.get("fiscalYears"):
        para(f"Fiscal years: {', '.join(a['fiscalYears'])}", 10, False, "6B7280", True)
    para(f"Exported {datetime.now(timezone.utc).strftime('%d %B %Y')}", 10, False, "6B7280", True)
    if prepared_by and (prepared_by.get("name") or prepared_by.get("organisation")):
        para("Prepared by " + " · ".join(x for x in (prepared_by.get("name"), prepared_by.get("organisation")) if x), 10, False, "6B7280", True)

    doc.add_page_break()
    meta = doc.add_table(rows=0, cols=2)
    meta.style = "Table Grid"
    for k, v in (("Document type", ROUNDTRIP_DOC_MARKER), ("Assessment ID", a["id"]),
                 ("Snapshot at", datetime.now(timezone.utc).isoformat(timespec="seconds")), ("Framework", fw)):
        row = meta.add_row().cells
        row[0].text, row[1].text = k, v
    para("Edit any of the value cells (Key Respondents, Data Source, Result Summary, Result Detail, Maturity Level). "
         "Do not change the MBI code or Indicator text. When re-uploading, separate multiple Key Respondents with semicolons and "
         "give the Maturity Level as a number 1-4 or a level name.", 9, False, "4B5563")

    for d in a["dimensions"]:
        doc.add_page_break()
        doc.add_heading(f"{prefix}{d['id']}. {d['name']}", level=1)
        para(f"Status: {d['status']}", 9, False, "6B7280")
        t = doc.add_table(rows=1, cols=len(ROUNDTRIP_COLUMNS))
        t.style = "Table Grid"
        for i, h in enumerate(ROUNDTRIP_COLUMNS):
            c = t.rows[0].cells[i]
            c.text = ""
            run = c.paragraphs[0].add_run(h)
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor.from_string("3730A3")
            _shade(c, "EEF2FF")
        for m in d["mbis"]:
            e = m.get("entry") or {}
            score = e.get("score")
            cells = t.add_row().cells
            vals = [m["code"], m["question"], "; ".join(e.get("keyRespondents", [])), e.get("dataSource", ""),
                    e.get("resultSummary", ""), e.get("resultDetail", ""), f"{score} - {F.score_label(score)}" if score else ""]
            for i, v in enumerate(vals):
                cells[i].text = v
                for p in cells[i].paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(9)
            if score:
                _shade(cells[6], bg[score])
                for r in cells[6].paragraphs[0].runs:
                    r.bold = True
                    r.font.color.rgb = RGBColor.from_string(fg[score])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), f"{safe_title(a['title'], 'InfraGov_Assessment')}.docx"


# ---------------------------------------------------------------- Word import

def parse_maturity_cell(raw: str) -> tuple[int | None, bool]:
    s = raw.strip()
    if not s:
        return None, False
    m = re.match(r"^([1-4])\b", s)
    if m:
        return int(m.group(1)), False
    word = unicodedata.normalize("NFD", s.lower())
    word = "".join(ch for ch in word if not unicodedata.combining(ch) and ch.isalpha())
    if word in MATURITY_WORD_TO_SCORE:
        return MATURITY_WORD_TO_SCORE[word], False
    return None, True


def parse_roundtrip(data: bytes, a: dict) -> dict:
    """Return {'changes': [...], 'warnings': [...]} for the preview modal."""
    import zipfile

    from docx import Document

    if data[:4] != b"PK\x03\x04":
        raise ValidationError("Only .docx uploads are supported. Save your Word document as .docx and try again.")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if sum(i.file_size for i in zf.infolist()) > 100 * 1024 * 1024:
            raise ValidationError("The document is too large.")
    doc = Document(io.BytesIO(data))
    body = doc.element.body
    tables_text = " ".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    if ROUNDTRIP_DOC_MARKER not in tables_text and ROUNDTRIP_DOC_MARKER not in "\n".join(p.text for p in doc.paragraphs):
        raise ValidationError("This document doesn't look like an InfraGov round-trip export. Only .docx files downloaded from the Sharing Panel can be uploaded here.")
    warnings: list[str] = []
    changes: list[dict] = []
    doc_aid, snapshot = "", ""
    for t in doc.tables:
        if ROUNDTRIP_DOC_MARKER in " ".join(c.text for r in t.rows for c in r.cells):
            for r in t.rows:
                if len(r.cells) >= 2:
                    label = r.cells[0].text.strip().lower()
                    if label == "assessment id":
                        doc_aid = r.cells[1].text.strip()
                    elif label == "snapshot at":
                        snapshot = r.cells[1].text.strip()
            break
    if doc_aid and doc_aid != a["id"]:
        raise ValidationError("This document belongs to a different assessment. Open the assessment it was exported from and try again.")
    if snapshot:
        try:
            snap = datetime.fromisoformat(snapshot.replace("Z", "+00:00"))
            upd = datetime.fromisoformat(a["updatedAt"].replace("Z", "+00:00"))
            if upd.replace(tzinfo=timezone.utc) > snap.replace(tzinfo=snap.tzinfo or timezone.utc):
                warnings.append("The assessment has been edited on the server since this document was exported. Review the diff carefully — some fields may have newer values online than the document shows.")
        except ValueError:
            pass
    dims = {d["id"]: d for d in a["dimensions"]}
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    current = None
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            if p.style is not None and p.style.name.lower().startswith("heading"):
                m = re.match(r"^(?:D|P)\s*(\d+)\b", p.text.strip(), re.I)
                current = dims.get(int(m.group(1))) if m else None
        elif tag == "tbl" and current is not None:
            table = Table(child, doc)
            for row in table.rows[1:]:
                cells = [c.text.strip() for c in row.cells]
                if len(cells) < 7:
                    continue
                code, _, resp, src, summ, det, mat = cells[:7]
                mbi = next((m for m in current["mbis"] if m["code"] == code), None)
                if not mbi:
                    continue
                e = mbi.get("entry") or {}
                skip = "Dimension is Published — cannot edit" if current["status"] == "Published" else None
                for field, label, cur_v, new_v in (
                    ("keyRespondents", "Key Respondents", "; ".join(e.get("keyRespondents", [])), resp),
                    ("dataSource", "Data Source", e.get("dataSource", ""), src),
                    ("resultSummary", "Result Summary", e.get("resultSummary", ""), summ),
                    ("resultDetail", "Result Detail", e.get("resultDetail", ""), det),
                ):
                    if cur_v != new_v:
                        changes.append({"dimensionId": current["id"], "mbiId": mbi["id"], "mbiCode": code, "field": field,
                                        "fieldLabel": label, "currentValue": cur_v, "proposedValue": new_v, "skipReason": skip})
                score, bad = parse_maturity_cell(mat)
                cur_score = e.get("score")
                if bad or score != cur_score:
                    changes.append({"dimensionId": current["id"], "mbiId": mbi["id"], "mbiCode": code, "field": "score",
                                    "fieldLabel": "Maturity Level",
                                    "currentValue": f"{cur_score} - {F.score_label(cur_score)}" if cur_score else "",
                                    "proposedValue": mat, "skipReason": skip, "unresolvable": bad, "score": score})
    return {"changes": changes, "warnings": warnings}


def patch_from_changes(changes: list[dict]) -> dict:
    patch: dict = {}
    for c in changes:
        if c["field"] == "keyRespondents":
            patch["keyRespondents"] = [x.strip() for x in c["proposedValue"].split(";") if x.strip()]
        elif c["field"] == "score":
            patch["maturityBenchmark"] = SCORE_TO_LEVEL.get(c.get("score") or 0, "")
        else:
            patch[c["field"]] = c["proposedValue"]
    return patch


def report_fy(a: dict) -> str:
    return fy_range_display(a.get("fiscalYears"))

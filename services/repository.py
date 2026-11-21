"""
Repository — all reads and writes of assessment data.

Each public function takes the signed-in ``user`` and enforces the rules in
services/permissions.py *server-side* before touching data. Results are
filtered so a user only receives what they are entitled to see (e.g. draft
indicator answers only for dimensions they are assigned to, internal Result
Detail only for Owner/Admin/Contributor, team & activity only for members).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import constants as C
from services import permissions as P
from services.crypto import decrypt_field, encrypt_field, new_token, sha256_hex
from services.db import get_db, in_clause, jdump, jload, parse_ts, to_iso, utcnow
from services.validators import (
    ValidationError, clean_text, new_uuid, validate_choice, validate_email, validate_fiscal_year,
)
from utils import framework as F
from utils.countries import find_country

log = logging.getLogger("infragov.repo")
T = C.T


class Forbidden(PermissionError):
    """Raised when the caller is not allowed to perform an action."""


class NotFound(LookupError):
    pass


def _initials(name: str) -> str:
    return "".join(p[0] for p in (name or "").split() if p)[:2].upper()


def _db():
    return get_db()


# ============================================================================
# Loading
# ============================================================================

def _load_base(aids: list[str]) -> dict[str, dict]:
    """Assessment rows + dimension status + collaborators + team user ids."""
    if not aids:
        return {}
    db = _db()
    clause, params = in_clause("a", aids)
    arows = db.query(f"SELECT * FROM {T['assessments']} WHERE id IN {clause}", params)
    drows = db.query(f"SELECT id, assessment_id, dim_id, status, updated_at FROM {T['dimensions']} WHERE assessment_id IN {clause}", params)
    crows = db.query(f"SELECT * FROM {T['dimension_collaborators']} WHERE assessment_id IN {clause}", params)
    trows = db.query(f"SELECT * FROM {T['assessment_team']} WHERE assessment_id IN {clause}", params)
    uids = {c["user_id"] for c in crows} | {t["user_id"] for t in trows} | {a["owner_user_id"] for a in arows}
    users = _users_by_id(list(uids))
    out: dict[str, dict] = {}
    for a in arows:
        out[a["id"]] = {
            "id": a["id"],
            "kind": a.get("kind") or "infragov",
            "title": a["title"],
            "country": a["country"],
            "department": a.get("department") or "",
            "description": a.get("description") or "",
            "fiscalYears": jload(a.get("fiscal_years")),
            "ownerUserId": a["owner_user_id"],
            "createdAt": to_iso(a["created_at"]),
            "updatedAt": to_iso(a["updated_at"]),
            "dimUuid": {}, "dimStatus": {}, "collaborators": {}, "teamUserIds": set(), "teamRows": [],
            "_users": users,
        }
    by_uuid: dict[str, tuple[str, int]] = {}
    for d in drows:
        a = out.get(d["assessment_id"])
        if a is None:
            continue
        a["dimUuid"][int(d["dim_id"])] = d["id"]
        a["dimStatus"][int(d["dim_id"])] = d["status"]
        by_uuid[d["id"]] = (d["assessment_id"], int(d["dim_id"]))
    for c in crows:
        loc = by_uuid.get(c["dimension_id"])
        if not loc:
            continue
        a = out[loc[0]]
        u = users.get(c["user_id"], {})
        a["collaborators"].setdefault(loc[1], []).append({
            "userId": c["user_id"], "name": u.get("name", ""), "email": u.get("email", ""),
            "role": c["role"], "invitedAt": to_iso(c["invited_at"]), "invitedBy": c["invited_by"],
        })
    for t in trows:
        a = out.get(t["assessment_id"])
        if a is None:
            continue
        a["teamUserIds"].add(t["user_id"])
        a["teamRows"].append(t)
    return out


def _users_by_id(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    clause, params = in_clause("u", ids)
    rows = _db().query(f"SELECT id, name, email, organisation, role FROM {T['users']} WHERE id IN {clause}", params)
    return {r["id"]: r for r in rows}


def _visible_ids(user: dict) -> list[str]:
    db = _db()
    if P.is_admin(user):
        rows = db.query(f"SELECT id FROM {T['assessments']} ORDER BY created_at DESC")
    else:
        rows = db.query(
            f"""SELECT id FROM {T['assessments']}
                WHERE owner_user_id = :uid
                   OR id IN (SELECT assessment_id FROM {T['dimension_collaborators']} WHERE user_id = :uid)
                   OR id IN (SELECT assessment_id FROM {T['assessment_team']} WHERE user_id = :uid)
                   OR id IN (SELECT assessment_id FROM {T['dimensions']} WHERE status = 'Published')
                ORDER BY created_at DESC""",
            {"uid": user["id"]},
        )
    return [r["id"] for r in rows]


def list_assessments(user: dict) -> list[dict]:
    """Assessment cards for the list page (no indicator data)."""
    ids = _visible_ids(user)
    base = _load_base(ids)
    out = []
    for aid in ids:
        a = base.get(aid)
        if not a or not P.can_view_assessment(user, a):
            continue
        total = len(F.dimensions_for(a["kind"]))
        published = sum(1 for s in a["dimStatus"].values() if s == "Published")
        out.append({
            **{k: a[k] for k in ("id", "kind", "title", "country", "department", "fiscalYears", "createdAt", "updatedAt", "ownerUserId")},
            "published": published, "total": total,
            "role": P.role_for_assessment(user, a), "mine": P.is_mine(user, a),
        })
    return out


def get_assessment(
    user: dict, aid: str, locale: str = "en", *, entries: bool = True, comments: bool = False,
    activity: bool = False, team: bool = False, invitations: bool = False, unpublish: bool = True,
) -> dict:
    """Full assessment bundle, filtered to what `user` may see."""
    a = _load_base([aid]).get(aid)
    if not a:
        raise NotFound("Assessment not found")
    if not P.can_view_assessment(user, a):
        raise Forbidden("You do not have access to this assessment")
    db = _db()
    member = P.is_member(user, a)
    viewable = {d for d in a["dimUuid"] if P.can_view_dimension(user, a, d)}
    entry_rows: dict[tuple[int, str], dict] = {}
    if entries and viewable:
        clause, params = in_clause("d", [a["dimUuid"][d] for d in viewable])
        rows = db.query(f"SELECT * FROM {T['mbi_entries']} WHERE dimension_id IN {clause}", params)
        uuid_to_dim = {v: k for k, v in a["dimUuid"].items()}
        for r in rows:
            entry_rows[(uuid_to_dim[r["dimension_id"]], r["mbi_code"])] = r
    comment_rows: list[dict] = []
    commentable = {d for d in viewable if P.can_comment_dimension(user, a, d)}
    if comments and commentable:
        rows = db.query(f"SELECT * FROM {T['comments']} WHERE assessment_id = :aid ORDER BY created_at ASC", {"aid": aid})
        uuid_to_dim = {v: k for k, v in a["dimUuid"].items()}
        for r in rows:
            d = uuid_to_dim.get(r["dimension_id"])
            if d in commentable:
                r["_dim"] = d
                comment_rows.append(r)
    dims = []
    for meta in F.dimensions_for(a["kind"], locale):
        did = meta["id"]
        can_detail = P.can_see_result_detail(user, a, did)
        dcomments = [_comment(r) for r in comment_rows if r["_dim"] == did and not r.get("mbi_code")]
        mbis = []
        for i, q in enumerate(meta["indicators"]):
            code = F.mbi_code(did, i + 1)
            row = entry_rows.get((did, code))
            entry = None
            if row:
                entry = {
                    "keyRespondents": jload(row.get("key_respondents")),
                    "dataSource": row.get("data_source") or "",
                    "resultSummary": row.get("result_summary") or "",
                    "resultDetail": decrypt_field(row.get("result_detail")) if can_detail else "",
                    "maturityBenchmark": row.get("maturity_benchmark") or "",
                    "score": int(row["score"]) if row.get("score") is not None else None,
                    "files": jload(row.get("files")),
                    "lastEditedBy": row.get("last_edited_by") or "",
                    "lastEditedAt": to_iso(row.get("last_edited_at")),
                }
            mbis.append({
                "id": i + 1, "code": code, **q,
                "status": (row or {}).get("status") or "untouched",
                "entry": entry,
                "comments": [_comment(r) for r in comment_rows if r["_dim"] == did and r.get("mbi_code") == code],
            })
        dims.append({
            "id": did, "name": meta["name"], "shortName": meta["shortName"], "thematicArea": meta["thematicArea"],
            "status": a["dimStatus"].get(did, "Draft"), "mbis": mbis, "comments": dcomments,
            "collaborators": a["collaborators"].get(did, []),
            "canView": did in viewable,
        })
    a["dimensions"] = dims
    users = a["_users"]
    a["team"] = []
    if team and member:
        for t in a["teamRows"]:
            u = users.get(t["user_id"], {})
            a["team"].append({
                "id": t["user_id"], "name": u.get("name", ""), "email": u.get("email", ""),
                "role": t["role"], "organisation": t.get("organisation") or u.get("organisation") or "",
                "joinedAt": to_iso(t["joined_at"]), "lastActivity": to_iso(t["last_activity"]),
            })
    a["invitations"] = []
    if invitations and P.can_manage(user, a):
        uuid_to_dim = {v: k for k, v in a["dimUuid"].items()}
        for r in db.query(f"SELECT * FROM {T['dimension_invitations']} WHERE assessment_id = :aid", {"aid": aid}):
            a["invitations"].append({
                "id": r["id"], "assessmentId": aid, "dimensionId": uuid_to_dim.get(r["dimension_id"], 0),
                "email": r["email"], "role": r["role"], "organisation": r.get("organisation") or "",
                "status": r["status"], "createdAt": to_iso(r["created_at"]), "acceptedAt": to_iso(r.get("accepted_at")),
            })
    a["activityLog"] = _activity_for(aid) if (activity and member) else []
    a["unpublishRequests"] = _unpublish_for(a) if (unpublish and (P.can_manage(user, a))) else []
    a["viewerIsMember"] = member
    a.pop("teamRows", None)
    a.pop("_users", None)
    return a


def _comment(r: dict) -> dict:
    return {
        "id": r["id"], "author": r["author_name"], "authorUserId": r["author_user_id"],
        "authorInitials": _initials(r["author_name"]), "text": r["text"],
        "timestamp": to_iso(r["created_at"]), "updatedAt": to_iso(r.get("updated_at")) or None,
    }


def _activity_for(aid: str) -> list[dict]:
    rows = _db().query(
        f"SELECT * FROM {T['activity_log']} WHERE assessment_id = :aid ORDER BY created_at DESC LIMIT 1000", {"aid": aid}
    )
    return [{
        "id": r["id"], "timestamp": to_iso(r["created_at"]), "actorUserId": r["actor_user_id"],
        "actorName": r["actor_name"], "actorOrganisation": r.get("actor_organisation") or "",
        "type": r["type"], "targetUserId": r.get("target_user_id"), "targetName": r.get("target_name") or "",
        "dimensionId": r.get("dim_id"), "dimensionName": r.get("dimension_name") or "",
        "dimensionIds": jload(r.get("dimension_ids")), "mbiCode": r.get("mbi_code") or "",
        "fieldsChanged": jload(r.get("fields_changed")), "importSource": r.get("import_source") or "",
        "documentName": r.get("document_name") or "", "aiAssisted": bool(r.get("ai_assisted")),
        "fromRole": r.get("from_role"), "toRole": r.get("to_role"), "reason": r.get("reason") or "",
        "reviewNote": r.get("review_note") or "", "requestId": r.get("request_id"),
    } for r in rows]


def _unpublish_for(a: dict) -> list[dict]:
    rows = _db().query(f"SELECT * FROM {T['unpublish_requests']} WHERE assessment_id = :aid", {"aid": a["id"]})
    uuid_to_dim = {v: k for k, v in a["dimUuid"].items()}
    return [_unpub(r, uuid_to_dim.get(r["dimension_id"], 0)) for r in rows]


def _unpub(r: dict, dim_id: int) -> dict:
    return {
        "id": r["id"], "assessmentId": r["assessment_id"], "dimensionId": dim_id,
        "requestedByUserId": r["requested_by_user_id"], "requestedByName": r["requested_by_name"],
        "requestedByEmail": r["requested_by_email"], "reason": r["reason"],
        "requestedAt": to_iso(r["created_at"]), "status": r["status"],
        "reviewedByUserId": r.get("reviewed_by_user_id"), "reviewedByName": r.get("reviewed_by_name") or "",
        "reviewedAt": to_iso(r.get("reviewed_at")), "reviewNote": r.get("review_note") or "",
    }


def _require(a_or_none: Any, ok: bool, msg: str = "You do not have permission to do that.") -> None:
    if not ok:
        raise Forbidden(msg)


def _base_or_404(aid: str) -> dict:
    a = _load_base([aid]).get(aid)
    if not a:
        raise NotFound("Assessment not found")
    return a


# ============================================================================
# Activity helpers
# ============================================================================

def add_activity(aid: str, type_: str, actor: dict, **f: Any) -> None:
    validate_choice(type_, C.ACTIVITY_TYPES)
    _db().insert(T["activity_log"], {
        "id": new_uuid(), "assessment_id": aid, "type": type_,
        "actor_user_id": actor["id"], "actor_name": actor.get("name") or actor.get("email", ""),
        "actor_organisation": actor.get("organisation") or None,
        "target_user_id": f.get("target_user_id"), "target_name": f.get("target_name"),
        "dim_id": f.get("dim_id"), "dimension_name": f.get("dimension_name"),
        "dimension_ids": jdump(f["dimension_ids"]) if f.get("dimension_ids") is not None else None,
        "mbi_code": f.get("mbi_code"),
        "fields_changed": jdump(f["fields_changed"]) if f.get("fields_changed") is not None else None,
        "import_source": f.get("import_source"), "document_name": f.get("document_name"),
        "ai_assisted": bool(f.get("ai_assisted")), "from_role": f.get("from_role"), "to_role": f.get("to_role"),
        "reason": f.get("reason"), "review_note": f.get("review_note"), "request_id": f.get("request_id"),
        "created_at": utcnow(),
    })


def _dim_name(a: dict, dim_id: int) -> str:
    meta = F.dimension_meta(a["kind"], dim_id)
    return meta["name"] if meta else f"D{dim_id}"


def _touch(aid: str) -> None:
    _db().update(T["assessments"], {"updated_at": utcnow()}, {"id": aid})


# ============================================================================
# Assessments
# ============================================================================

def create_assessment(user: dict, *, kind: str, country: str, fiscal_year: str, department: str, description: str) -> str:
    _require(None, P.can_create_assessment(user), "Only Admins and Owners can create assessments.")
    kind = validate_choice(kind, C.FRAMEWORKS)
    c = find_country(country)
    if not c:
        raise ValidationError("Select a country.")
    fy = validate_fiscal_year(fiscal_year)
    department = clean_text(department, C.FIELD_LIMITS["department"], multiline=False)
    if not department:
        raise ValidationError("Department is required.")
    description = clean_text(description, C.FIELD_LIMITS["description"])
    from utils.countries import fy_display

    title = f"{c['name']} {fy_display(fy)}" + (" (PAG-FA)" if kind == "pagfa" else "")
    db = _db()
    for row in db.query(
        f"SELECT fiscal_years FROM {T['assessments']} WHERE country = :c AND kind = :k", {"c": c["name"], "k": kind}
    ):
        if fy in jload(row["fiscal_years"]):
            raise ValidationError(f"{c['name']} already has an assessment for {fy}. Each country can only have one assessment per year.")
    aid, now = new_uuid(), utcnow()
    db.insert(T["assessments"], {
        "id": aid, "kind": kind, "title": title, "country": c["name"], "department": department,
        "description": description or None, "fiscal_years": jdump([fy]), "owner_user_id": user["id"],
        "created_at": now, "updated_at": now,
    })
    for i in range(1, len(F.dimensions_for(kind)) + 1):
        db.insert(T["dimensions"], {"id": new_uuid(), "assessment_id": aid, "dim_id": i, "status": "Draft",
                                    "created_at": now, "updated_at": now})
    db.insert(T["assessment_team"], {"id": new_uuid(), "assessment_id": aid, "user_id": user["id"], "role": "Owner",
                                     "organisation": user.get("organisation") or None, "joined_at": now, "last_activity": now})
    add_activity(aid, "assessment.created", user)
    return aid


def update_assessment_details(user: dict, aid: str, department: str, description: str) -> None:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a))
    department = clean_text(department, C.FIELD_LIMITS["department"], multiline=False)
    if not department:
        raise ValidationError("Department is required.")
    _db().update(T["assessments"], {
        "department": department,
        "description": clean_text(description, C.FIELD_LIMITS["description"]) or None,
        "updated_at": utcnow(),
    }, {"id": aid})


def delete_assessment(user: dict, aid: str) -> None:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a), "Only the assessment Owner or an Admin can delete it.")
    db = _db()
    from services import storage

    for doc in db.query(f"SELECT storage_path FROM {T['assessment_documents']} WHERE assessment_id = :aid", {"aid": aid}):
        storage.delete(doc["storage_path"])
    # UC foreign keys are informational — cascade explicitly, children first.
    for key in ("indicator_suggestions", "assessment_documents", "unpublish_requests", "assessment_team",
                "dimension_invitations", "dimension_collaborators", "activity_log", "comments", "mbi_entries",
                "dimensions"):
        db.delete(T[key], {"assessment_id": aid})
    db.delete(T["assessments"], {"id": aid})


# ============================================================================
# Indicator answers
# ============================================================================

ENTRY_FIELDS = ("keyRespondents", "dataSource", "resultSummary", "resultDetail", "maturityBenchmark", "files")


def _clean_entry(entry: dict) -> dict:
    out: dict[str, Any] = {}
    if "keyRespondents" in entry:
        seen, items = set(), []
        for r in (entry.get("keyRespondents") or [])[:50]:
            v = clean_text(r, C.FIELD_LIMITS["keyRespondent"], multiline=False)
            if v and v.lower() not in seen:
                seen.add(v.lower())
                items.append(v)
        out["keyRespondents"] = items
    for k in ("dataSource", "resultSummary", "resultDetail"):
        if k in entry:
            out[k] = clean_text(entry.get(k), C.FIELD_LIMITS[k])
    if "maturityBenchmark" in entry:
        mb = entry.get("maturityBenchmark") or ""
        out["maturityBenchmark"] = validate_choice(mb, C.MATURITY_LEVELS) if mb else ""
    if "files" in entry:
        from services.validators import safe_filename
        out["files"] = [safe_filename(f, 160) for f in (entry.get("files") or [])[:50]]
    return out


def save_mbi_entry(user: dict, aid: str, dim_id: int, mbi_id: int, entry: dict, *,
                   ai_assisted: bool = False, skip_log: bool = False) -> bool:
    """Merge-save one indicator. Returns True when something was persisted."""
    a = _base_or_404(aid)
    _require(a, P.can_edit_dimension(user, a, dim_id), "You cannot edit this dimension.")
    meta = F.dimension_meta(a["kind"], dim_id)
    if not meta or not (1 <= mbi_id <= meta["mbiCount"]):
        raise NotFound("Indicator not found")
    dim_uuid = a["dimUuid"].get(dim_id)
    if not dim_uuid:
        raise NotFound("Dimension not found")
    code = F.mbi_code(dim_id, mbi_id)
    clean = _clean_entry(entry)
    db = _db()
    row = db.one(f"SELECT * FROM {T['mbi_entries']} WHERE dimension_id = :d AND mbi_code = :c", {"d": dim_uuid, "c": code})
    old = {
        "keyRespondents": jload((row or {}).get("key_respondents")),
        "dataSource": (row or {}).get("data_source") or "",
        "resultSummary": (row or {}).get("result_summary") or "",
        "resultDetail": decrypt_field((row or {}).get("result_detail")),
        "maturityBenchmark": (row or {}).get("maturity_benchmark") or "",
        "files": jload((row or {}).get("files")),
    }
    merged = {**old, **clean}
    changed = [f for f in ENTRY_FIELDS if (old.get(f) or None) != (merged.get(f) or None)]
    if (row and not changed) or (not row and not any(merged.get(f) for f in ENTRY_FIELDS)):
        return True  # nothing to persist (never create empty "in-progress" rows)
    complete = bool(merged["keyRespondents"]) and bool(merged["dataSource"]) and bool(merged["resultSummary"]) and bool(merged["maturityBenchmark"])
    now = utcnow()
    values = {
        "dimension_id": dim_uuid, "assessment_id": aid, "mbi_code": code,
        "key_respondents": jdump(merged["keyRespondents"]), "data_source": merged["dataSource"],
        "result_summary": merged["resultSummary"], "result_detail": encrypt_field(merged["resultDetail"]),
        "maturity_benchmark": merged["maturityBenchmark"] or None,
        "score": F.maturity_to_score(merged["maturityBenchmark"]) or None,
        "files": jdump(merged["files"]), "status": "complete" if complete else "in-progress",
        "last_edited_by": user["id"], "last_edited_at": now, "updated_at": now,
    }
    if row:
        db.update(T["mbi_entries"], values, {"id": row["id"]})
    else:
        db.insert(T["mbi_entries"], {"id": new_uuid(), "created_at": now, **values})
    _touch(aid)
    if not skip_log and changed:
        add_activity(aid, "mbi.updated", user, dim_id=dim_id, dimension_name=_dim_name(a, dim_id),
                     mbi_code=code, fields_changed=changed, ai_assisted=ai_assisted)
    return True


def log_dimension_import(user: dict, aid: str, dim_id: int, codes: list[str], source: str = "docx") -> None:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a))
    add_activity(aid, "dimension.imported", user, dim_id=dim_id, dimension_name=_dim_name(a, dim_id),
                 fields_changed=codes, import_source=validate_choice(source, ("docx", "pdf")))


def _dimension_complete(a: dict, dim_id: int) -> bool:
    meta = F.dimension_meta(a["kind"], dim_id)
    rows = _db().query(
        f"SELECT status FROM {T['mbi_entries']} WHERE dimension_id = :d", {"d": a["dimUuid"][dim_id]}
    )
    return bool(meta) and sum(1 for r in rows if r["status"] == "complete") >= meta["mbiCount"]


def publish_dimension(user: dict, aid: str, dim_id: int) -> None:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a), "Only the assessment Owner can publish.")
    if dim_id not in a["dimUuid"]:
        raise NotFound("Dimension not found")
    if a["dimStatus"][dim_id] == "Published":
        return
    if not _dimension_complete(a, dim_id):
        raise ValidationError("Complete all indicators before publishing.")
    _db().update(T["dimensions"], {"status": "Published", "updated_at": utcnow()}, {"id": a["dimUuid"][dim_id]})
    _touch(aid)
    add_activity(aid, "dimension.published", user, dim_id=dim_id, dimension_name=_dim_name(a, dim_id))


def admin_unpublish_dimension(user: dict, aid: str, dim_id: int) -> None:
    """Direct unpublish — platform Admins only (Owners must file a request)."""
    _require(None, P.is_admin(user), "Only a platform Admin can unpublish directly.")
    a = _base_or_404(aid)
    if a["dimStatus"].get(dim_id) != "Published":
        return
    _db().update(T["dimensions"], {"status": "Draft", "updated_at": utcnow()}, {"id": a["dimUuid"][dim_id]})
    add_activity(aid, "dimension.unpublished", user, dim_id=dim_id, dimension_name=_dim_name(a, dim_id))


def request_unpublish(user: dict, aid: str, dim_id: int, reason: str) -> str:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a))
    reason = clean_text(reason, C.FIELD_LIMITS["unpublishReason"])
    if len(reason) < 10:
        raise ValidationError("Please give a reason of at least 10 characters.")
    if a["dimStatus"].get(dim_id) != "Published":
        raise ValidationError("Only published dimensions can be unpublished.")
    db = _db()
    if db.one(f"SELECT id FROM {T['unpublish_requests']} WHERE dimension_id = :d AND status = 'Pending'", {"d": a["dimUuid"][dim_id]}):
        raise ValidationError("There is already a pending request for this dimension.")
    rid = new_uuid()
    db.insert(T["unpublish_requests"], {
        "id": rid, "assessment_id": aid, "dimension_id": a["dimUuid"][dim_id],
        "requested_by_user_id": user["id"], "requested_by_name": user["name"], "requested_by_email": user["email"],
        "reason": reason, "status": "Pending", "reviewed_by_user_id": None, "reviewed_by_name": None,
        "reviewed_at": None, "review_note": None, "created_at": utcnow(),
    })
    add_activity(aid, "unpublish.requested", user, dim_id=dim_id, dimension_name=_dim_name(a, dim_id), reason=reason, request_id=rid)
    return rid


def pending_unpublish_requests(user: dict, locale: str = "en") -> list[dict]:
    if not P.is_admin(user):
        return []
    db = _db()
    rows = db.query(f"SELECT * FROM {T['unpublish_requests']} WHERE status = 'Pending' ORDER BY created_at DESC")
    if not rows:
        return []
    base = _load_base(list({r["assessment_id"] for r in rows}))
    out = []
    for r in rows:
        a = base.get(r["assessment_id"])
        if not a:
            continue
        dim_id = {v: k for k, v in a["dimUuid"].items()}.get(r["dimension_id"], 0)
        if a["dimStatus"].get(dim_id) != "Published":
            continue
        meta = F.dimension_meta(a["kind"], dim_id, locale) or {"name": ""}
        out.append({"request": _unpub(r, dim_id), "assessment": {"id": a["id"], "country": a["country"], "title": a["title"]},
                    "dimension": {"id": dim_id, "name": meta["name"]}})
    return out


def decide_unpublish(user: dict, request_id: str, approve: bool, note: str = "") -> None:
    _require(None, P.is_admin(user), "Only platform Admins can review unpublish requests.")
    db = _db()
    r = db.one(f"SELECT * FROM {T['unpublish_requests']} WHERE id = :id", {"id": request_id})
    if not r or r["status"] != "Pending":
        raise NotFound("Request not found or already decided")
    note = clean_text(note, C.FIELD_LIMITS["reviewNote"])
    if not approve and not note:
        raise ValidationError("A note is required when denying a request.")
    a = _base_or_404(r["assessment_id"])
    dim_id = {v: k for k, v in a["dimUuid"].items()}.get(r["dimension_id"], 0)
    now = utcnow()
    db.update(T["unpublish_requests"], {
        "status": "Approved" if approve else "Denied", "reviewed_by_user_id": user["id"],
        "reviewed_by_name": user["name"], "reviewed_at": now, "review_note": note or None,
    }, {"id": request_id})
    name = _dim_name(a, dim_id)
    if approve:
        was_published = a["dimStatus"].get(dim_id) == "Published"
        if was_published:
            db.update(T["dimensions"], {"status": "Draft", "updated_at": now}, {"id": r["dimension_id"]})
        add_activity(a["id"], "unpublish.approved", user, dim_id=dim_id, dimension_name=name, request_id=request_id, review_note=note or None)
        if was_published:
            add_activity(a["id"], "dimension.unpublished", user, dim_id=dim_id, dimension_name=name)
    else:
        add_activity(a["id"], "unpublish.denied", user, dim_id=dim_id, dimension_name=name, request_id=request_id, review_note=note)


# ============================================================================
# Comments
# ============================================================================

def add_comment(user: dict, aid: str, dim_id: int, mbi_id: int | None, text: str) -> None:
    a = _base_or_404(aid)
    _require(a, P.can_comment_dimension(user, a, dim_id), "You cannot comment on this dimension.")
    text = clean_text(text, C.FIELD_LIMITS["comment"])
    if not text:
        raise ValidationError("Comment is empty.")
    code = None
    if mbi_id:
        meta = F.dimension_meta(a["kind"], dim_id)
        if not meta or not (1 <= mbi_id <= meta["mbiCount"]):
            raise NotFound("Indicator not found")
        code = F.mbi_code(dim_id, mbi_id)
    _db().insert(T["comments"], {
        "id": new_uuid(), "assessment_id": aid, "dimension_id": a["dimUuid"][dim_id], "mbi_code": code,
        "author_user_id": user["id"], "author_name": user["name"] or user["email"], "text": text,
        "created_at": utcnow(), "updated_at": None,
    })


def _own_comment(user: dict, comment_id: str) -> dict:
    r = _db().one(f"SELECT * FROM {T['comments']} WHERE id = :id", {"id": comment_id})
    if not r:
        raise NotFound("Comment not found")
    _require(None, r["author_user_id"] == user["id"], "You can only change your own comments.")
    return r


def update_comment(user: dict, comment_id: str, text: str) -> None:
    _own_comment(user, comment_id)
    text = clean_text(text, C.FIELD_LIMITS["comment"])
    if not text:
        raise ValidationError("Comment is empty.")
    _db().update(T["comments"], {"text": text, "updated_at": utcnow()}, {"id": comment_id})


def delete_comment(user: dict, comment_id: str) -> None:
    _own_comment(user, comment_id)
    _db().delete(T["comments"], {"id": comment_id})


# ============================================================================
# Collaboration
# ============================================================================

def _ensure_team(aid: str, user_id: str, role: str, organisation: str | None) -> None:
    now = utcnow()
    _db().upsert(T["assessment_team"], ["assessment_id", "user_id"], {
        "id": new_uuid(), "assessment_id": aid, "user_id": user_id, "role": role,
        "organisation": organisation, "joined_at": now, "last_activity": now,
    }, insert_only=["id", "role", "organisation", "joined_at"])


def assign_user_to_dimensions(user: dict, aid: str, dim_ids: list[int], email: str, name: str,
                              organisation: str, role: str) -> dict:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a), "Only the assessment Owner (or an Admin) can assign team members.")
    email = validate_email(email)
    role = validate_choice(role, C.COLLAB_ROLES)
    organisation = clean_text(organisation, C.FIELD_LIMITS["organisation"], multiline=False)
    dim_ids = sorted({int(d) for d in dim_ids if int(d) in a["dimUuid"]})
    if not dim_ids:
        raise ValidationError("Select at least one dimension to assign access to.")
    db = _db()
    target = db.one(f"SELECT id, name, organisation FROM {T['users']} WHERE email = :e AND is_active = :t", {"e": email, "t": True})
    newly: list[int] = []
    links: list[tuple[int, str]] = []
    now = utcnow()
    if target:
        for d in dim_ids:
            if P.collab_role(a, d, target["id"]):
                continue
            db.upsert(T["dimension_collaborators"], ["dimension_id", "user_id"], {
                "id": new_uuid(), "dimension_id": a["dimUuid"][d], "assessment_id": aid, "user_id": target["id"],
                "role": role, "invited_by": user["id"], "invited_at": now,
            }, insert_only=["id"])
            newly.append(d)
        if newly:
            _ensure_team(aid, target["id"], role, organisation or target.get("organisation"))
            add_activity(aid, "collaborator.added", user, target_user_id=target["id"],
                         target_name=target.get("name") or name or email, dimension_ids=newly, to_role=role)
    else:
        for d in dim_ids:
            links.append((d, _create_invitation(user, a, d, email, role, organisation)))
            newly.append(d)
    return {"assigned": newly, "invited": bool(links), "links": links}


def _create_invitation(user: dict, a: dict, dim_id: int, email: str, role: str, organisation: str) -> str:
    raw = new_token(24)
    now = utcnow()
    _db().insert(T["dimension_invitations"], {
        "id": new_uuid(), "token_hash": sha256_hex(raw), "assessment_id": a["id"],
        "dimension_id": a["dimUuid"][dim_id], "email": email, "role": role,
        "organisation": organisation or None, "invited_by": user["id"], "status": "Pending",
        "accepted_user_id": None, "accepted_at": None,
        "expires_at": now + timedelta(days=C.DIMENSION_INVITE_TTL_DAYS), "created_at": now,
    })
    return raw


def invite_to_dimension(user: dict, aid: str, dim_id: int, email: str, role: str, organisation: str) -> str:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a), "Only the assessment Owner can invite contributors to this dimension.")
    if dim_id not in a["dimUuid"]:
        raise NotFound("Dimension not found")
    return _create_invitation(user, a, dim_id, validate_email(email), validate_choice(role, C.COLLAB_ROLES),
                              clean_text(organisation, C.FIELD_LIMITS["organisation"], multiline=False))


def set_collaborator_role(user: dict, aid: str, dim_id: int, target_id: str, role: str) -> None:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a))
    role = validate_choice(role, C.COLLAB_ROLES)
    current = P.collab_role(a, dim_id, target_id)
    if not current or current == role:
        return
    _db().update(T["dimension_collaborators"], {"role": role}, {"dimension_id": a["dimUuid"][dim_id], "user_id": target_id})
    name = next((c["name"] for c in a["collaborators"].get(dim_id, []) if c["userId"] == target_id), "")
    add_activity(aid, "collaborator.roleChanged", user, target_user_id=target_id, target_name=name, dim_id=dim_id,
                 dimension_name=_dim_name(a, dim_id), from_role=current, to_role=role)


def remove_collaborator(user: dict, aid: str, dim_id: int, target_id: str) -> None:
    a = _base_or_404(aid)
    _require(a, P.can_manage(user, a))
    current = P.collab_role(a, dim_id, target_id)
    if not current:
        return
    _db().delete(T["dimension_collaborators"], {"dimension_id": a["dimUuid"][dim_id], "user_id": target_id})
    name = next((c["name"] for c in a["collaborators"].get(dim_id, []) if c["userId"] == target_id), "")
    add_activity(aid, "collaborator.removed", user, target_user_id=target_id, target_name=name, dim_id=dim_id,
                 dimension_name=_dim_name(a, dim_id), from_role=current, to_role=None)


def peek_invitation(raw_token: str) -> dict | None:
    r = _db().one(f"SELECT * FROM {T['dimension_invitations']} WHERE token_hash = :h", {"h": sha256_hex(raw_token)})
    if not r:
        return None
    a = _load_base([r["assessment_id"]]).get(r["assessment_id"])
    if not a:
        return None
    dim_id = {v: k for k, v in a["dimUuid"].items()}.get(r["dimension_id"], 0)
    expired = (parse_ts(r["expires_at"]) or utcnow()) <= utcnow()
    return {"row": r, "assessmentId": a["id"], "dimensionId": dim_id, "role": r["role"], "email": r["email"],
            "status": "Expired" if (expired and r["status"] == "Pending") else r["status"]}


def accept_invitation(user: dict, raw_token: str) -> dict:
    inv = peek_invitation(raw_token)
    if not inv:
        raise NotFound("Invite not found")
    if inv["status"] == "Accepted":
        if inv["row"].get("accepted_user_id") == user["id"]:
            return inv
        raise ValidationError("This invitation has already been accepted.")
    if inv["status"] != "Pending":
        raise ValidationError("This invitation is invalid, revoked or has expired.")
    # Security: the invite is bound to the invited e-mail address.
    if inv["email"].lower() != user["email"].lower():
        raise Forbidden("This invitation was sent to a different e-mail address.")
    r = inv["row"]
    now = utcnow()
    db = _db()
    db.upsert(T["dimension_collaborators"], ["dimension_id", "user_id"], {
        "id": new_uuid(), "dimension_id": r["dimension_id"], "assessment_id": r["assessment_id"],
        "user_id": user["id"], "role": r["role"], "invited_by": r["invited_by"], "invited_at": now,
    }, insert_only=["id"])
    _ensure_team(r["assessment_id"], user["id"], r["role"], r.get("organisation") or user.get("organisation"))
    db.update(T["dimension_invitations"], {"status": "Accepted", "accepted_user_id": user["id"], "accepted_at": now}, {"id": r["id"]})
    inviter = _users_by_id([r["invited_by"]]).get(r["invited_by"], {"id": r["invited_by"], "name": "", "email": ""})
    add_activity(r["assessment_id"], "collaborator.added", {**inviter, "organisation": inviter.get("organisation")},
                 target_user_id=user["id"], target_name=user["name"] or user["email"],
                 dimension_ids=[inv["dimensionId"]], to_role=r["role"])
    return inv


def organisations_for_country(user: dict, country: str) -> list[str]:
    """Previously-used organisations for a country (managers only)."""
    db = _db()
    rows = db.query(
        f"""SELECT t.organisation AS o FROM {T['assessment_team']} t
            JOIN {T['assessments']} a ON a.id = t.assessment_id WHERE a.country = :c
            UNION SELECT i.organisation AS o FROM {T['dimension_invitations']} i
            JOIN {T['assessments']} a ON a.id = i.assessment_id WHERE a.country = :c""",
        {"c": country},
    )
    vals = {" ".join(str(r["o"]).split()) for r in rows if r.get("o")}
    return sorted(vals, key=str.lower)


def respondents_for_country(user: dict, country: str) -> list[str]:
    """Key respondents previously recorded for this country (readable dims only)."""
    from services.respondents import is_document_review

    db = _db()
    rows = db.query(
        f"""SELECT e.key_respondents AS kr, e.assessment_id AS aid, e.dimension_id AS did, d.status AS st
            FROM {T['mbi_entries']} e JOIN {T['assessments']} a ON a.id = e.assessment_id
            JOIN {T['dimensions']} d ON d.id = e.dimension_id WHERE a.country = :c""",
        {"c": country},
    )
    base = _load_base(list({r["aid"] for r in rows}))
    out: set[str] = set()
    for r in rows:
        a = base.get(r["aid"])
        if not a:
            continue
        dim_id = {v: k for k, v in a["dimUuid"].items()}.get(r["did"], 0)
        if not P.can_view_dimension(user, a, dim_id):
            continue
        for v in jload(r["kr"]):
            v = " ".join(str(v).split())
            if v and not is_document_review(v):
                out.add(v)
    return sorted(out, key=str.lower)


# ============================================================================
# Global dashboard (published data only — the public-facing view)
# ============================================================================

def published_overview(user: dict, locale: str = "en") -> list[dict]:
    """Every assessment with ≥1 published dimension, with ONLY published data
    and only public fields (code, question, summary, score, level)."""
    if not user:
        raise Forbidden("Sign in required")
    db = _db()
    drows = db.query(f"SELECT id, assessment_id, dim_id FROM {T['dimensions']} WHERE status = 'Published'")
    if not drows:
        return []
    aids = list({d["assessment_id"] for d in drows})
    clause, params = in_clause("a", aids)
    arows = {a["id"]: a for a in db.query(f"SELECT id, kind, country, fiscal_years, updated_at FROM {T['assessments']} WHERE id IN {clause}", params)}
    dclause, dparams = in_clause("d", [d["id"] for d in drows])
    erows = db.query(
        f"SELECT dimension_id, mbi_code, result_summary, score, maturity_benchmark FROM {T['mbi_entries']} WHERE dimension_id IN {dclause}",
        dparams,
    )
    by_dim: dict[str, dict[str, dict]] = {}
    for e in erows:
        by_dim.setdefault(e["dimension_id"], {})[e["mbi_code"]] = e
    out: dict[str, dict] = {}
    for d in drows:
        a = arows.get(d["assessment_id"])
        if not a:
            continue
        item = out.setdefault(a["id"], {
            "id": a["id"], "kind": a["kind"], "country": a["country"], "fiscalYears": jload(a["fiscal_years"]),
            "updatedAt": to_iso(a["updated_at"]), "dims": {},
        })
        meta = F.dimension_meta(a["kind"], int(d["dim_id"]), locale)
        if not meta:
            continue
        entries = by_dim.get(d["id"], {})
        mbis = []
        for i, q in enumerate(meta["indicators"]):
            code = F.mbi_code(meta["id"], i + 1)
            e = entries.get(code, {})
            mbis.append({"id": i + 1, "code": code, "question": q["question"],
                         "score": int(e["score"]) if e.get("score") is not None else None,
                         "level": e.get("maturity_benchmark") or "", "summary": e.get("result_summary") or ""})
        item["dims"][meta["id"]] = mbis
    return list(out.values())


def countries_by_framework(user: dict) -> dict[str, list[str]]:
    if not user:
        return {"infragov": [], "pagfa": []}
    rows = _db().query(
        f"""SELECT DISTINCT a.kind AS kind, a.country AS country FROM {T['assessments']} a
            WHERE a.id IN (SELECT assessment_id FROM {T['dimensions']} WHERE status = 'Published')"""
    )
    res = {"infragov": set(), "pagfa": set()}
    for r in rows:
        res["pagfa" if r["kind"] == "pagfa" else "infragov"].add(r["country"])
    return {k: sorted(v, key=str.lower) for k, v in res.items()}


# ============================================================================
# Suggestions (AI drafts)
# ============================================================================

def list_saved_suggestions(user: dict, aid: str, dim_id: int) -> list[dict]:
    a = _base_or_404(aid)
    _require(a, P.can_edit_dimension(user, a, dim_id))
    rows = _db().query(
        f"SELECT * FROM {T['indicator_suggestions']} WHERE assessment_id = :a AND dim_id = :d", {"a": aid, "d": dim_id}
    )
    return [{
        "mbiId": int(r["mbi_id"]), "status": r["status"], "suggestion": jload(r.get("suggestion"), {}),
        "reason": r.get("reason") or "", "documentIds": jload(r.get("document_ids")),
        "draftedAt": to_iso(r["drafted_at"]), "draftedByName": r.get("drafted_by_name") or "",
    } for r in rows]


def save_suggestion(user: dict, a: dict, dim_id: int, mbi_id: int, response: dict, locale: str, model: str, doc_ids: list[str]) -> None:
    _db().upsert(T["indicator_suggestions"], ["dimension_id", "mbi_id"], {
        "id": new_uuid(), "assessment_id": a["id"], "dimension_id": a["dimUuid"][dim_id], "dim_id": dim_id,
        "mbi_id": mbi_id, "status": response["status"],
        "suggestion": jdump(response.get("suggestion")) if response["status"] == "suggested" else None,
        "reason": response.get("reason") if response["status"] == "no_evidence" else None,
        "locale": locale, "model": model, "document_ids": jdump(doc_ids), "drafted_by": user["id"],
        "drafted_by_name": user.get("name"), "drafted_at": utcnow(),
    }, insert_only=["id"])

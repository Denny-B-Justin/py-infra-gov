"""
Authorisation rules — the server-side equivalent of the original store's
can*/getUserRole* helpers *and* the Supabase RLS policies.

Every repository function calls these before reading or writing, so a user
can only ever reach their own data, however the request was crafted.
"""
from __future__ import annotations

from typing import Any

import constants as C

User = dict[str, Any]


def is_admin(user: User | None) -> bool:
    return bool(user) and user.get("role") == C.ROLE_ADMIN


def can_create_assessment(user: User | None) -> bool:
    return bool(user) and user.get("role") in (C.ROLE_ADMIN, C.ROLE_OWNER)


def collab_role(a: dict, dim_id: int, user_id: str) -> str | None:
    for c in a.get("collaborators", {}).get(dim_id, []):
        if c["userId"] == user_id:
            return c["role"]
    return None


def role_for_assessment(user: User | None, a: dict) -> str:
    if not user:
        return C.ROLE_VIEWER
    if is_admin(user):
        return C.ROLE_ADMIN
    if a.get("ownerUserId") == user["id"]:
        return C.ROLE_OWNER
    roles = {c["role"] for cs in a.get("collaborators", {}).values() for c in cs if c["userId"] == user["id"]}
    if C.ROLE_CONTRIBUTOR in roles:
        return C.ROLE_CONTRIBUTOR
    if C.ROLE_REVIEWER in roles:
        return C.ROLE_REVIEWER
    return C.ROLE_VIEWER


def role_for_dimension(user: User | None, a: dict, dim_id: int) -> str:
    if not user:
        return C.ROLE_VIEWER
    if is_admin(user):
        return C.ROLE_ADMIN
    if a.get("ownerUserId") == user["id"]:
        return C.ROLE_OWNER
    return collab_role(a, dim_id, user["id"]) or C.ROLE_VIEWER


def dim_status(a: dict, dim_id: int) -> str:
    d = a.get("dimStatus", {}).get(dim_id)
    return d or "Draft"


def can_manage(user: User | None, a: dict) -> bool:
    return role_for_assessment(user, a) in (C.ROLE_ADMIN, C.ROLE_OWNER)


def is_member(user: User | None, a: dict) -> bool:
    """Owner, Admin, any per-dimension collaborator, or listed team member."""
    if not user:
        return False
    if is_admin(user) or a.get("ownerUserId") == user["id"]:
        return True
    if any(c["userId"] == user["id"] for cs in a.get("collaborators", {}).values() for c in cs):
        return True
    return user["id"] in a.get("teamUserIds", set())


def can_view_assessment(user: User | None, a: dict) -> bool:
    if not user:
        return False
    return is_member(user, a) or any(s == "Published" for s in a.get("dimStatus", {}).values())


def can_view_dimension(user: User | None, a: dict, dim_id: int) -> bool:
    if not user:
        return False
    if dim_status(a, dim_id) == "Published":
        return True
    if is_admin(user) or a.get("ownerUserId") == user["id"]:
        return True
    return collab_role(a, dim_id, user["id"]) is not None


def can_edit_dimension(user: User | None, a: dict, dim_id: int) -> bool:
    if dim_status(a, dim_id) == "Published":
        return False
    return role_for_dimension(user, a, dim_id) in (C.ROLE_ADMIN, C.ROLE_OWNER, C.ROLE_CONTRIBUTOR)


def can_comment_dimension(user: User | None, a: dict, dim_id: int) -> bool:
    return can_view_dimension(user, a, dim_id) and role_for_dimension(user, a, dim_id) != C.ROLE_VIEWER


def can_see_result_detail(user: User | None, a: dict, dim_id: int) -> bool:
    return role_for_dimension(user, a, dim_id) in (C.ROLE_ADMIN, C.ROLE_OWNER, C.ROLE_CONTRIBUTOR)


def can_read_documents(user: User | None, a: dict) -> bool:
    if can_manage(user, a):
        return True
    return any(
        c["userId"] == (user or {}).get("id") and c["role"] in (C.ROLE_CONTRIBUTOR, C.ROLE_REVIEWER)
        for cs in a.get("collaborators", {}).values() for c in cs
    )


def is_mine(user: User | None, a: dict) -> bool:
    if not user:
        return False
    if is_admin(user) or a.get("ownerUserId") == user["id"]:
        return True
    return any(c["userId"] == user["id"] for cs in a.get("collaborators", {}).values() for c in cs)


def role_label(role: str | None) -> str:
    if not role:
        return "View Only"
    return "View Only" if role == C.ROLE_VIEWER else role

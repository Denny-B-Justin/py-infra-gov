"""Activity feed, comments panel and sharing panel (ports of the React components)."""
from __future__ import annotations

from datetime import datetime, timezone

import constants as C
from dash import dcc, html

from pages import pages_constants as PC
from services import permissions as P
from utils.components import icon, initials


def format_relative(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "")).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return ""
    secs = max(1, int((datetime.now(timezone.utc) - then).total_seconds()))
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins} minute{'' if mins == 1 else 's'} ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hour{'' if hours == 1 else 's'} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'' if days == 1 else 's'} ago"
    return then.strftime("%d/%m/%Y")


def format_comment_time(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", ""))
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b')} · {d.strftime('%H:%M')}"


B = "font-medium text-gray-800"


def activity_row(e: dict, hide_dim: bool = False):
    def dim_label(did, name):
        if hide_dim:
            return None
        if not did:
            return "a dimension"
        return html.Span([f"D{did}", html.Span(f" — {name}", className="text-gray-500") if name else None], className=B)

    typ = e["type"]
    ic, body = "user", []
    if typ == "assessment.created":
        ic, body = "file-plus", ["created this assessment"]
    elif typ == "collaborator.added":
        ids = e.get("dimensionIds") or []
        ic = "user-plus"
        body = ["added ", html.Span(e.get("targetName"), className=B), " as ", html.Span(e.get("toRole"), className=B)]
        if not hide_dim:
            body += [" on ", f"D{ids[0]}" if len(ids) == 1 else f"{len(ids)} dimensions"]
    elif typ == "collaborator.roleChanged":
        ic = "shield-check"
        body = ["changed ", html.Span(e.get("targetName"), className=B), "'s role"]
        if not hide_dim and e.get("dimensionId"):
            body.append(f" on D{e['dimensionId']}")
        body += [" from ", html.Span(e.get("fromRole"), className=B), " to ", html.Span(e.get("toRole"), className=B)]
    elif typ == "collaborator.removed":
        ic = "user-minus"
        body = ["removed ", html.Span(e.get("targetName"), className=B)]
        if not hide_dim and e.get("dimensionId"):
            body.append(f" from D{e['dimensionId']}")
        body += [" (now ", html.Span("Viewer", className=B), ")"]
    elif typ == "dimension.published":
        ic, body = "check-circle", ["published ", dim_label(e.get("dimensionId"), e.get("dimensionName"))]
    elif typ == "dimension.unpublished":
        ic, body = "x-circle", ["unpublished ", dim_label(e.get("dimensionId"), e.get("dimensionName"))]
    elif typ == "mbi.updated":
        ic = "pencil"
        fields = e.get("fieldsChanged") or []
        body = ["edited ", html.Span(e.get("mbiCode") or "an indicator", className=B)]
        if fields:
            body += [" · ", html.Span(", ".join(PC.FIELD_LABELS.get(f, f) for f in fields), className="text-gray-600")]
        if e.get("aiAssisted"):
            body.append(html.Span("AI-assisted", className="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100"))
    elif typ == "dimension.imported":
        ic = "upload"
        fields = e.get("fieldsChanged") or []
        body = ["imported changes to ", dim_label(e.get("dimensionId"), e.get("dimensionName")), " from a ",
                html.Span(("PDF" if e.get("importSource") == "pdf" else "Word") + " document", className=B)]
        if fields:
            body.append(html.Span([html.Span(f"{len(fields)} indicator{'' if len(fields) == 1 else 's'} updated: ", className="font-medium"),
                                   ", ".join(fields)], className="block mt-0.5 text-gray-500"))
    elif typ == "document.uploaded":
        ic, body = "file-up", ["uploaded the document ", html.Span(e.get("documentName") or "a document", className=B)]
    elif typ == "document.deleted":
        ic, body = "file-x", ["removed the document ", html.Span(e.get("documentName") or "a document", className=B)]
    elif typ in ("unpublish.requested", "unpublish.approved", "unpublish.denied"):
        ic = {"unpublish.requested": "clock", "unpublish.approved": "check-circle", "unpublish.denied": "alert-triangle"}[typ]
        lead = {"unpublish.requested": "requested to unpublish ", "unpublish.approved": "approved the unpublish request for ",
                "unpublish.denied": "denied the unpublish request for "}[typ]
        body = [lead, dim_label(e.get("dimensionId"), e.get("dimensionName"))]
        note = e.get("reason") if typ == "unpublish.requested" else e.get("reviewNote")
        if note:
            label = "Note: " if typ == "unpublish.approved" else "Reason: "
            body.append(html.Span([html.Span(label, className="font-semibold"), note],
                                  className="block mt-1 px-2.5 py-1.5 bg-gray-50 border border-gray-100 rounded text-gray-600"))
    return html.Div([
        html.Div(icon(ic, 12, "text-gray-500"), className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center shrink-0 mt-0.5"),
        html.Div([
            html.P([html.Span(e.get("actorName"), className="font-semibold text-gray-800"),
                    html.Span(f" · {e['actorOrganisation']}", className="text-gray-500") if e.get("actorOrganisation") else None],
                   className="text-sm leading-snug"),
            html.P(body, className="text-xs text-gray-600 mt-0.5 leading-relaxed"),
            html.P(format_relative(e.get("timestamp", "")), className="text-[11px] text-gray-400 mt-0.5"),
        ], className="flex-1 min-w-0"),
    ], className="flex items-start gap-3 px-5 py-3")


def activity_feed(entries: list[dict], visible: int, more_id: str, hide_dim: bool = False, empty=None):
    if not entries:
        return empty
    shown = entries[:visible]
    remaining = max(0, len(entries) - visible)
    return html.Div([
        html.Div([activity_row(e, hide_dim) for e in shown], className="divide-y divide-gray-100"),
        html.Div(html.Button([icon("chevron-down", 12), "Show older entries", html.Span(f"({remaining} more)", className="text-gray-400 font-normal")],
                             id=more_id, n_clicks=0, className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800"),
                 className="px-5 py-3 border-t border-gray-100 text-center") if remaining else None,
    ])


def comments_body(dim: dict, mbi: dict | None, scope: str, user: dict, editing: str | None = None):
    comments = (mbi or {}).get("comments", []) if scope == "mbi" else dim.get("comments", [])
    tabs = html.Div([
        html.Button(f"Dimension {('(' + str(len(dim['comments'])) + ')') if dim['comments'] else ''}", id={"type": "cm-scope", "index": "dimension"}, n_clicks=0,
                    className="px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px "
                    + ("border-indigo-600 text-indigo-700" if scope == "dimension" else "border-transparent text-gray-500 hover:text-gray-700")),
        html.Button(f"This indicator {('(' + str(len(mbi['comments'])) + ')') if mbi and mbi['comments'] else ''}", id={"type": "cm-scope", "index": "mbi"}, n_clicks=0,
                    className="px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px "
                    + ("border-indigo-600 text-indigo-700" if scope == "mbi" else "border-transparent text-gray-500 hover:text-gray-700")) if mbi else None,
    ], className="flex gap-1 px-4 border-b border-gray-200")
    if not comments:
        items = [html.Div([
            html.Div(icon("send", 18, "text-gray-300"), className="w-10 h-10 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3"),
            html.P("No comments yet. " + ("Discuss this specific indicator." if scope == "mbi" else "Start a thread on this dimension."),
                   className="text-xs text-gray-400"),
        ], className="text-center py-12")]
    else:
        items = []
        for c in comments:
            mine = c["authorUserId"] == user["id"]
            is_edit = editing == c["id"]
            items.append(html.Div([
                html.Div(c["authorInitials"], className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-[10px] font-bold shrink-0"),
                html.Div([
                    html.Div([
                        html.Span(c["author"], className="text-xs font-semibold text-gray-800"),
                        html.Span(format_comment_time(c["timestamp"]), className="text-[10px] text-gray-400"),
                        html.Span("(edited)", className="text-[10px] text-gray-400 italic") if c.get("updatedAt") else None,
                        html.Div([
                            html.Button([icon("pencil", 12), "Edit"], id={"type": "cm-edit", "index": c["id"]}, n_clicks=0,
                                        className="text-xs text-gray-500 hover:text-indigo-600 transition-colors flex items-center gap-1"),
                            html.Button([icon("trash-2", 12), "Delete"], id={"type": "cm-del", "index": c["id"]}, n_clicks=0,
                                        className="text-xs text-gray-500 hover:text-red-600 transition-colors flex items-center gap-1"),
                        ], className="ml-auto flex items-center gap-2") if mine and not is_edit else None,
                    ], className="flex items-center gap-2 flex-wrap"),
                    html.Div([
                        dcc.Textarea(id={"type": "cm-edit-text", "index": c["id"]}, value=c["text"], rows=3, maxLength=C.FIELD_LIMITS["comment"],
                                     className="w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"),
                        html.Div([html.Button("Cancel", id={"type": "cm-edit-cancel", "index": c["id"]}, n_clicks=0, className="text-xs text-gray-500 hover:text-gray-700"),
                                  html.Button("Save", id={"type": "cm-edit-save", "index": c["id"]}, n_clicks=0,
                                              className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-3 py-1 rounded")],
                                 className="flex items-center justify-end gap-2 mt-1.5"),
                    ], className="mt-1") if is_edit else html.P(c["text"], className="text-sm text-gray-700 mt-0.5 whitespace-pre-wrap break-words"),
                ], className="flex-1 min-w-0"),
            ], className="flex gap-2.5"))
    return html.Div([
        tabs,
        html.Div(items, className="px-4 py-4 space-y-4"),
    ])


def comments_form(scope: str):
    return html.Div(html.Div([
        dcc.Input(id="cm-text", type="text", value="", maxLength=C.FIELD_LIMITS["comment"], n_submit=0,
                  placeholder="Comment on this indicator…" if scope == "mbi" else "Comment on this dimension…",
                  className="flex-1 px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"),
        html.Button(icon("send", 14), id="cm-send", n_clicks=0,
                    className="p-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors", **{"aria-label": "Send"}),
    ], className="flex items-center gap-2"), className="px-4 py-3 border-t border-gray-200")


def sharing_body(a: dict, dim: dict | None, user: dict, orgs: list[str], link_text: str | None = None, msg=None):
    is_owner = P.can_manage(user, a)
    parts = []
    if dim:
        parts.append(html.Div([
            html.Div([icon("lock", 12, "mt-0.5 shrink-0"), "Only the assessment Owner can invite contributors to this dimension."],
                     className="mb-3 flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2") if not is_owner else None,
            html.P("Invite to this dimension", className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2"),
            html.Div([
                dcc.Input(id="sh-email", type="email", placeholder="colleague@gov.org", disabled=not is_owner, maxLength=254,
                          className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-60"),
                dcc.Dropdown(id="sh-role", options=[{"label": r, "value": r} for r in C.COLLAB_ROLES], value="Contributor", clearable=False,
                             searchable=False, disabled=not is_owner, className="ig-select"),
                dcc.Dropdown(id="sh-org", options=[{"label": o, "value": o} for o in orgs], placeholder="Select or add an organisation…",
                             disabled=not is_owner, className="ig-select"),
                dcc.Input(id="sh-org-new", type="text", placeholder="…or type a new organisation", disabled=not is_owner, maxLength=120,
                          className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"),
                html.Button([icon("user-plus", 13), "Invite"], id="sh-invite", n_clicks=0, disabled=not is_owner,
                            className="w-full flex items-center justify-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white text-sm font-semibold px-3 py-2 rounded-lg transition-colors"),
                html.P(PC.ROLE_DESCRIPTIONS["Contributor"], id="sh-role-desc", className="text-[11px] text-gray-500"),
            ], className="space-y-2"),
            msg,
            html.Div([
                html.P("Invite link", className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1.5"),
                html.Div([html.Code(link_text, className="flex-1 text-[11px] text-gray-700 bg-gray-50 border border-gray-200 rounded px-2 py-1.5 break-all"),
                          dcc.Clipboard(content=link_text, className="text-xs text-indigo-600 hover:text-indigo-800 shrink-0 px-2 cursor-pointer", title="Copy")],
                         className="flex items-start gap-2"),
                html.P(f"Share this link with the invitee — it scopes them to D{dim['id']}. It only works for the invited e-mail address and expires in {C.DIMENSION_INVITE_TTL_DAYS} days.",
                       className="text-[11px] text-gray-500 mt-1.5"),
            ], className="mt-4") if link_text else None,
        ], className="px-4 py-4 border-b border-gray-200"))
    else:
        parts.append(html.P("Open a specific dimension to invite contributors just to that dimension.",
                            className="px-4 py-4 border-b border-gray-200 text-xs text-gray-500"))
    if dim:
        team = [{"id": "owner", "name": "Owner", "email": "—", "role": "Owner"}] + [
            {"id": c["userId"], "name": c["name"], "email": c["email"], "role": c["role"]} for c in dim["collaborators"]]
    else:
        team = [{"id": m["id"], "name": m["name"], "email": m["email"], "role": m["role"]} for m in a.get("team", [])]
    parts.append(html.Div([
        html.P(f"{'On this dimension' if dim else 'Assessment team'} ({len(team)})", className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2"),
        html.P("No contributors yet.", className="text-xs text-gray-400") if not team else html.Div([
            html.Div([
                html.Div(initials(m["name"]), className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-[10px] font-bold shrink-0"),
                html.Div([html.P(m["name"], className="text-xs font-medium text-gray-800 truncate"), html.P(m["email"], className="text-xs text-gray-400 truncate")],
                         className="flex-1 min-w-0"),
                html.Span(P.role_label(m["role"]), className="text-[10px] font-semibold px-2 py-0.5 rounded-full " + PC.ROLE_BADGE.get(m["role"], "bg-gray-100 text-gray-600")),
            ], className="flex items-center gap-2.5") for m in team], className="space-y-2.5"),
    ], className="px-4 py-4 border-b border-gray-200"))
    btn = "w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
    can_rt = P.can_manage(user, a)
    parts.append(html.Div([
        html.P("Export", className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2"),
        html.Div([
            html.A([icon("file-text", 14, "text-red-500"), "Export as PDF report"], href=_report_href(a["id"]), className=btn),
            html.Button([icon("file-spreadsheet", 14, "text-green-600"), "Export as CSV"], id="sh-csv", n_clicks=0, className=btn),
            html.Button([icon("file-type-2", 14, "text-blue-600"), "Download as Word (editable)"], id="sh-docx", n_clicks=0, className=btn) if can_rt else None,
        ], className="space-y-2"),
    ], className="px-4 py-4 border-b border-gray-200"))
    if can_rt:
        parts.append(html.Div([
            html.P("Sync from document", className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1"),
            html.P("Upload the .docx you edited offline. You'll review each proposed change before anything overwrites the assessment.",
                   className="text-xs text-gray-500 mb-2"),
            dcc.Upload(html.Div([icon("upload", 14), "Upload edited document"], className="flex items-center justify-center gap-2"),
                       id="sh-upload", accept=".docx", max_size=20 * 1024 * 1024, multiple=False,
                       className="w-full px-3 py-2 text-sm font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition-colors cursor-pointer"),
            html.Div(id="sh-upload-msg"),
        ], className="px-4 py-4"))
    return html.Div(parts)


def _report_href(aid: str) -> str:
    from utils.components import href

    return href("report", id=aid)

"""
Dimension entry — /?page=dimension&id=<assessment>&dim=<n>[&mbi=<k>]
(port of assessments/[id]/dimensions/[dimensionId]/page.tsx)

The indicator form, stepper, summary view, publish/unpublish status box,
side panels (comments / activity / sharing), AI Cleanup and Suggest
Responses. Every save re-validates permissions on the server.
"""
from __future__ import annotations

import time
from datetime import datetime

import constants as C
from dash import ALL, Input, Output, State, callback, clientside_callback, ClientsideFunction, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from pages.shared_panels import panel_stores
from services import ai, repository
from services import permissions as P
from services.respondents import DOCUMENT_REVIEW_RESPONDENT, is_document_review
from utils import framework as F
from utils.components import alert, href, icon, link, maturity_level_badge, modal
from utils.context import current_locale, require_user, user_message
from utils.i18n import rich, t

LEVELS = list(C.MATURITY_LEVELS)
TEXTAREA = ("w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 "
            "focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none transition-colors disabled:opacity-60 disabled:cursor-not-allowed")


# ============================================================================ builders

def _load(user, aid, dim_id, loc):
    a = repository.get_assessment(user, aid, loc, entries=True, comments=True, unpublish=True)
    dim = next((d for d in a["dimensions"] if d["id"] == dim_id), None)
    if not dim:
        raise repository.NotFound("Dimension not found")
    return a, dim


def _flags(user, a, dim, force_edit: bool):
    total = len(dim["mbis"])
    done = sum(1 for m in dim["mbis"] if m["status"] == "complete")
    published = dim["status"] == "Published"
    all_complete = done == total
    return {
        "total": total, "done": done, "allComplete": all_complete, "published": published,
        "showSummary": published or (all_complete and not force_edit),
        "canEdit": P.can_edit_dimension(user, a, dim["id"]), "isOwner": P.can_manage(user, a),
        "role": P.role_for_dimension(user, a, dim["id"]), "isAdmin": P.is_admin(user),
    }


def build_progress(loc, f, saved: bool):
    pct = (f["done"] / f["total"] * 100) if f["total"] else 0
    return html.Div([
        html.Div(html.Div(className="bg-indigo-600 h-1.5 rounded-full transition-all", style={"width": f"{pct}%"}), className="flex-1 bg-gray-200 rounded-full h-1.5"),
        html.Span([t(loc, "DimensionEntry", "mbisCompleted", completed=f["done"], total=f["total"]),
                   html.Span(t(loc, "DimensionEntry", "saved"), className="ml-2 text-green-600") if saved else None],
                  className="text-xs text-gray-500 font-medium whitespace-nowrap"),
    ], className="mb-5 flex items-center gap-3")


def build_stepper(loc, dim, active: int, f):
    if f["showSummary"]:
        return None
    steps = []
    for i, m in enumerate(dim["mbis"]):
        is_active = m["id"] == active
        cls = ("bg-indigo-600 border-indigo-600 text-white shadow-md ring-4 ring-indigo-200" if is_active
               else "bg-green-500 border-green-500 text-white hover:shadow-md" if m["status"] == "complete"
               else "bg-amber-400 border-amber-400 text-white hover:shadow-md" if m["status"] == "in-progress"
               else "bg-white border-gray-300 text-gray-400 hover:border-gray-400")
        steps.append(html.Div([
            html.Button([str(m["id"]),
                         html.Span(str(len(m["comments"])), className="absolute -top-1 -right-1 w-4 h-4 bg-orange-400 text-white text-[9px] rounded-full flex items-center justify-center") if m["comments"] else None],
                        id={"type": "mbi-step", "index": m["id"]}, n_clicks=0,
                        className=f"relative w-9 h-9 shrink-0 rounded-full flex items-center justify-center text-sm font-bold transition-all border-2 {cls}"),
            html.Div(className="w-8 h-0.5 shrink-0 " + ("bg-green-300" if m["status"] == "complete" else "bg-gray-200")) if i < len(dim["mbis"]) - 1 else None,
        ], className="flex items-center"))
    return html.Div([
        html.P(t(loc, "DimensionEntry", "indicatorsTitle"), className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2"),
        html.Div(html.Div(steps, className="flex items-center gap-0 min-w-max"), className="overflow-x-auto py-3 px-1 ig-no-scrollbar ig-stepper"),
    ], className="mb-8")


def build_statusbox(loc, a, dim, f, user):
    if not (f["allComplete"] or not f["isOwner"]):
        return None
    status_label = {"Published": t(loc, "DimensionEntry", "statusPublished"),
                    "Validated": t(loc, "DimensionEntry", "statusValidated")}.get(dim["status"], t(loc, "DimensionEntry", "statusDraft"))
    pill_cls = {"Published": "bg-green-100 text-green-700", "Validated": "bg-blue-100 text-blue-700"}.get(dim["status"], "bg-gray-100 text-gray-700")
    head = html.Div([html.Span(t(loc, "DimensionEntry", "statusLabel"), className="text-gray-500"),
                     html.Span([icon("check-circle", 11) if dim["status"] == "Published" else None, status_label],
                               className=f"inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold {pill_cls}")],
                    className="flex items-center gap-2 mb-4 text-sm")
    reqs = [r for r in a.get("unpublishRequests", []) if r["dimensionId"] == dim["id"]]
    pending = max((r for r in reqs if r["status"] == "Pending"), key=lambda r: r["requestedAt"], default=None)
    resolved = max((r for r in reqs if r["status"] != "Pending"), key=lambda r: r.get("reviewedAt") or r["requestedAt"], default=None)
    if f["isOwner"]:
        banners = []
        if dim["status"] == "Published" and pending:
            banners.append(html.Div(html.Div([icon("clock", 15, "text-amber-600 mt-0.5"), html.Div([
                html.P("Unpublish request pending Admin review", className="text-sm font-semibold text-amber-900"),
                html.P([html.Span(pending["requestedByName"], className="font-medium"),
                        f" requested this dimension be unpublished on {_dt(pending['requestedAt'])}. The dimension stays Published until a platform Admin approves the request."],
                       className="text-xs text-amber-800 mt-1 leading-relaxed"),
                html.Div([html.Span("Reason: ", className="font-semibold text-amber-900"), pending["reason"]],
                         className="mt-2 px-3 py-2 bg-white border border-amber-100 rounded text-xs text-gray-700 leading-relaxed"),
            ], className="flex-1 min-w-0")], className="flex items-start gap-2.5"), className="mb-5 bg-amber-50 border border-amber-200 rounded-lg p-4"))
        elif dim["status"] == "Published" and resolved and resolved["status"] == "Denied":
            banners.append(html.Div(html.Div([icon("alert-triangle", 15, "text-red-600 mt-0.5"), html.Div([
                html.P("Last unpublish request denied", className="text-sm font-semibold text-red-900"),
                html.P(["Denied by ", html.Span(resolved.get("reviewedByName") or "an Admin", className="font-medium"),
                        f" on {_dt(resolved.get('reviewedAt') or resolved['requestedAt'])}."], className="text-xs text-red-800 mt-1 leading-relaxed"),
                html.Div([html.Span("Admin note: ", className="font-semibold text-red-900"), resolved.get("reviewNote")],
                         className="mt-2 px-3 py-2 bg-white border border-red-100 rounded text-xs text-gray-700 leading-relaxed") if resolved.get("reviewNote") else None,
            ], className="flex-1 min-w-0")], className="flex items-start gap-2.5"), className="mb-5 bg-red-50 border border-red-200 rounded-lg p-4"))
        if dim["status"] == "Published":
            if pending and not f["isAdmin"]:
                primary = html.Span([icon("clock", 15), "Awaiting Admin review"],
                                    className="flex items-center gap-2 bg-amber-100 border border-amber-200 text-amber-800 text-sm font-semibold px-5 py-2.5 rounded-lg")
            elif f["isAdmin"]:
                primary = html.Button([icon("x", 15), t(loc, "DimensionEntry", "unpublish")], id="de-admin-unpublish", n_clicks=0,
                                      className="flex items-center gap-2 bg-white border border-red-300 text-red-600 hover:bg-red-50 text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors")
            else:
                primary = html.Button([icon("x", 15), "Request unpublish"], id="de-request-unpublish", n_clicks=0,
                                      className="flex items-center gap-2 bg-white border border-red-300 text-red-600 hover:bg-red-50 text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors")
            actions = [primary, link(t(loc, "DimensionEntry", "backToDimensions"), "dimensions", "text-indigo-600 hover:text-indigo-800 text-sm font-medium transition-colors", id=a["id"])]
        else:
            actions = [
                link([icon("check", 15), t(loc, "DimensionEntry", "publishData")], "publish",
                     "flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors", id=a["id"], dim=dim["id"]),
                html.Button(t(loc, "DimensionEntry", "editAnswers") if f["showSummary"] else t(loc, "DimensionEntry", "backToSummary"),
                            id={"type": "de-force", "index": "edit" if f["showSummary"] else "summary"}, n_clicks=0,
                            className="text-indigo-600 hover:text-indigo-800 text-sm font-medium transition-colors"),
                link(t(loc, "DimensionEntry", "leaveAsDraft"), "dimensions", "text-gray-500 hover:text-gray-700 text-sm font-medium transition-colors", id=a["id"]),
            ]
        inner = html.Div([
            html.Div([html.P(t(loc, "DimensionEntry", "whatHappensTitle"), className="font-semibold text-gray-700 mb-2"),
                      html.P(t(loc, "DimensionEntry", "whatHappensBlurb"), className="text-gray-500 text-xs leading-relaxed mb-2"),
                      html.Ul([html.Li("• " + t(loc, "DimensionEntry", k)) for k in ("publishedBullet1", "publishedBullet2", "publishedBullet3")],
                              className="text-gray-500 text-xs space-y-1")],
                     className="bg-gray-50 rounded-lg border border-gray-200 p-4 text-sm mb-5"),
            html.Div([icon("check-circle", 20, "text-green-500"), html.P(t(loc, "DimensionEntry", "allCompleteHeadline"), className="text-gray-800 font-semibold")],
                     className="flex items-center gap-2 mb-3"),
            html.P(t(loc, "DimensionEntry", "publishedSubhead" if dim["status"] == "Published" else "draftSubhead"), className="text-gray-500 text-sm mb-6"),
            *banners,
            html.Div(actions, className="flex items-center gap-4 flex-wrap"),
        ])
    elif f["canEdit"] and not f["published"] and f["showSummary"]:
        inner = html.Div([html.Button(t(loc, "DimensionEntry", "editAnswers"), id={"type": "de-force", "index": "edit"}, n_clicks=0,
                                      className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"),
                          html.P(t(loc, "DimensionEntry", "ownerOnlyNote"), className="text-sm text-gray-500")], className="flex items-center gap-4 flex-wrap")
    else:
        inner = html.P(t(loc, "DimensionEntry", "ownerOnlyNote"), className="text-sm text-gray-500")
    return html.Div([head, inner], className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 mb-6")


def _dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "")).strftime("%d/%m/%Y, %H:%M:%S")
    except (ValueError, AttributeError):
        return ""


def build_summary(loc, dim, f):
    if not f["showSummary"]:
        return None
    pub = f["published"]
    return html.Div([
        html.Div([
            html.Div([icon("lock", 14, "text-green-600") if pub else icon("check-circle", 14, "text-indigo-600"),
                      html.H2(t(loc, "DimensionEntry", "summaryPublishedHeading" if pub else "summaryDraftHeading"), className="text-sm font-semibold text-gray-800")],
                     className="flex items-center gap-2"),
            html.P(t(loc, "DimensionEntry", "summaryPublishedSubhead" if pub else "summaryDraftSubhead"), className="text-xs text-gray-500 mt-1"),
        ], className="px-6 py-4 border-b border-gray-100"),
        html.Table([
            html.Thead(html.Tr([html.Th(t(loc, "DimensionEntry", "summaryColMbi"), className="px-6 py-3 w-16"),
                                html.Th(t(loc, "DimensionEntry", "summaryColIndicator"), className="px-2 py-3 w-2/5"),
                                html.Th(t(loc, "DimensionEntry", "summaryColResult"), className="px-2 py-3"),
                                html.Th(t(loc, "DimensionEntry", "summaryColMaturity"), className="px-6 py-3 w-36 text-right")],
                               className="text-left text-[10px] font-bold text-gray-500 uppercase tracking-wide"), className="bg-gray-50"),
            html.Tbody([html.Tr([
                html.Td(m["code"], className="px-6 py-3 text-gray-400 font-medium"),
                html.Td(m["question"], className="px-2 py-3 text-gray-700 pr-3 leading-snug"),
                html.Td((m.get("entry") or {}).get("resultSummary") or html.Span("—", className="text-gray-300"), className="px-2 py-3 text-gray-600 pr-3 text-xs leading-relaxed"),
                html.Td(maturity_level_badge((m.get("entry") or {}).get("maturityBenchmark", "")), className="px-6 py-3 text-right"),
            ], className="border-t border-gray-100 align-top") for m in dim["mbis"]]),
        ], className="w-full text-sm"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden")


def maturity_cards(loc, mbi, selected: str, can_edit: bool):
    cards = []
    for lvl in LEVELS:
        on = selected == lvl
        color = F.MATURITY_COLORS[lvl]
        cls = "shadow-sm" if on else ("border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50" if can_edit else "border-gray-200 bg-white opacity-70")
        cards.append(html.Button([
            html.Span(icon("check", 12), className="absolute top-2 right-2 inline-flex items-center justify-center w-5 h-5 rounded-full",
                      style={"backgroundColor": color, "color": F.MATURITY_TEXT_COLORS[lvl]}) if on else None,
            html.Div([html.P(t(loc, "DimensionEntry", f"level{lvl}"), className="font-bold text-sm text-gray-800"),
                      html.Span(f"({F.maturity_to_score(lvl)})", className="text-[10px] text-gray-400 font-semibold")], className="flex items-baseline gap-1.5 mb-1.5"),
            html.P(mbi[lvl.lower()], className="text-xs text-gray-600 leading-relaxed"),
        ], id={"type": "mat", "index": lvl}, n_clicks=0, disabled=not can_edit, type="button", **{"aria-pressed": "true" if on else "false"},
            className=f"relative flex flex-col items-stretch justify-start text-left rounded-lg p-3 pr-7 border-2 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed {cls}",
            style={"borderColor": color, "backgroundColor": color + "12"} if on else {}))
    return cards


def _label(text, required=True, tip=None, extra=None):
    return html.Label([text, html.Span("*", className="text-red-400") if required else None, extra,
                       html.Span(icon("info", 11, "text-gray-400 cursor-help"), title=tip, className="inline-flex") if tip else None],
                      className="flex items-center gap-1.5 text-xs font-semibold text-gray-600")


def _ai_btn(field: str, can_edit: bool):
    if not C.AI_ENABLED:
        return None
    return html.Button([icon("sparkles", 11), "AI Cleanup"], id={"type": "ai-refine", "index": field}, n_clicks=0, disabled=not can_edit, type="button",
                       title="Polish this text with AI",
                       className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded px-2 py-0.5 hover:bg-indigo-50 disabled:opacity-40 disabled:cursor-not-allowed")


def build_form(loc, a, dim, mbi, f, respondents: list[str]):
    e = mbi.get("entry") or {}
    can_edit = f["canEdit"]
    role = f["role"]
    kr = [r for r in e.get("keyRespondents", []) if not is_document_review(r)]
    doc_review = any(is_document_review(r) for r in e.get("keyRespondents", []))
    opts = sorted(set(respondents) | set(kr), key=str.lower)
    q = mbi["question"]
    idx = q.find(":")
    q_el = [html.Span(q, className="font-bold")] if idx == -1 else [html.Span(q[:idx + 1], className="font-bold"), html.Span(q[idx + 1:], className="font-normal")]
    banner = None
    if not can_edit:
        if role == C.ROLE_REVIEWER:
            msg = rich(loc, "DimensionEntry", "reviewerBanner")
        elif role == C.ROLE_VIEWER:
            msg = rich(loc, "DimensionEntry", "viewerBanner")
        else:
            msg = t(loc, "DimensionEntry", "readOnlyBanner")
        banner = html.Div([icon("eye", 14), html.Span(msg)], className="mb-5 flex items-center gap-2 px-4 py-2.5 bg-blue-50 border border-blue-200 rounded-lg text-blue-700 text-xs")
    show_detail = role in (C.ROLE_ADMIN, C.ROLE_OWNER, C.ROLE_CONTRIBUTOR)
    only_resp_missing = (not kr and not doc_review) and bool(e.get("dataSource")) and bool(e.get("resultSummary")) and bool(e.get("maturityBenchmark"))
    files = e.get("files", [])
    return html.Div([
        dcc.Store(id="f-mat", data=e.get("maturityBenchmark") or ""),
        dcc.Store(id="f-files", data=files),
        banner,
        html.Div([html.P(t(loc, "DimensionEntry", "indicatorEyebrow"), className="text-indigo-600 text-sm font-semibold mb-1"),
                  html.P(q_el, className="text-gray-900 text-base leading-snug")], className="mb-5"),
        html.Div([
            html.Div([
                html.Div(_label(t(loc, "DimensionEntry", "keyRespondentsLabel"), tip=t(loc, "DimensionEntry", "keyRespondentsTooltip")), className="mb-1.5"),
                dcc.Dropdown(id="f-kr", options=[{"label": o, "value": o} for o in opts], value=kr, multi=True, disabled=not can_edit,
                             placeholder=t(loc, "DimensionEntry", "keyRespondentsPlaceholder"), className="ig-select ig-multi"),
                html.Div([
                    dcc.Input(id="f-kr-new", type="text", placeholder="Add a new respondent…", maxLength=100, disabled=not can_edit, n_submit=0,
                              className="flex-1 px-3 py-1.5 bg-gray-50 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"),
                    html.Button([icon("plus", 12), "Add"], id="f-kr-add", n_clicks=0, disabled=not can_edit, type="button",
                                className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded px-2 py-1.5 hover:bg-indigo-50 disabled:opacity-50"),
                ], className="flex items-center gap-2 mt-2") if can_edit else None,
                dcc.Checklist(id="f-docreview", options=[{"label": html.Span([html.Span(t(loc, "DimensionEntry", "documentReviewLabel"), className="font-medium text-gray-700"),
                                                                           " — ", t(loc, "DimensionEntry", "documentReviewHelp")]), "value": "yes", "disabled": not can_edit}],
                              value=["yes"] if doc_review else [], className="mt-2 text-xs text-gray-600",
                              labelClassName="flex items-start gap-2 " + ("cursor-pointer" if can_edit else "opacity-70"), inputClassName="mt-0.5"),
                html.P([icon("alert-triangle", 12), t(loc, "DimensionEntry", "keyRespondentsNeeded")], className="mt-1.5 text-xs text-amber-700 flex items-center gap-1.5") if (can_edit and only_resp_missing) else None,
            ]),
            html.Div([
                html.Div([_label(t(loc, "DimensionEntry", "dataSourceLabel"), tip=t(loc, "DimensionEntry", "dataSourceTooltip")), _ai_btn("dataSource", can_edit)],
                         className="flex items-center justify-between gap-2 mb-1.5"),
                dcc.Textarea(id="f-ds", value=e.get("dataSource", ""), rows=3, maxLength=100, disabled=not can_edit,
                             placeholder=t(loc, "DimensionEntry", "dataSourcePlaceholder"), className=TEXTAREA),
                html.Div([
                    dcc.Upload(html.Span([icon("paperclip", 11), t(loc, "DimensionEntry", "attachFile")], className="flex items-center gap-1.5"),
                               id="f-attach", multiple=True, disabled=not can_edit, max_size=C.DOCUMENT_MAX_BYTES,
                               className="text-xs text-indigo-600 hover:text-indigo-800 transition-colors border border-indigo-200 rounded px-2 py-1 hover:bg-indigo-50 cursor-pointer"),
                    html.P(f"{len(e.get('dataSource', ''))}/100", id="f-ds-count", className="text-xs text-gray-300"),
                ], className="flex items-center justify-between mt-1.5"),
                html.Div(id="f-files-list", children=_files_list(files, can_edit)),
            ]),
            html.Div([
                html.Div([_label(t(loc, "DimensionEntry", "resultsSummaryLabel"), tip=t(loc, "DimensionEntry", "resultsSummaryTooltip")), _ai_btn("resultSummary", can_edit)],
                         className="flex items-center justify-between gap-2 mb-1.5"),
                dcc.Textarea(id="f-rs", value=e.get("resultSummary", ""), rows=4, maxLength=200, disabled=not can_edit,
                             placeholder=t(loc, "DimensionEntry", "resultsSummaryPlaceholder"), className=TEXTAREA),
                html.P(f"{len(e.get('resultSummary', ''))}/200", id="f-rs-count", className="text-right text-xs text-gray-300 mt-0.5"),
            ]),
            html.Div([
                html.Div([
                    _label(t(loc, "DimensionEntry", "maturityBenchmarkLabel"), extra=html.Span(t(loc, "DimensionEntry", "selectLevel"), className="text-xs text-gray-400 font-normal ml-1")),
                    link(["About the maturity levels", icon("external-link", 11)], "about", "inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors",
                         new_tab=True, section="maturity"),
                ], className="flex items-center justify-between gap-3 mb-2 flex-wrap"),
                html.Div(maturity_cards(loc, mbi, e.get("maturityBenchmark") or "", can_edit), id="f-mat-cards", className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"),
            ]),
            html.Div([
                html.Div([_label(t(loc, "DimensionEntry", "resultDetailLabel"), required=False, tip=t(loc, "DimensionEntry", "resultDetailTooltip"),
                                 extra=html.Span(t(loc, "DimensionEntry", "resultDetailOwnerOnly"), className="text-gray-400 font-normal")), _ai_btn("resultDetail", can_edit)],
                         className="flex items-center justify-between gap-2 mb-1.5"),
                dcc.Textarea(id="f-rd", value=e.get("resultDetail", ""), rows=4, maxLength=2000, disabled=not can_edit,
                             placeholder=t(loc, "DimensionEntry", "resultDetailPlaceholder"), className=TEXTAREA),
                html.P(f"{len(e.get('resultDetail', ''))}/2000", id="f-rd-count", className="text-right text-xs text-gray-300 mt-0.5"),
            ], className="" if show_detail else "hidden"),
        ], className="space-y-5"),
        html.Div([
            html.Div([
                html.Button([icon("save", 14), t(loc, "DimensionEntry", "saveData")], id="f-save", n_clicks=0,
                            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"),
                html.Button(t(loc, "DimensionEntry", "cancel"), id="f-cancel", n_clicks=0, className="text-gray-500 hover:text-gray-700 text-sm transition-colors"),
                html.Span(id="f-save-status", className="text-sm font-medium text-green-700 flex items-center gap-1.5"),
            ] if can_edit else [html.Span([icon("lock", 12), t(loc, "DimensionEntry", "editingDisabled")], className="text-gray-400 text-xs flex items-center gap-1.5"),
                       html.Span(id="f-save-status", className="hidden"),
                       html.Button(id="f-save", n_clicks=0, className="hidden"), html.Button(id="f-cancel", n_clicks=0, className="hidden")],
                className="flex items-center gap-3"),
            html.Div([
                html.Button([icon("chevron-left", 14), t(loc, "DimensionEntry", "previous")], id="f-prev", n_clicks=0,
                            className="flex items-center gap-1.5 text-indigo-600 hover:text-indigo-800 text-sm font-medium transition-colors " + ("" if mbi["id"] > 1 else "hidden")),
                html.Button([t(loc, "DimensionEntry", "publishingOptions" if mbi["id"] == len(dim["mbis"]) else "nextIndicator"), icon("chevron-right", 14)], id="f-next", n_clicks=0,
                            className="flex items-center gap-1.5 text-indigo-600 hover:text-indigo-800 text-sm font-medium transition-colors"),
            ], className="flex items-center gap-4"),
        ], className="flex items-center justify-between pt-5 mt-5 border-t border-gray-100"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6")


def _files_list(files, can_edit):
    if not files:
        return None
    return html.Div([html.Div([icon("paperclip", 10), html.Span(f), html.Button(icon("x", 10), id={"type": "file-rm", "index": f}, n_clicks=0, disabled=not can_edit,
                                                                                className="text-gray-400 hover:text-red-500 disabled:opacity-40")],
                              className="flex items-center gap-1.5 text-xs text-indigo-600") for f in files], className="mt-1.5 space-y-1")


def _locked(loc, a, dim):
    return html.Div([
        html.Div(icon("lock", 20, "text-gray-500"), className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gray-100 mb-4"),
        html.H1("This dimension hasn't been shared with you", className="text-xl font-bold text-gray-900 mb-2"),
        html.P(["Only people the assessment Owner has assigned to ", html.Span(f"D{dim['id']}: {dim['name']}", className="font-semibold text-gray-700"),
                " can open it while it's still in draft. Once the Owner publishes the dimension, it becomes visible here and on the global dashboard."],
               className="text-sm text-gray-500 mb-6 max-w-md mx-auto"),
        link([icon("arrow-left", 14), "Back to dimensions"], "dimensions", "inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors", id=a["id"]),
    ], className="px-8 py-12 max-w-2xl mx-auto text-center")


# ============================================================================ layout

def content(ctx, a: dict, dim_id: int):
    loc, user = ctx.locale, ctx.user
    dim = next((d for d in a["dimensions"] if d["id"] == dim_id), None)
    if not dim:
        raise repository.NotFound("Dimension not found")
    if not dim["canView"]:
        return _locked(loc, a, dim)
    try:
        mbi_id = max(1, min(int(ctx.params.get("mbi") or 1), len(dim["mbis"])))
    except ValueError:
        mbi_id = 1
    f = _flags(user, a, dim, False)
    can_comment = P.can_comment_dimension(user, a, dim_id)
    mbi = dim["mbis"][mbi_id - 1]
    respondents = repository.respondents_for_country(user, a["country"]) if f["canEdit"] else []
    n_comments = len(dim["comments"]) + len(mbi["comments"])
    btn = "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-white border border-gray-200 text-gray-700 hover:bg-gray-50"
    can_suggest = C.AI_ENABLED and f["canEdit"] and not f["published"]
    return html.Div([
        dcc.Store(id="de-ctx", data={"aid": a["id"], "dim": dim_id}),
        dcc.Store(id="de-active", data=mbi_id),
        dcc.Store(id="de-force", data=False),
        dcc.Store(id="de-dirty", data=False),
        dcc.Store(id="de-reload", data=0),
        dcc.Store(id="de-saved", data=None),
        dcc.Store(id="sg-state", data=None),
        dcc.Interval(id="de-autosave", interval=3000, disabled=not f["canEdit"]),
        html.Div([
            link([icon("arrow-left", 14), t(loc, "DimensionEntry", "back")], "dimensions", "flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 transition-colors", id=a["id"]),
            html.Div([
                html.Button([icon("message-circle", 14), t(loc, "DimensionEntry", "comments"),
                             html.Span(str(n_comments), className="w-4 h-4 bg-orange-400 text-white text-[10px] rounded-full flex items-center justify-center") if n_comments else None],
                            id={"type": "panel-open", "index": "comments"}, n_clicks=0, className=btn) if can_comment else None,
                html.Button([icon("history", 14), "Activity Log"], id={"type": "panel-open", "index": "activity"}, n_clicks=0, className=btn,
                            title="Show the activity log for this dimension"),
                html.Button([icon("users", 14), t(loc, "DimensionEntry", "sharing")], id={"type": "panel-open", "index": "sharing"}, n_clicks=0, className=btn),
            ], className="flex items-center gap-2"),
        ], className="sticky top-14 z-30 bg-gray-100 border-b border-gray-200 px-8 py-3 flex items-center justify-between"),
        html.Div(html.Div([
            html.Div([
                html.P(t(loc, "DimensionEntry", "dimensionLabel"), className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-2"),
                html.Div([
                    html.Div(dcc.Dropdown(id="de-dim-select", options=[{"label": f"{d['id']}. {d['name']}", "value": d["id"]} for d in a["dimensions"]],
                                          value=dim_id, clearable=False, searchable=False, className="ig-select"), className="relative w-full max-w-xl"),
                    html.Div([
                        html.Button([icon("wand-sparkles", 15), "Suggest Responses"], id="de-suggest", n_clicks=0,
                                    className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-lg text-sm font-semibold border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 hover:border-indigo-300 transition-colors"),
                        link("Upload documents" if f["isOwner"] else "Documents", "details", "text-xs text-indigo-600 hover:text-indigo-800 hover:underline", id=a["id"], tab="documents"),
                    ], className="flex items-center gap-2") if can_suggest else None,
                ], className="flex items-center gap-3 flex-wrap"),
                html.Div(id="de-notice"),
            ], className="mb-6"),
            html.Div(build_progress(loc, f, False), id="de-progress"),
            html.Div(build_stepper(loc, dim, mbi_id, f), id="de-stepper"),
            html.Div(build_statusbox(loc, a, dim, f, user), id="de-statusbox"),
            html.Div(build_summary(loc, dim, f), id="de-summary"),
            html.Div(build_form(loc, a, dim, mbi, f, respondents), id="de-form", className="hidden" if f["showSummary"] else ""),
        ], id="de-main", className="flex-1 min-w-0 px-8 py-6 transition-all"), className="flex"),
        *panel_stores(a["id"], dim_id, mbi_id),
    ], className="bg-gray-100")


# ============================================================================ callbacks

clientside_callback(ClientsideFunction("infragov", "charCount"), Output("f-ds-count", "children"), Input("f-ds", "value"), prevent_initial_call=True)
clientside_callback(ClientsideFunction("infragov", "charCount200"), Output("f-rs-count", "children"), Input("f-rs", "value"), prevent_initial_call=True)
clientside_callback(ClientsideFunction("infragov", "charCount2000"), Output("f-rd-count", "children"), Input("f-rd", "value"), prevent_initial_call=True)
clientside_callback(ClientsideFunction("infragov", "markDirty"), Output("de-dirty", "data", allow_duplicate=True),
                    Input("f-kr", "value"), Input("f-docreview", "value"), Input("f-ds", "value"), Input("f-rs", "value"),
                    Input("f-rd", "value"), Input("f-mat", "data"), Input("f-files", "data"), prevent_initial_call=True)
clientside_callback(ClientsideFunction("infragov", "panelMargin"), Output("de-main", "className"), Input("panel-state", "data"), prevent_initial_call=True)


@callback(Output("url", "href", allow_duplicate=True), Input("de-dim-select", "value"), State("de-ctx", "data"), prevent_initial_call=True)
def _switch_dim(value, dctx_):
    if not value or value == dctx_["dim"]:
        raise PreventUpdate
    return href("dimension", id=dctx_["aid"], dim=value)


@callback(Output("f-mat", "data"), Output("f-mat-cards", "children"), Input({"type": "mat", "index": ALL}, "n_clicks"),
          State("de-ctx", "data"), State("de-active", "data"), prevent_initial_call=True)
def _pick_level(clicks, dctx_, active):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    level = dctx.triggered_id["index"]
    a = repository.get_assessment(user, dctx_["aid"], loc, entries=False)
    if not P.can_edit_dimension(user, a, dctx_["dim"]):
        raise PreventUpdate
    mbi = next(d for d in a["dimensions"] if d["id"] == dctx_["dim"])["mbis"][active - 1]
    return level, maturity_cards(loc, mbi, level, True)


@callback(Output("f-kr", "value"), Output("f-kr", "options"), Output("f-kr-new", "value"),
          Input("f-kr-add", "n_clicks"), Input("f-kr-new", "n_submit"), State("f-kr-new", "value"), State("f-kr", "value"), State("f-kr", "options"),
          prevent_initial_call=True)
def _add_respondent(n, s, new, value, options):
    if not (n or s):
        raise PreventUpdate
    v = " ".join((new or "").split())[:100]
    if not v:
        raise PreventUpdate
    value = list(value or [])
    if v.lower() not in {x.lower() for x in value}:
        value.append(v)
    if v not in {o["value"] for o in options or []}:
        options = (options or []) + [{"label": v, "value": v}]
    return value, options, ""


@callback(Output("f-files", "data"), Output("f-files-list", "children"),
          Input("f-attach", "filename"), Input({"type": "file-rm", "index": ALL}, "n_clicks"), State("f-files", "data"),
          prevent_initial_call=True)
def _files(names, rm, files):
    """Like the original, only file NAMES are recorded on the indicator (the
    file content is discarded — evidence documents go to Details → Documents)."""
    from services.validators import safe_filename

    files = list(files or [])
    trig = dctx.triggered_id
    if trig == "f-attach":
        if not names:
            raise PreventUpdate
        for n in names or []:
            n = safe_filename(n)
            if n not in files:
                files.append(n)
    elif isinstance(trig, dict) and any(rm):
        files = [f for f in files if f != trig["index"]]
    else:
        raise PreventUpdate
    return files[:50], _files_list(files[:50], True)


def _entry_from_form(kr, docrev, ds, rs, rd, mat, files, include_detail: bool) -> dict:
    respondents = [r for r in (kr or []) if not is_document_review(r)]
    if docrev:
        respondents.append(DOCUMENT_REVIEW_RESPONDENT)
    entry = {"keyRespondents": respondents, "dataSource": ds or "", "resultSummary": rs or "", "maturityBenchmark": mat or "", "files": files or []}
    if include_detail:
        entry["resultDetail"] = rd or ""
    return entry


@callback(
    Output("de-active", "data"), Output("de-dirty", "data"), Output("de-saved", "data"), Output("de-force", "data"),
    Output("url", "href", allow_duplicate=True), Output("de-notice", "children", allow_duplicate=True),
    Input("f-save", "n_clicks"), Input({"type": "mbi-step", "index": ALL}, "n_clicks"), Input("f-next", "n_clicks"),
    Input("f-prev", "n_clicks"), Input("de-autosave", "n_intervals"), Input({"type": "de-force", "index": ALL}, "n_clicks"),
    State("f-kr", "value"), State("f-docreview", "value"), State("f-ds", "value"), State("f-rs", "value"), State("f-rd", "value"),
    State("f-mat", "data"), State("f-files", "data"), State("de-active", "data"), State("de-dirty", "data"), State("de-ctx", "data"), State("de-force", "data"),
    prevent_initial_call=True,
)
def _save_and_nav(_save, steps, _next, _prev, _tick, force_clicks, kr, docrev, ds, rs, rd, mat, files, active, dirty, dctx_, force):
    trig = dctx.triggered_id
    if trig is None:
        raise PreventUpdate
    if trig == "de-autosave" and not dirty:
        raise PreventUpdate
    if trig in ("f-save", "f-next", "f-prev") and not {"f-save": _save, "f-next": _next, "f-prev": _prev}[trig]:
        raise PreventUpdate  # fired by insertion, not by a click
    if isinstance(trig, dict) and trig.get("type") in ("mbi-step", "de-force") and not any((steps if trig["type"] == "mbi-step" else force_clicks) or [0]):
        raise PreventUpdate
    user = require_user()
    aid, dim_id = dctx_["aid"], dctx_["dim"]
    saved_flag, notice = no_update, no_update
    if dirty or trig == "f-save":
        try:
            a = repository._base_or_404(aid)
            if P.can_edit_dimension(user, a, dim_id):
                include = P.can_see_result_detail(user, a, dim_id)
                repository.save_mbi_entry(user, aid, dim_id, active, _entry_from_form(kr, docrev, ds, rs, rd, mat, files, include))
                saved_flag = {"mbi": active, "at": time.time()}
        except Exception as exc:  # noqa: BLE001
            return no_update, no_update, no_update, no_update, no_update, alert(user_message(exc), "error", "mt-3 max-w-2xl")
    new_active, new_force, url = no_update, no_update, no_update
    if isinstance(trig, dict) and trig["type"] == "mbi-step":
        new_active = trig["index"]
    elif trig == "f-next":
        meta = F.dimension_meta(repository._base_or_404(aid)["kind"], dim_id)
        if active >= meta["mbiCount"]:
            url = href("publish", id=aid, dim=dim_id)
        else:
            new_active = active + 1
    elif trig == "f-prev" and active > 1:
        new_active = active - 1
    elif isinstance(trig, dict) and trig["type"] == "de-force":
        new_force = trig["index"] == "edit"
    return new_active, False, saved_flag, new_force, url, notice


@callback(Output("de-reload", "data"), Input("f-cancel", "n_clicks"), prevent_initial_call=True)
def _cancel(n):
    if not n:
        raise PreventUpdate
    return time.time()


@callback(
    Output("de-progress", "children"), Output("de-stepper", "children"), Output("de-statusbox", "children"),
    Output("de-summary", "children"), Output("de-form", "children"), Output("de-form", "className"),
    Output("page-ctx", "data", allow_duplicate=True),
    Input("de-active", "data"), Input("de-force", "data"), Input("de-reload", "data"),
    State("de-ctx", "data"), State("page-ctx", "data"), prevent_initial_call=True,
)
def _render_full(active, force, _reload, dctx_, pctx):
    user = require_user()
    loc = current_locale()
    a, dim = _load(user, dctx_["aid"], dctx_["dim"], loc)
    f = _flags(user, a, dim, bool(force))
    mbi = dim["mbis"][max(1, min(active, len(dim["mbis"]))) - 1]
    respondents = repository.respondents_for_country(user, a["country"]) if f["canEdit"] else []
    return (build_progress(loc, f, False), build_stepper(loc, dim, mbi["id"], f), build_statusbox(loc, a, dim, f, user),
            build_summary(loc, dim, f), build_form(loc, a, dim, mbi, f, respondents), "hidden" if f["showSummary"] else "",
            {**(pctx or {}), "mbi": mbi["id"]})


@callback(
    Output("de-progress", "children", allow_duplicate=True), Output("de-stepper", "children", allow_duplicate=True),
    Output("de-statusbox", "children", allow_duplicate=True), Output("de-summary", "children", allow_duplicate=True),
    Output("de-form", "className", allow_duplicate=True), Output("f-save-status", "children"),
    Input("de-saved", "data"), State("de-active", "data"), State("de-force", "data"), State("de-ctx", "data"), prevent_initial_call=True,
)
def _render_light(saved, active, force, dctx_):
    """After an (auto)save refresh status only — never the fields being typed in."""
    if not saved:
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    a, dim = _load(user, dctx_["aid"], dctx_["dim"], loc)
    f = _flags(user, a, dim, bool(force))
    status = [icon("check-circle", 15), t(loc, "DimensionEntry", "allChangesSaved")]
    return (build_progress(loc, f, saved.get("mbi") == active), build_stepper(loc, dim, active, f), build_statusbox(loc, a, dim, f, user),
            build_summary(loc, dim, f), "hidden" if f["showSummary"] else "", status)


clientside_callback(ClientsideFunction("infragov", "clearSaveStatus"), Output("f-save-status", "children", allow_duplicate=True),
                    Input("de-dirty", "data"), prevent_initial_call=True)


# ------------------------------------------------------------ publish controls

@callback(Output("refresh", "data", allow_duplicate=True), Input("de-admin-unpublish", "n_clicks"), State("de-ctx", "data"), prevent_initial_call=True)
def _admin_unpublish(n, dctx_):
    if not n:
        raise PreventUpdate
    user = require_user()
    repository.admin_unpublish_dimension(user, dctx_["aid"], dctx_["dim"])
    return time.time()


@callback(Output("modal-host", "children", allow_duplicate=True), Input("de-request-unpublish", "n_clicks"), State("de-ctx", "data"), prevent_initial_call=True)
def _open_unpublish(n, dctx_):
    if not n:
        raise PreventUpdate
    user = require_user()
    a = repository.get_assessment(user, dctx_["aid"], current_locale(), entries=False, unpublish=False)
    name = next(d["name"] for d in a["dimensions"] if d["id"] == dctx_["dim"])
    return modal([
        html.Div([
            html.Div([html.Div(icon("alert-triangle", 16, "text-amber-600"), className="w-9 h-9 rounded-full bg-amber-50 flex items-center justify-center shrink-0"),
                      html.Div([html.H3("Request unpublish", className="text-base font-semibold text-gray-900"), html.P(name, className="text-xs text-gray-500 mt-0.5")])],
                     className="flex items-start gap-3"),
            html.Button(icon("x", 16), id="ur-cancel-x", n_clicks=0, className="text-gray-400 hover:text-gray-600"),
        ], className="flex items-start justify-between px-6 py-4 border-b border-gray-200"),
        html.Div([
            html.Div(["Unpublishing requires platform-Admin approval. The dimension stays", html.Span(" Published", className="font-semibold"),
                      " while your request is reviewed. You'll see the decision (and any reviewer note) in the dimension banner and the assessment's Activity Log."],
                     className="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-lg p-3 leading-relaxed"),
            html.Div([
                html.Label(["Reason for unpublishing ", html.Span("*", className="text-red-400")], className="block text-xs font-semibold text-gray-600 mb-1.5"),
                dcc.Textarea(id="ur-reason", rows=4, maxLength=500, autoFocus=True, className=TEXTAREA,
                             placeholder="e.g. New data from the Ministry shows our prior assessment was based on a draft strategy that has since been revised…"),
                html.P("Minimum 10 characters. Maximum 500.", className="text-[11px] text-gray-400 mt-1"),
            ]),
            html.Div(id="ur-error"),
        ], className="px-6 py-4 space-y-4"),
        html.Div([html.Button("Cancel", id="ur-cancel", n_clicks=0, className="px-4 py-2 text-sm font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"),
                  html.Button([icon("send", 12), "Submit request"], id="ur-submit", n_clicks=0,
                              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg")],
                 className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200"),
    ])


@callback(Output("modal-host", "children", allow_duplicate=True), Input("ur-cancel", "n_clicks"), Input("ur-cancel-x", "n_clicks"), prevent_initial_call=True)
def _close_unpublish(a, b):
    if not (a or b):
        raise PreventUpdate
    return None


@callback(Output("modal-host", "children", allow_duplicate=True), Output("ur-error", "children"), Output("refresh", "data", allow_duplicate=True),
          Input("ur-submit", "n_clicks"), State("ur-reason", "value"), State("de-ctx", "data"), prevent_initial_call=True)
def _submit_unpublish(n, reason, dctx_):
    if not n:
        raise PreventUpdate
    user = require_user()
    try:
        repository.request_unpublish(user, dctx_["aid"], dctx_["dim"], reason or "")
    except Exception as exc:  # noqa: BLE001
        return no_update, alert(user_message(exc), "error", "text-xs"), no_update
    return None, None, time.time()


# ------------------------------------------------------------ AI Cleanup

@callback(Output("modal-host", "children", allow_duplicate=True), Input({"type": "ai-refine", "index": ALL}, "n_clicks"),
          State("f-ds", "value"), State("f-rs", "value"), State("f-rd", "value"), State("de-ctx", "data"), prevent_initial_call=True)
def _refine_open(clicks, ds, rs, rd, dctx_):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    user = require_user()
    field = dctx.triggered_id["index"]
    text = {"dataSource": ds, "resultSummary": rs, "resultDetail": rd}.get(field) or ""
    max_len = ai.FIELD_CONFIGS[field][1]
    try:
        polished, err = ai.refine(user, dctx_["aid"], dctx_["dim"], field, text), None
    except Exception as exc:  # noqa: BLE001
        polished, err = "", str(exc) if isinstance(exc, (ai.AIError,)) else user_message(exc)
    return modal([
        dcc.Store(id="ai-field", data=field),
        html.Div([html.Div([html.H2([icon("sparkles", 14, "text-indigo-500"), "AI Cleanup"], className="text-base font-semibold text-gray-900 flex items-center gap-2"),
                            html.P("Facts are preserved — grammar, phrasing, and tightness are cleaned up. Nothing is saved until you click Accept.", className="text-xs text-gray-500 mt-0.5")]),
                  html.Button(icon("x", 16), id="ai-close", n_clicks=0, className="text-gray-400 hover:text-gray-600")],
                 className="flex items-start justify-between px-6 py-4 border-b border-gray-200"),
        html.Div([
            html.Div([html.P("Your draft", className="text-[10px] font-bold text-gray-500 uppercase tracking-wide mb-1.5"),
                      html.Div(text, className="text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-lg p-3 whitespace-pre-wrap min-h-[120px]"),
                      html.P(f"{len(text)} chars", className="text-[10px] text-gray-400 mt-1")]),
            html.Div([html.P("Polished (editable)", className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-1.5"),
                      alert(err, "error") if err else dcc.Textarea(id="ai-polished", value=polished, rows=6, maxLength=max_len, className=TEXTAREA),
                      html.P(f"max {max_len} chars", className="text-[10px] text-gray-400 mt-1")]),
        ], className="grid grid-cols-1 md:grid-cols-2 gap-4 px-6 py-4"),
        html.Div([html.Button("Cancel", id="ai-cancel", n_clicks=0, className="px-4 py-2 text-sm font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"),
                  html.Button([icon("check", 14), "Accept"], id="ai-accept", n_clicks=0, disabled=bool(err),
                              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 rounded-lg")],
                 className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200"),
    ], className="max-w-3xl")


@callback(Output("modal-host", "children", allow_duplicate=True), Input("ai-close", "n_clicks"), Input("ai-cancel", "n_clicks"), prevent_initial_call=True)
def _refine_close(a, b):
    if not (a or b):
        raise PreventUpdate
    return None


@callback(Output("modal-host", "children", allow_duplicate=True), Output("f-ds", "value"), Output("f-rs", "value"), Output("f-rd", "value"),
          Input("ai-accept", "n_clicks"), State("ai-field", "data"), State("ai-polished", "value"), prevent_initial_call=True)
def _refine_accept(n, field, polished):
    if not n or not (polished or "").strip():
        raise PreventUpdate
    v = polished.strip()
    return None, v if field == "dataSource" else no_update, v if field == "resultSummary" else no_update, v if field == "resultDetail" else no_update

"""Assessment settings — /?page=details&id=…&tab=settings|team|documents|activity
(port of …/[id]/details/page.tsx + components/DocumentsTab.tsx)."""
from __future__ import annotations

import base64
import time

import constants as C
import dash
from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from pages import pages_constants as PC
from services import documents as D
from services import permissions as P
from services import repository
from utils.components import alert, icon, initials, modal
from utils.context import current_locale, require_user, user_message
from utils.countries import fy_range_display
from utils.i18n import t
from utils.panels import activity_feed, format_relative

TABS = [("settings", "Settings"), ("team", "Team & Permissions"), ("documents", "Documents"), ("activity", "Activity Log")]
IN = "w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-400"
RO = "w-full px-3 py-2 bg-gray-100 border border-gray-200 rounded-lg text-sm text-gray-700"


def _settings(loc, a, user):
    can_manage = P.can_manage(user, a)
    return html.Div([
        html.Div([
            html.H2([icon("settings", 15), "Assessment Metadata"], className="font-semibold text-gray-700 flex items-center gap-2 text-sm"),
            html.Div([html.Label("Assessment Title", className="block text-xs font-medium text-gray-600 mb-1"),
                      html.Div([icon("lock", 12, "text-gray-400"), a["title"]], className=RO + " flex items-center gap-2"),
                      html.P("The title is generated from the country and fiscal year.", className="text-[11px] text-gray-400 mt-1")]),
            html.Div([html.Label("Country", className="block text-xs font-medium text-gray-600 mb-1"),
                      html.Div(a["country"] or html.Span("No country set", className="text-gray-400 italic"), className=RO),
                      html.P("Country cannot be changed once an assessment has been created.", className="text-[11px] text-gray-400 mt-1")]),
            html.Div([html.Label("Fiscal Year(s)", className="block text-xs font-medium text-gray-600 mb-1"),
                      html.Div(fy_range_display(a["fiscalYears"]) or html.Span("No fiscal years set", className="text-gray-400 italic"), className=RO),
                      html.P("To change the fiscal year coverage, create a new assessment.", className="text-[11px] text-gray-400 mt-1")]),
            html.Div([html.Label("Department", htmlFor="dt-dept", className="block text-xs font-medium text-gray-600 mb-1"),
                      dcc.Input(id="dt-dept", value=a["department"], maxLength=C.FIELD_LIMITS["department"], disabled=not can_manage, className=IN)]),
            html.Div([html.Label("Description", htmlFor="dt-desc", className="block text-xs font-medium text-gray-600 mb-1"),
                      dcc.Textarea(id="dt-desc", value=a.get("description") or "", rows=3, maxLength=C.FIELD_LIMITS["description"], disabled=not can_manage, className=IN + " resize-none")]),
            html.Div(id="dt-save-msg"),
            html.Button([icon("save", 14), "Save Changes"], id="dt-save", n_clicks=0, disabled=not can_manage,
                        className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-4"),
        html.Div([
            html.H3([icon("trash-2", 14), "Danger Zone"], className="font-semibold text-red-700 text-sm mb-2 flex items-center gap-2"),
            html.P(t(loc, "DeleteAssessmentModal", "body"), className="text-red-600 text-xs mb-3"),
            html.Button(t(loc, "DeleteAssessmentModal", "delete"), id={"type": "del-open", "index": "details"}, n_clicks=0,
                        className="bg-red-600 hover:bg-red-700 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors"),
        ], className="bg-red-50 border border-red-200 rounded-xl p-5") if can_manage else None,
    ], className="max-w-lg space-y-5")


def _team(loc, a, user, orgs, feedback=None):
    can_manage = P.can_manage(user, a)
    owner = next((m for m in a["team"] if m["id"] == a["ownerUserId"]), None)
    form = (html.Div([icon("lock", 12, "mt-0.5 shrink-0"), "Only the assessment Owner (or an Admin) can assign team members."],
                     className="px-5 py-4 text-xs text-amber-700 bg-amber-50 flex items-start gap-2") if not can_manage else html.Div([
        html.Div([
            html.Div([html.Label(["Email ", html.Span("*", className="text-red-400")], className="block text-xs font-semibold text-gray-600 mb-1"),
                      dcc.Input(id="tm-email", type="email", placeholder="colleague@gov.org", maxLength=254, className=IN)]),
            html.Div([html.Label(["Name ", html.Span("(optional)", className="text-gray-400 font-normal")], className="block text-xs font-semibold text-gray-600 mb-1"),
                      dcc.Input(id="tm-name", type="text", placeholder="Jane Doe", maxLength=120, className=IN)]),
        ], className="grid grid-cols-1 sm:grid-cols-2 gap-3"),
        html.Div([html.Label("Organisation", className="block text-xs font-semibold text-gray-600 mb-1"),
                  html.Div([dcc.Dropdown(id="tm-org", options=[{"label": o, "value": o} for o in orgs], placeholder="Select or add an organisation…", className="ig-select flex-1"),
                            dcc.Input(id="tm-org-new", type="text", placeholder="New organisation…", maxLength=120, className=IN + " flex-1")],
                           className="flex gap-2"),
                  html.P("No previous organisations for this country yet." if not orgs else None, className="text-[11px] text-gray-400 mt-1")]),
        html.Div([html.Label("Role", className="block text-xs font-semibold text-gray-600 mb-1"),
                  dcc.Dropdown(id="tm-role", options=[{"label": "Contributor — can edit and comment", "value": "Contributor"},
                                                      {"label": "Reviewer — can comment only", "value": "Reviewer"},
                                                      {"label": "Viewer — can read only", "value": "Viewer"}], value="Contributor",
                               clearable=False, searchable=False, className="ig-select")]),
        html.Div([
            html.Div([html.Label(["Dimensions ", html.Span("*", className="text-red-400")], className="block text-xs font-semibold text-gray-600"),
                      html.Button("Select all", id="tm-all", n_clicks=0, className="text-xs font-semibold text-indigo-600 hover:text-indigo-800")],
                     className="flex items-center justify-between mb-2"),
            dcc.Checklist(id="tm-dims", options=[{"label": html.Span([html.Span(f"D{d['id']}", className="font-semibold mr-1"), d["name"]]), "value": d["id"]} for d in a["dimensions"]],
                          value=[], className="grid grid-cols-1 sm:grid-cols-2 gap-1 max-h-64 overflow-y-auto bg-gray-50 border border-gray-200 rounded-lg p-2",
                          labelClassName="flex items-start gap-2 px-2 py-1.5 rounded text-xs cursor-pointer hover:bg-white text-gray-700", inputClassName="mt-0.5"),
        ]),
        html.Div(feedback, id="tm-feedback"),
        html.Div([html.Button([icon("user-plus", 14), "Assign access"], id="tm-assign", n_clicks=0,
                              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors")],
                 className="flex items-center gap-3"),
    ], className="px-5 py-4 space-y-4"))
    with_collabs = [d for d in a["dimensions"] if d["collaborators"]]
    per_dim = html.Div("No contributors yet. Use the form above to assign team members to one or more dimensions.", className="px-5 py-8 text-center text-sm text-gray-400") if not with_collabs else html.Div([
        html.Div([
            html.Div([html.Div([html.Span(f"D{d['id']}", className="text-xs text-gray-400 font-medium w-6"), html.Span(d["name"], className="text-sm font-semibold text-gray-700")],
                               className="flex items-center gap-2"),
                      html.Span(f"{len(d['collaborators'])} member{'' if len(d['collaborators']) == 1 else 's'}", className="text-xs text-gray-400")],
                     className="flex items-center justify-between mb-2.5"),
            html.Div([html.Div([
                html.Div(initials(c["name"]), className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-[10px] font-bold shrink-0"),
                html.Div([html.P(c["name"], className="text-xs font-medium text-gray-800 truncate"), html.P(c["email"], className="text-xs text-gray-400 truncate")], className="flex-1 min-w-0"),
                html.Span(P.role_label(c["role"]), className="text-xs font-semibold px-2 py-0.5 rounded-full " + PC.ROLE_BADGE.get(c["role"], "")),
                html.Details([
                    html.Summary(icon("more-vertical", 14), className="p-1 text-gray-400 hover:text-gray-600 rounded list-none cursor-pointer", **{"aria-label": f"Actions for {c['name']} on D{d['id']}"}),
                    html.Div([html.Button([icon("shield-check", 12, "text-gray-400"), f"Change to {r}"], id={"type": "tm-role-set", "index": f"{d['id']}|{c['userId']}|{r}"}, n_clicks=0,
                                          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 hover:bg-gray-50") for r in C.COLLAB_ROLES if r != c["role"]]
                             + [html.Button([icon("user-minus", 12), "Remove from this dimension"], id={"type": "tm-remove", "index": f"{d['id']}|{c['userId']}"}, n_clicks=0,
                                            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-600 hover:bg-red-50 border-t border-gray-100"),
                                html.P(["Removing falls back to ", html.Span("Viewer", className="font-semibold"), " (read-only)."], className="px-3 py-2 text-[10px] text-gray-400 border-t border-gray-100")],
                             className="absolute right-0 top-7 bg-white rounded-lg shadow-xl border border-gray-100 w-52 py-1 z-20"),
                ], className="relative ig-menu") if can_manage else None,
            ], className="flex items-center gap-2.5 pl-8 relative") for c in d["collaborators"]], className="space-y-2"),
        ], className="px-5 py-4") for d in with_collabs], className="divide-y divide-gray-100")
    return html.Div([
        html.Div([html.H2("Owner", className="font-semibold text-gray-700 text-sm mb-3"), html.Div([
            html.Div(initials((owner or {}).get("name", "")) or "O", className="w-9 h-9 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-sm font-bold"),
            html.Div([html.P((owner or {}).get("name") or "Owner", className="font-medium text-gray-800 text-sm"), html.P((owner or {}).get("email", ""), className="text-gray-400 text-xs")], className="flex-1"),
            html.Span("Owner", className="text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700"),
        ], className="flex items-center gap-3")], className="bg-white rounded-xl border border-gray-200 shadow-sm p-5"),
        html.Div([html.Div([html.H2([icon("user-plus", 14, "text-indigo-500"), "Assign team member"], className="font-semibold text-gray-700 text-sm flex items-center gap-2"),
                            html.Span("Pick the dimensions you want to give them access to", className="text-xs text-gray-400")],
                           className="px-5 py-4 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2"), form],
                 className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"),
        html.Div([html.Div([html.H2("Per-dimension contributors", className="font-semibold text-gray-700 text-sm"),
                            html.Span("Assigned above, or invited from inside each dimension", className="text-xs text-gray-400")],
                           className="px-5 py-4 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2"), per_dim],
                 className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"),
    ], className="max-w-3xl space-y-4")


def _fmt_bytes(n):
    return f"{n} B" if n < 1024 else (f"{round(n / 1024)} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB")


def _docs(user, a, problems=None):
    can_manage = P.can_manage(user, a)
    if not P.can_read_documents(user, a):
        return html.Div([icon("lock", 18, "text-gray-400 mx-auto mb-2 block"),
                         html.P("Source documents are only visible to the assessment Owner, Admins, and the Contributors and Reviewers working on it.", className="text-sm text-gray-500")],
                        className="max-w-2xl bg-white rounded-xl border border-gray-200 p-8 text-center")
    docs = D.list_documents(user, a["id"])
    items = []
    for d in docs:
        ext = D.extension(d["filename"])
        ic, ic_cls = ("file-spreadsheet", "text-green-600") if ext in ("xlsx", "xls", "csv") else ("file-text", "text-red-500" if ext == "pdf" else "text-blue-600")
        chip = {"ready": ([icon("check-circle", 10), " Ready"], "bg-green-50 text-green-700"), "failed": ([icon("alert-triangle", 10), " Failed"], "bg-red-50 text-red-700")}.get(
            d["status"], ([icon("loader-2", 10, "animate-spin"), " Processing"], "bg-gray-100 text-gray-600"))
        meta = " · ".join(x for x in (_fmt_bytes(d["sizeBytes"]), f"{d['pageCount']} page{'' if d['pageCount'] == 1 else 's'}" if d.get("pageCount") else None) if x)
        dl = html.A(d["filename"], href=dash.get_relative_path(f"/files/document/{d['id']}"), className="text-sm font-medium text-gray-800 hover:text-indigo-700 truncate", title="Download")
        items.append(html.Li([
            icon(ic, 16, ic_cls + " mt-0.5"),
            html.Div([html.Div([dl, html.Span(chip[0], className=f"inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded {chip[1]}")], className="flex items-center gap-2 min-w-0"),
                      html.P(f"{meta} · {d['uploadedByName']}" + (f" · {d['uploadedByOrganisation']}" if d["uploadedByOrganisation"] else "") + f" · {format_relative(d['createdAt'])}", className="text-xs text-gray-400 mt-0.5"),
                      html.P(d["error"], className="text-xs text-red-600 mt-1") if d["status"] == "failed" and d["error"] else None], className="flex-1 min-w-0"),
            html.Div([
                html.Button(icon("rotate-cw", 14), id={"type": "doc-retry", "index": d["id"]}, n_clicks=0, title="Process again", className="p-1.5 text-gray-400 hover:text-indigo-600") if can_manage and d["status"] != "ready" else None,
                html.A(icon("download", 14), href=dl.href, title="Download", className="p-1.5 text-gray-400 hover:text-indigo-600"),
                html.Button(icon("trash-2", 14), id={"type": "doc-del", "index": d["id"]}, n_clicks=0, title="Delete", className="p-1.5 text-gray-400 hover:text-red-600") if can_manage else None,
            ], className="flex items-center gap-1 shrink-0"),
        ], className="flex items-start gap-3 px-5 py-3"))
    return html.Div([
        html.Div([
            html.Div([html.H2("Source documents", className="font-semibold text-gray-700 text-sm"),
                      html.P("The strategies, laws, audit reports and data your team is assessing against. Suggest Responses reads these to draft indicator answers, citing where each finding came from.",
                             className="text-xs text-gray-500 mt-1")], className="px-5 py-4 border-b border-gray-100"),
            html.Div(dcc.Upload(html.Div([icon("upload", 18, "text-gray-400 mx-auto mb-2 block"),
                                          html.P(["Drag files here, or ", html.Span("choose files", className="font-semibold text-indigo-600 hover:text-indigo-800")], className="text-sm text-gray-600"),
                                          html.P("PDF, Word (.docx), Excel (.xlsx / .xls) or CSV · up to 50 MB each", className="text-xs text-gray-400 mt-1")]),
                                id="doc-upload", multiple=True, accept=PC.DOC_ACCEPT, max_size=C.DOCUMENT_MAX_BYTES,
                                className="rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors border-gray-200 bg-gray-50/50 cursor-pointer",
                                className_active="rounded-lg border-2 border-dashed px-4 py-6 text-center border-indigo-400 bg-indigo-50/60"),
                     className="px-5 py-4 border-b border-gray-100") if can_manage else None,
            html.Div([alert(p, "warning", "text-xs") for p in problems], className="px-5 py-3 space-y-2") if problems else None,
            (html.P("No documents yet. Upload the sources your team is working from to get started." if can_manage else "No documents have been uploaded to this assessment yet.",
                    className="px-5 py-8 text-center text-sm text-gray-400") if not docs else html.Ul(items, className="divide-y divide-gray-100")),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"),
        html.P("Documents are visible to the assessment Owner, Admins, and the Contributors and Reviewers working on it. Only the Owner and Admins can add or remove them.",
               className="text-xs text-gray-400 mt-3"),
    ], className="max-w-3xl")


def _activity(a, visible=10):
    return html.Div(html.Div([
        html.Div([html.H2("Activity Log", className="font-semibold text-gray-700 text-sm"),
                  html.P("Role changes, publish events, and other assessment-level actions, newest first.", className="text-xs text-gray-400 mt-0.5")],
                 className="px-5 py-4 border-b border-gray-100"),
        activity_feed(a["activityLog"], visible, "dt-act-more",
                      empty=html.Div("No activity recorded yet for this assessment.", className="px-5 py-12 text-center text-sm text-gray-400")),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"), className="max-w-2xl")


def tab_body(user, loc, aid, tab, extra=None, visible=10):
    a = repository.get_assessment(user, aid, loc, entries=False, team=True, activity=tab == "activity", unpublish=False)
    if tab == "team":
        orgs = repository.organisations_for_country(user, a["country"]) if P.can_manage(user, a) else []
        return _team(loc, a, user, orgs, extra)
    if tab == "documents":
        return _docs(user, a, extra)
    if tab == "activity":
        return _activity(a, visible)
    return _settings(loc, a, user)


def content(ctx, a: dict):
    tab = ctx.params.get("tab") if ctx.params.get("tab") in dict(TABS) else "settings"
    return html.Div([
        dcc.Store(id="dt-ctx", data={"aid": a["id"], "tab": tab, "visible": 10}),
        html.H1("Assessment Settings", className="text-3xl font-bold text-gray-900 mb-6"),
        html.Div([html.Button(label, id={"type": "dt-tab", "index": key}, n_clicks=0,
                              className="px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px "
                              + ("border-indigo-600 text-indigo-700" if tab == key else "border-transparent text-gray-500 hover:text-gray-700"))
                  for key, label in TABS], id="dt-tabs", className="flex gap-1 mb-6 border-b border-gray-200"),
        html.Div(tab_body(ctx.user, ctx.locale, a["id"], tab), id="dt-body"),
    ], className="p-8")


def _tabs(tab):
    return [html.Button(label, id={"type": "dt-tab", "index": key}, n_clicks=0,
                        className="px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px "
                        + ("border-indigo-600 text-indigo-700" if tab == key else "border-transparent text-gray-500 hover:text-gray-700")) for key, label in TABS]


@callback(Output("dt-ctx", "data"), Output("dt-tabs", "children"), Output("dt-body", "children"),
          Input({"type": "dt-tab", "index": ALL}, "n_clicks"), State("dt-ctx", "data"), prevent_initial_call=True)
def _switch(clicks, c):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    user = require_user()
    tab = dctx.triggered_id["index"]
    return {**c, "tab": tab, "visible": 10}, _tabs(tab), tab_body(user, current_locale(), c["aid"], tab)


@callback(Output("dt-ctx", "data", allow_duplicate=True), Output("dt-body", "children", allow_duplicate=True),
          Input("dt-act-more", "n_clicks"), State("dt-ctx", "data"), prevent_initial_call=True)
def _more(n, c):
    if not n:
        raise PreventUpdate
    user = require_user()
    v = c.get("visible", 10) + 10
    return {**c, "visible": v}, tab_body(user, current_locale(), c["aid"], "activity", visible=v)


@callback(Output("dt-save-msg", "children"), Input("dt-save", "n_clicks"), State("dt-dept", "value"), State("dt-desc", "value"), State("dt-ctx", "data"), prevent_initial_call=True)
def _save(n, dept, desc, c):
    if not n:
        raise PreventUpdate
    user = require_user()
    try:
        repository.update_assessment_details(user, c["aid"], dept or "", desc or "")
    except Exception as exc:  # noqa: BLE001
        return alert(user_message(exc), "error", "text-xs")
    return html.P([icon("check", 12), "Saved."], className="text-xs text-green-700 flex items-center gap-1.5")


@callback(Output("tm-dims", "value"), Input("tm-all", "n_clicks"), State("tm-dims", "value"), State("tm-dims", "options"), prevent_initial_call=True)
def _all(n, value, options):
    if not n:
        raise PreventUpdate
    every = [o["value"] for o in options]
    return [] if len(value or []) == len(every) else every


@callback(Output("dt-body", "children", allow_duplicate=True), Input("tm-assign", "n_clicks"),
          State("tm-email", "value"), State("tm-name", "value"), State("tm-org", "value"), State("tm-org-new", "value"),
          State("tm-role", "value"), State("tm-dims", "value"), State("dt-ctx", "data"), prevent_initial_call=True)
def _assign(n, email, name, org, org_new, role, dims, c):
    if not n:
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    try:
        res = repository.assign_user_to_dimensions(user, c["aid"], dims or [], email or "", name or "", (org_new or org or "").strip(), role or "Contributor")
    except Exception as exc:  # noqa: BLE001
        return tab_body(user, loc, c["aid"], "team", alert(user_message(exc), "error", "text-xs"))
    e = (email or "").strip().lower()
    k = len(res["assigned"])
    requested = len(set(dims or []))
    if res["invited"]:
        from utils.context import base_url

        links = [html.Li([f"D{d}: ", html.Code(f"{base_url()}?page=join&token={tok}", className="break-all text-[11px]")]) for d, tok in res["links"]]
        fb = html.Div([html.P(f"{e} doesn't have an account yet — created {k} invitation link{'' if k == 1 else 's'}. Share them securely (each only works for {e}):",
                              className="text-xs text-green-700"), html.Ul(links, className="mt-1 space-y-1 text-xs text-gray-700")])
    elif k == 0:
        fb = html.P(f"{e} already had access to those dimensions.", className="text-xs text-green-700")
    elif requested - k > 0:
        fb = html.P([icon("check", 12), f"Added {e} to {k} dimension{'' if k == 1 else 's'} ({requested - k} already assigned)."], className="text-xs text-green-700 flex items-center gap-1.5")
    else:
        fb = html.P([icon("check", 12), f"Added {e} to {k} dimension{'' if k == 1 else 's'} as {role}."], className="text-xs text-green-700 flex items-center gap-1.5")
    return tab_body(user, loc, c["aid"], "team", fb)


@callback(Output("dt-body", "children", allow_duplicate=True),
          Input({"type": "tm-role-set", "index": ALL}, "n_clicks"), Input({"type": "tm-remove", "index": ALL}, "n_clicks"),
          State("dt-ctx", "data"), prevent_initial_call=True)
def _collab(r1, r2, c):
    trig = dctx.triggered_id
    if not trig or not any((r1 or []) + (r2 or [])):
        raise PreventUpdate
    user = require_user()
    parts = trig["index"].split("|")
    try:
        if trig["type"] == "tm-role-set":
            repository.set_collaborator_role(user, c["aid"], int(parts[0]), parts[1], parts[2])
        else:
            repository.remove_collaborator(user, c["aid"], int(parts[0]), parts[1])
    except Exception as exc:  # noqa: BLE001
        return tab_body(user, current_locale(), c["aid"], "team", alert(user_message(exc), "error", "text-xs"))
    return tab_body(user, current_locale(), c["aid"], "team")


@callback(Output("dt-body", "children", allow_duplicate=True), Input("doc-upload", "contents"), State("doc-upload", "filename"),
          State("dt-ctx", "data"), prevent_initial_call=True)
def _upload(contents, names, c):
    if not contents:
        raise PreventUpdate
    user = require_user()
    problems = []
    for data_url, name in zip(contents, names or []):
        try:
            raw = base64.b64decode(data_url.split(",", 1)[1], validate=False)
            D.upload_document(user, c["aid"], name, raw)
        except Exception as exc:  # noqa: BLE001
            problems.append(user_message(exc))
    return tab_body(user, current_locale(), c["aid"], "documents", problems)


@callback(Output("dt-body", "children", allow_duplicate=True), Input({"type": "doc-retry", "index": ALL}, "n_clicks"),
          Input({"type": "doc-del", "index": ALL}, "n_clicks"), State("dt-ctx", "data"), prevent_initial_call=True)
def _doc_action(r, d, c):
    trig = dctx.triggered_id
    if not trig or not any((r or []) + (d or [])):
        raise PreventUpdate
    user = require_user()
    problems = []
    try:
        if trig["type"] == "doc-retry":
            D.retry(user, trig["index"])
        else:
            D.delete_document(user, trig["index"])
    except Exception as exc:  # noqa: BLE001
        problems.append(user_message(exc))
    return tab_body(user, current_locale(), c["aid"], "documents", problems)


# ------------------------------------------------------------ delete assessment (sidebar + danger zone)

def delete_modal(loc, title, error=None):
    return modal([
        html.Div([html.Div([icon("alert-triangle", 18), html.H2(t(loc, "DeleteAssessmentModal", "title"), className="text-lg font-semibold")], className="flex items-center gap-2 text-red-600"),
                  html.Button(icon("x", 16), id="del-cancel-x", n_clicks=0, className="text-gray-400 hover:text-gray-600", **{"aria-label": t(loc, "DeleteAssessmentModal", "close")})],
                 className="flex items-center justify-between mb-3"),
        html.P(t(loc, "DeleteAssessmentModal", "body"), className="text-sm text-gray-600 mb-2"),
        html.Ul([html.Li(t(loc, "DeleteAssessmentModal", k)) for k in ("bulletDimensions", "bulletComments", "bulletActivity", "bulletTeam")],
                className="list-disc ml-5 text-sm text-gray-600 space-y-0.5 mb-4"),
        html.P(["To confirm, retype the assessment title ", html.Strong(title, className="text-gray-900"), " below:"], className="text-sm text-gray-700 mb-2"),
        dcc.Input(id="del-confirm", type="text", placeholder=title, autoFocus=True, className=IN),
        alert(error, "error", "mt-3 text-xs") if error else None,
        html.Div([html.Button(t(loc, "DeleteAssessmentModal", "cancel"), id="del-cancel", n_clicks=0, className="px-4 py-2 text-sm font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"),
                  html.Button([icon("trash-2", 14), t(loc, "DeleteAssessmentModal", "delete")], id="del-submit", n_clicks=0, disabled=True,
                              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:bg-red-300 disabled:cursor-not-allowed rounded-lg")],
                 className="flex items-center justify-end gap-2 mt-5"),
        dcc.Store(id="del-title", data=title),
    ], className="max-w-md p-6")

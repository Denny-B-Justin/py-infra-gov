"""Callbacks for chrome shared by every authenticated page: language switcher,
sign-out, tutorial modal, Admin notifications bell, delete-assessment modal."""
from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import parse_qs

import flask
from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import constants as C
from pages.details import delete_modal
from services import auth, repository
from utils.components import alert, href, icon, link
from utils.context import current_locale, require_user, user_message
from utils.layout import tutorial_modal


@callback(Output("refresh", "data", allow_duplicate=True), Input({"type": "nav-lang", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def _lang(clicks):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    code = dctx.triggered_id["index"]
    if code in C.LOCALES:
        flask.session["locale"] = code
    return time.time()


@callback(Output("url", "href", allow_duplicate=True), Input("nav-logout", "n_clicks"), prevent_initial_call=True)
def _logout(n):
    if not n:
        raise PreventUpdate
    auth.logout()
    return href("login")


@callback(Output("tutorial-host", "children", allow_duplicate=True), Input("nav-help", "n_clicks"), prevent_initial_call=True)
def _help(n):
    if not n:
        raise PreventUpdate
    return tutorial_modal(True)


@callback(Output("tutorial-host", "children", allow_duplicate=True), Input("tutorial-close", "n_clicks"), Input("tutorial-close-x", "n_clicks"), prevent_initial_call=True)
def _tutorial_close(a, b):
    if not (a or b):
        raise PreventUpdate
    flask.session["tutorial_seen"] = True
    return None


# ------------------------------------------------------------------ bell

def bell(pending: list[dict], is_admin: bool, error=None):
    count = len(pending)
    items = []
    if not is_admin:
        items = [html.P("No notifications.", className="px-4 py-6 text-xs text-gray-500 text-center")]
    elif not pending:
        items = [html.P("No pending requests. You'll see unpublish requests here as Owners submit them.", className="px-4 py-6 text-xs text-gray-500 text-center")]
    for p in pending:
        r, a, d = p["request"], p["assessment"], p["dimension"]
        try:
            when = datetime.fromisoformat(r["requestedAt"].replace("Z", "")).strftime("%d/%m/%Y, %H:%M")
        except ValueError:
            when = ""
        items.append(html.Div(html.Div([
            html.Div(icon("clock", 12, "text-amber-600"), className="w-6 h-6 rounded-full bg-amber-50 flex items-center justify-center shrink-0 mt-0.5"),
            html.Div([
                html.P(f"Unpublish request — {a['country']} · D{d['id']}", className="text-xs font-semibold text-gray-800"),
                html.P(d["name"], className="text-xs text-gray-500 truncate"),
                html.P([html.Span(r["requestedByName"], className="font-medium"), " · ", when], className="text-[11px] text-gray-400 mt-0.5"),
                html.Div([html.Span("Reason: ", className="font-semibold"), r["reason"]], className="mt-2 px-2.5 py-1.5 bg-gray-50 border border-gray-100 rounded text-[11px] text-gray-600 leading-relaxed"),
                dcc.Textarea(id={"type": "bell-note", "index": r["id"]}, rows=2, maxLength=400, placeholder="Note (required to deny)…",
                             className="mt-2 w-full px-2 py-1.5 border border-gray-300 rounded text-[11px] focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"),
                html.Div([
                    html.Button([icon("check", 11), "Approve"], id={"type": "bell-approve", "index": r["id"]}, n_clicks=0,
                                className="flex items-center gap-1 text-[11px] font-semibold text-white bg-green-600 hover:bg-green-700 px-2.5 py-1 rounded"),
                    html.Button([icon("x", 11), "Deny"], id={"type": "bell-deny", "index": r["id"]}, n_clicks=0,
                                className="flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-white border border-red-200 hover:bg-red-50 px-2.5 py-1 rounded"),
                    link(["View", icon("chevron-right", 10)], "dimension", "ml-auto flex items-center gap-0.5 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800",
                         id=a["id"], dim=d["id"]),
                ], className="flex items-center gap-2 mt-2"),
            ], className="flex-1 min-w-0"),
        ], className="flex items-start gap-2.5"), className="px-4 py-3 border-b border-gray-100"))
    return html.Details([
        html.Summary([icon("bell", 18), html.Span("9+" if count > 9 else str(count), className="absolute top-0.5 right-0.5 min-w-4 h-4 px-1 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center") if count else None],
                     className="relative p-2 text-gray-300 hover:text-white transition-colors list-none cursor-pointer", **{"aria-label": f"Notifications{f' ({count} pending)' if count else ''}"}),
        html.Div([
            html.Div([html.H3("Notifications", className="text-sm font-semibold text-gray-800"),
                      html.Span(f"{count} pending", className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full") if is_admin and count else None],
                     className="flex items-center justify-between px-4 py-3 border-b border-gray-100"),
            alert(error, "error", "m-3 text-xs") if error else None,
            html.Div(items, className="max-h-[420px] overflow-y-auto"),
        ], role="menu", className="absolute right-0 top-10 bg-white text-gray-800 rounded-lg shadow-xl w-96 border border-gray-100 z-20"),
    ], className="relative ig-menu", open=bool(error))


@callback(Output("nav-bell", "children"), Output("refresh", "data", allow_duplicate=True),
          Input({"type": "bell-approve", "index": ALL}, "n_clicks"), Input({"type": "bell-deny", "index": ALL}, "n_clicks"),
          State({"type": "bell-note", "index": ALL}, "value"), State({"type": "bell-note", "index": ALL}, "id"), prevent_initial_call=True)
def _bell(approve, deny, notes, ids):
    trig = dctx.triggered_id
    if not trig or not any((approve or []) + (deny or [])):
        raise PreventUpdate
    user = require_user()
    note = next((n for n, i in zip(notes, ids) if i["index"] == trig["index"]), "") or ""
    try:
        repository.decide_unpublish(user, trig["index"], trig["type"] == "bell-approve", note)
    except Exception as exc:  # noqa: BLE001
        return bell(repository.pending_unpublish_requests(user, current_locale()), True, user_message(exc)), no_update
    return no_update, time.time()


# ------------------------------------------------------------------ delete assessment

@callback(Output("modal-host", "children", allow_duplicate=True), Input({"type": "del-open", "index": ALL}, "n_clicks"),
          State("url", "search"), prevent_initial_call=True)
def _open_delete(clicks, search):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    user = require_user()
    aid = (parse_qs((search or "").lstrip("?")).get("id") or [""])[0]
    base = repository._base_or_404(aid)
    from services import permissions as P

    if not P.can_manage(user, base):
        raise PreventUpdate
    return delete_modal(current_locale(), base["title"])


@callback(Output("del-submit", "disabled"), Input("del-confirm", "value"), State("del-title", "data"), prevent_initial_call=True)
def _confirm_typed(v, title):
    return (v or "").strip() != title


@callback(Output("modal-host", "children", allow_duplicate=True), Input("del-cancel", "n_clicks"), Input("del-cancel-x", "n_clicks"), prevent_initial_call=True)
def _close_delete(a, b):
    if not (a or b):
        raise PreventUpdate
    return None


@callback(Output("modal-host", "children", allow_duplicate=True), Output("url", "href", allow_duplicate=True),
          Input("del-submit", "n_clicks"), State("del-confirm", "value"), State("del-title", "data"), State("url", "search"), prevent_initial_call=True)
def _delete(n, typed, title, search):
    if not n or (typed or "").strip() != title:
        raise PreventUpdate
    user = require_user()
    aid = (parse_qs((search or "").lstrip("?")).get("id") or [""])[0]
    try:
        repository.delete_assessment(user, aid)
    except Exception as exc:  # noqa: BLE001
        return delete_modal(current_locale(), title, user_message(exc) or t_fail()), no_update
    return None, href("assessments")


def t_fail():
    from utils.i18n import t

    return t(current_locale(), "DeleteAssessmentModal", "failure")

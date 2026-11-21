"""
Callbacks for the right-hand side panels shared by the Dimensions list and
the Dimension entry pages: Comments, Activity Log, Sharing (+ exports and the
Word round-trip import). Every action re-checks permissions server-side via
the repository.
"""
from __future__ import annotations

import base64
import time

from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from pages import pages_constants as PC
from services import exports, repository
from services import permissions as P
from utils.components import alert, icon, modal, side_panel
from utils.context import base_url, current_locale, require_user, user_message
from utils.panels import activity_feed, comments_body, comments_form, sharing_body


def panel_stores(aid: str, dim: int | None = None, mbi: int | None = None):
    """Components every page using the side panels must include."""
    return [
        dcc.Store(id="page-ctx", data={"aid": aid, "dim": dim, "mbi": mbi}),
        dcc.Store(id="panel-state", data={"open": None, "scope": "dimension", "editing": None, "visible": 10, "link": None, "msg": None}),
        dcc.Store(id="panel-refresh", data=0),
        dcc.Store(id="rt-changes", data=None),
        html.Div(id="side-panel"),
    ]


@callback(Output("panel-state", "data"),
          Input({"type": "panel-open", "index": ALL}, "n_clicks"), Input({"type": "panel-close", "index": ALL}, "n_clicks"),
          State("panel-state", "data"), prevent_initial_call=True)
def _toggle(opens, closes, state):
    trig = dctx.triggered_id
    if not trig or not (any(opens) or any(closes)):
        raise PreventUpdate
    state = dict(state or {})
    if trig["type"] == "panel-close":
        state["open"] = None
    else:
        state["open"] = None if state.get("open") == trig["index"] else trig["index"]
    state.update({"editing": None, "link": None, "msg": None, "visible": 10})
    return state


@callback(Output("side-panel", "children"),
          Input("panel-state", "data"), Input("panel-refresh", "data"), Input("page-ctx", "data"), prevent_initial_call=True)
def _render(state, _r, pctx):
    which = (state or {}).get("open")
    if not which or not pctx:
        return None
    user = require_user()
    loc = current_locale()
    aid, dim_id, mbi_id = pctx["aid"], pctx.get("dim"), pctx.get("mbi")
    close = {"type": "panel-close", "index": 0}
    try:
        if which == "sharing":
            a = repository.get_assessment(user, aid, loc, entries=False, team=True)
            dim = next((d for d in a["dimensions"] if d["id"] == dim_id), None) if dim_id else None
            orgs = repository.organisations_for_country(user, a["country"]) if P.can_manage(user, a) else []
            msg = alert(state.get("msg"), "error", "mt-3 text-xs") if state.get("msg") else None
            return _panel("Sharing", f"D{dim['id']}: {dim['name']}" if dim else None, sharing_body(a, dim, user, orgs, state.get("link"), msg), close)
        a = repository.get_assessment(user, aid, loc, entries=False, comments=which == "comments", activity=which == "activity")
        dim = next(d for d in a["dimensions"] if d["id"] == dim_id)
        if which == "comments":
            if not P.can_comment_dimension(user, a, dim_id):
                return None
            mbi = next((m for m in dim["mbis"] if m["id"] == mbi_id), None)
            scope = state.get("scope", "dimension")
            return _panel("Comments", f"D{dim['id']}: {dim['name']}", comments_body(dim, mbi, scope, user, state.get("editing")), close,
                          comments_form(scope))
        entries = [e for e in a["activityLog"] if e.get("dimensionId") == dim_id or dim_id in (e.get("dimensionIds") or [])]
        empty = html.Div([html.Div(icon("history", 18, "text-gray-300"), className="w-10 h-10 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3"),
                          html.P("No activity yet on this dimension. Every indicator edit, publish, or team change will show up here.",
                                 className="text-xs text-gray-400 max-w-xs mx-auto")], className="text-center py-12 px-6")
        return _panel([icon("history", 14, "text-indigo-500"), "Activity Log"], f"D{dim['id']}: {dim['name']}",
                      activity_feed(entries, state.get("visible", 10), "act-more", hide_dim=True, empty=empty), close)
    except Exception as exc:  # noqa: BLE001
        return _panel("Error", None, alert(user_message(exc), "error", "m-4"), close)


def _panel(title, subtitle, body, close_id, footer=None):
    return side_panel(title, subtitle, body, close_id, footer)


@callback(Output("panel-state", "data", allow_duplicate=True), Input("act-more", "n_clicks"), State("panel-state", "data"), prevent_initial_call=True)
def _more(n, state):
    if not n:
        raise PreventUpdate
    return {**state, "visible": state.get("visible", 10) + 10}


# ------------------------------------------------------------------ comments

@callback(Output("panel-state", "data", allow_duplicate=True), Input({"type": "cm-scope", "index": ALL}, "n_clicks"),
          State("panel-state", "data"), prevent_initial_call=True)
def _scope(clicks, state):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    return {**state, "scope": dctx.triggered_id["index"], "editing": None}


@callback(Output("panel-refresh", "data", allow_duplicate=True), Output("cm-text", "value"),
          Input("cm-send", "n_clicks"), Input("cm-text", "n_submit"),
          State("cm-text", "value"), State("panel-state", "data"), State("page-ctx", "data"), prevent_initial_call=True)
def _send(n, s, text, state, pctx):
    if not (n or s) or not (text or "").strip():
        raise PreventUpdate
    user = require_user()
    mbi = pctx.get("mbi") if state.get("scope") == "mbi" else None
    try:
        repository.add_comment(user, pctx["aid"], pctx["dim"], mbi, text)
    except Exception:  # noqa: BLE001
        raise PreventUpdate from None
    return time.time(), ""


@callback(Output("panel-state", "data", allow_duplicate=True), Output("panel-refresh", "data", allow_duplicate=True),
          Input({"type": "cm-edit", "index": ALL}, "n_clicks"), Input({"type": "cm-edit-cancel", "index": ALL}, "n_clicks"),
          Input({"type": "cm-edit-save", "index": ALL}, "n_clicks"), Input({"type": "cm-del", "index": ALL}, "n_clicks"),
          State({"type": "cm-edit-text", "index": ALL}, "value"), State({"type": "cm-edit-text", "index": ALL}, "id"),
          State("panel-state", "data"), prevent_initial_call=True)
def _comment_actions(e, c, s, d, texts, text_ids, state):
    trig = dctx.triggered_id
    if not trig or not any((x or 0) for x in (e + c + s + d)):
        raise PreventUpdate
    user = require_user()
    cid = trig["index"]
    if trig["type"] == "cm-edit":
        return {**state, "editing": cid}, no_update
    if trig["type"] == "cm-edit-cancel":
        return {**state, "editing": None}, no_update
    try:
        if trig["type"] == "cm-edit-save":
            text = next((t for t, i in zip(texts, text_ids) if i["index"] == cid), "")
            repository.update_comment(user, cid, text)
        else:
            repository.delete_comment(user, cid)
    except Exception:  # noqa: BLE001
        raise PreventUpdate from None
    return {**state, "editing": None}, time.time()


# ------------------------------------------------------------------ sharing

@callback(Output("sh-role-desc", "children"), Input("sh-role", "value"), prevent_initial_call=True)
def _role_desc(role):
    if not dctx.triggered_id:
        raise PreventUpdate
    return PC.ROLE_DESCRIPTIONS.get(role or "", "")


@callback(Output("panel-state", "data", allow_duplicate=True), Input("sh-invite", "n_clicks"),
          State("sh-email", "value"), State("sh-role", "value"), State("sh-org", "value"), State("sh-org-new", "value"),
          State("panel-state", "data"), State("page-ctx", "data"), prevent_initial_call=True)
def _invite(n, email, role, org, org_new, state, pctx):
    if not n:
        raise PreventUpdate
    user = require_user()
    try:
        token = repository.invite_to_dimension(user, pctx["aid"], pctx["dim"], email or "", role or "Contributor", (org_new or org or "").strip())
    except Exception as exc:  # noqa: BLE001
        return {**state, "msg": user_message(exc), "link": None}
    return {**state, "link": f"{base_url()}?page=join&token={token}", "msg": None}


@callback(Output("download", "data", allow_duplicate=True), Input("sh-csv", "n_clicks"), State("page-ctx", "data"), prevent_initial_call=True)
def _csv(n, pctx):
    if not n:
        raise PreventUpdate
    user = require_user()
    a = repository.get_assessment(user, pctx["aid"], current_locale())
    content, name = exports.assessment_csv(a)
    return dict(content=content, filename=name, type="text/csv")


@callback(Output("download", "data", allow_duplicate=True), Input("sh-docx", "n_clicks"), State("page-ctx", "data"), prevent_initial_call=True)
def _docx(n, pctx):
    if not n:
        raise PreventUpdate
    user = require_user()
    a = repository.get_assessment(user, pctx["aid"], "en")
    if not P.can_manage(user, a):
        raise PreventUpdate
    data, name = exports.assessment_docx(a, {"name": user["name"], "organisation": user.get("organisation")})
    return dcc.send_bytes(data, name)


def _preview(result: dict):
    changes = result["changes"]
    if not changes:
        return modal([
            html.Div([icon("check", 16, "text-green-600"), html.H2("Document is up to date", className="text-base font-semibold text-gray-900")],
                     className="flex items-center gap-2 mb-2"),
            html.P("Every field in the uploaded document already matches what's on the server — nothing to apply.", className="text-sm text-gray-600 mb-5"),
            html.Div([html.Button("Close", id="rt-close", n_clicks=0, className="px-4 py-2 text-sm font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"),
                      html.Button(id="rt-cancel", n_clicks=0, className="hidden")], className="flex justify-end"),
        ], className="max-w-md p-6")
    opts = []
    for i, c in enumerate(changes):
        locked = bool(c.get("skipReason") or c.get("unresolvable"))
        opts.append({"value": i, "disabled": locked, "label": html.Div([
            html.Span(c["mbiCode"], className="w-14 shrink-0 font-medium text-gray-500"),
            html.Div([html.P(c["fieldLabel"], className="font-medium text-gray-700"),
                      html.P(c["skipReason"], className="text-[10px] text-amber-700") if c.get("skipReason") else None,
                      html.P("Value not recognised — cannot apply", className="text-[10px] text-red-600") if c.get("unresolvable") else None],
                     className="w-32 shrink-0"),
            html.P(c["currentValue"] or "(empty)", className="flex-1 text-gray-500 line-through decoration-gray-300 break-words"),
            html.P(c["proposedValue"] or "(empty)", className="flex-1 text-gray-900 break-words"),
        ], className="flex items-start gap-3 text-xs w-full")})
    default = [o["value"] for o in opts if not o["disabled"]]
    return modal([
        html.Div([html.Div([html.H2(f"Review changes ({len(changes)})", className="text-base font-semibold text-gray-900"),
                            html.P("Uncheck any rows you don't want applied. Fields on Published dimensions and unrecognised maturity values are locked.",
                                   className="text-xs text-gray-500 mt-0.5")]),
                  html.Button(icon("x", 16), id="rt-close", n_clicks=0, className="text-gray-400 hover:text-gray-600")],
                 className="flex items-start justify-between px-6 py-4 border-b border-gray-200"),
        html.Div([alert(w, "warning", "mb-2 text-xs") for w in result["warnings"]], className="px-6 pt-3") if result["warnings"] else None,
        html.Div([
            html.Div([html.Span("MBI", className="w-14"), html.Span("Field", className="w-32"), html.Span("Current", className="flex-1"), html.Span("Proposed", className="flex-1")],
                     className="flex gap-3 text-[10px] font-bold text-gray-500 uppercase tracking-wide pl-7 pb-2"),
            dcc.Checklist(id="rt-select", options=opts, value=default, className="space-y-2",
                          labelClassName="flex items-start gap-3 py-1.5 border-t border-gray-100", inputClassName="mt-0.5"),
        ], className="px-6 py-4 max-h-[55vh] overflow-y-auto"),
        html.Div(id="rt-error", className="px-6"),
        html.Div([html.Button("Cancel", id="rt-cancel", n_clicks=0, className="px-4 py-2 text-sm font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"),
                  html.Button([icon("check", 14), "Apply selected"], id="rt-apply", n_clicks=0,
                              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg")],
                 className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200"),
    ], className="max-w-4xl")


@callback(Output("modal-host", "children", allow_duplicate=True), Output("rt-changes", "data"), Output("sh-upload-msg", "children"),
          Input("sh-upload", "contents"), State("sh-upload", "filename"), State("page-ctx", "data"), prevent_initial_call=True)
def _upload(contents, filename, pctx):
    if not contents:
        raise PreventUpdate
    user = require_user()
    try:
        a = repository.get_assessment(user, pctx["aid"], "en")
        if not P.can_manage(user, a):
            raise repository.Forbidden("Only the Owner or an Admin can sync from a document.")
        if not (filename or "").lower().endswith(".docx"):
            raise exports.ValidationError("Only .docx uploads are supported. Save your Word document as .docx and try again.")
        data = base64.b64decode(contents.split(",", 1)[1])
        result = exports.parse_roundtrip(data, a)
    except Exception as exc:  # noqa: BLE001
        return no_update, no_update, alert(user_message(exc), "error", "mt-2 text-xs")
    return _preview(result), result["changes"], None


@callback(Output("modal-host", "children", allow_duplicate=True),
          Input("rt-close", "n_clicks"), Input("rt-cancel", "n_clicks"), prevent_initial_call=True)
def _rt_close(a, b):
    if not (a or b):
        raise PreventUpdate
    return None


@callback(Output("modal-host", "children", allow_duplicate=True), Output("rt-error", "children"), Output("refresh", "data", allow_duplicate=True),
          Input("rt-apply", "n_clicks"), State("rt-select", "value"), State("rt-changes", "data"), State("page-ctx", "data"),
          prevent_initial_call=True)
def _rt_apply(n, selected, changes, pctx):
    if not n or not changes:
        raise PreventUpdate
    user = require_user()
    groups: dict[tuple[int, int], list[dict]] = {}
    for i in selected or []:
        c = changes[i]
        if c.get("skipReason") or c.get("unresolvable"):
            continue
        groups.setdefault((c["dimensionId"], c["mbiId"]), []).append(c)
    ok_by_dim: dict[int, list[str]] = {}
    failed = 0
    for (dim, mbi), cs in groups.items():
        try:
            repository.save_mbi_entry(user, pctx["aid"], dim, mbi, exports.patch_from_changes(cs), skip_log=True)
            ok_by_dim.setdefault(dim, []).append(cs[0]["mbiCode"])
        except Exception:  # noqa: BLE001
            failed += len(cs)
    for dim, codes in ok_by_dim.items():
        try:
            repository.log_dimension_import(user, pctx["aid"], dim, codes, "docx")
        except Exception:  # noqa: BLE001
            pass
    if failed:
        return no_update, alert(f"{failed} field{'s' if failed != 1 else ''} could not be saved (likely a permission or published-dimension lock).", "error", "mt-2 text-xs"), time.time()
    return None, None, time.time()

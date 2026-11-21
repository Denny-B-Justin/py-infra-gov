"""
Suggest Responses modal (port of components/SuggestResponsesModal.tsx).

Drafts indicator answers from the assessment's documents, one indicator per
request (a self-chaining callback works through the queue). Nothing is
saved until the user reviews and clicks Apply.
"""
from __future__ import annotations

import time

import constants as C
from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import ai, repository
from services import documents as D
from services.respondents import DOCUMENT_REVIEW_RESPONDENT, is_document_review
from utils.components import alert, icon, modal
from utils.context import current_locale, require_user, user_message

FIELDS = ["dataSource", "resultSummary", "resultDetail", "maturityLevel"]
LABEL = {"dataSource": "Data Source", "resultSummary": "Result Summary", "resultDetail": "Result Detail", "maturityLevel": "Maturity Level"}
LIMIT = {"dataSource": 100, "resultSummary": 200, "resultDetail": 2000}
ROWS = {"dataSource": 2, "resultSummary": 3, "resultDetail": 6}
CONF_CLS = {"high": "bg-green-50 text-green-700 border-green-200", "medium": "bg-amber-50 text-amber-700 border-amber-200", "low": "bg-red-50 text-red-700 border-red-200"}


def _answered(entry: dict | None) -> bool:
    e = entry or {}
    return bool((e.get("dataSource") or "").strip() and (e.get("resultSummary") or "").strip() and e.get("maturityBenchmark"))


def _row_ui(r: dict):
    head = html.Div([
        html.Span(r["code"], className="text-xs font-bold text-gray-500 w-14 shrink-0"),
        html.P(r["question"], className="text-sm text-gray-800 flex-1 leading-snug"),
        _status_chip(r),
    ], className="flex items-start gap-3")
    body = None
    if r["status"] == "suggested":
        s = r["suggestion"]
        fields = []
        for k in FIELDS:
            val = s.get(k) if k != "maturityLevel" else (s.get("maturityLevel") or "")
            if not val:
                continue
            conf = s["confidence"].get(k, "low")
            editor = (dcc.Dropdown(id={"type": "sg-val", "index": f"{r['mbiId']}:{k}"}, options=[{"label": lv, "value": lv} for lv in C.MATURITY_LEVELS],
                                   value=val, clearable=False, searchable=False, className="ig-select")
                      if k == "maturityLevel" else
                      dcc.Textarea(id={"type": "sg-val", "index": f"{r['mbiId']}:{k}"}, value=val, rows=ROWS[k], maxLength=LIMIT[k],
                                   className="w-full px-2.5 py-1.5 bg-gray-50 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"))
            fields.append(html.Div([
                html.Div([
                    dcc.Checklist(id={"type": "sg-chk", "index": f"{r['mbiId']}:{k}"}, options=[{"label": LABEL[k], "value": "on"}],
                                  value=["on"] if r["checked"].get(k) else [], labelClassName="flex items-center gap-1.5 text-xs font-semibold text-gray-700",
                                  inputClassName="mr-1"),
                    html.Span(f"{conf} confidence", className=f"text-[10px] font-semibold px-1.5 py-0.5 rounded border {CONF_CLS[conf]}"),
                    html.Span("· replaces current answer", className="text-[10px] text-amber-700") if r["current"].get(k) else None,
                ], className="flex items-center gap-2 mb-1"),
                editor,
                html.P(s.get("maturityReasoning"), className="text-[11px] text-gray-500 mt-1 italic") if k == "maturityLevel" and s.get("maturityReasoning") else None,
            ]))
        cites = [html.Li([html.Span(f"{c['document']} · {c['location']}", className="font-medium text-gray-700"),
                          html.Span(" ✓ verified" if c["verified"] else " · not verified", className="text-green-600" if c["verified"] else "text-amber-600"),
                          html.Span(f" — “{c['quote']}”", className="text-gray-500")], className="text-[11px]") for c in s.get("citations", [])]
        body = html.Div(fields + ([html.Div([html.P("Citations", className="text-[10px] font-bold text-gray-500 uppercase tracking-wide mb-1"),
                                             html.Ul(cites, className="space-y-1")])] if cites else []), className="mt-3 pl-[68px] space-y-3")
    elif r["status"] == "no_evidence":
        body = html.P(r.get("reason"), className="mt-2 pl-[68px] text-xs text-gray-500")
    elif r["status"] == "error":
        body = html.P(r.get("error"), className="mt-2 pl-[68px] text-xs text-red-600")
    redraft = html.Button([icon("rotate-cw", 11), "Draft"], id={"type": "sg-redraft", "index": r["mbiId"]}, n_clicks=0,
                          className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1") if r["status"] in ("skipped", "error", "no_evidence", "suggested") else None
    return html.Div([head, body, html.Div(redraft, className="pl-[68px] mt-2") if redraft else None], className="px-6 py-4 border-t border-gray-100")


def _status_chip(r):
    st = r["status"]
    m = {
        "queued": ("Queued", "bg-gray-100 text-gray-600", "clock"), "running": ("Drafting…", "bg-indigo-50 text-indigo-700", "loader-2"),
        "suggested": ("Draft ready", "bg-green-50 text-green-700", "check-circle"), "no_evidence": ("No evidence", "bg-gray-100 text-gray-600", "file-search"),
        "error": ("Failed", "bg-red-50 text-red-700", "alert-triangle"), "skipped": ("Already answered", "bg-gray-50 text-gray-500", "check"),
    }[st]
    return html.Span([icon(m[2], 11, "animate-spin" if st == "running" else ""), m[0]],
                     className=f"inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 {m[1]}")


def _shell(rows, docs_count, mark_review=True, error=None):
    running = any(r["status"] in ("queued", "running") for r in rows)
    return modal([
        html.Div([
            html.Div([html.H2([icon("wand-sparkles", 15, "text-indigo-600"), "Suggest Responses"], className="text-base font-semibold text-gray-900 flex items-center gap-2"),
                      html.P(f"Drafted from {docs_count} source document{'s' if docs_count != 1 else ''}. Review each draft — nothing is saved until you apply it.",
                             className="text-xs text-gray-500 mt-0.5")]),
            html.Button(icon("x", 16), id="sg-close", n_clicks=0, className="text-gray-400 hover:text-gray-600"),
        ], className="flex items-start justify-between px-6 py-4 border-b border-gray-200"),
        html.Div([_row_ui(r) for r in rows], id="sg-rows", className="max-h-[60vh] overflow-y-auto"),
        alert(error, "error", "mx-6 my-2 text-xs") if error else None,
        html.Div([
            dcc.Checklist(id="sg-docreview", options=[{"label": "Record “Document review” as Key Respondent on indicators that have none", "value": "on"}],
                          value=["on"] if mark_review else [], labelClassName="flex items-center gap-2 text-xs text-gray-600", inputClassName="mr-1"),
            html.Div([html.Button("Cancel", id="sg-cancel", n_clicks=0, className="px-4 py-2 text-sm font-semibold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"),
                      html.Button([icon("check", 14), "Apply selected"], id="sg-apply", n_clicks=0, disabled=running,
                                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 rounded-lg")],
                     className="flex items-center gap-2"),
        ], className="flex items-center justify-between gap-3 px-6 py-4 border-t border-gray-200"),
    ], className="max-w-4xl")


def _make_row(m, saved=None):
    r = {"mbiId": m["id"], "code": m["code"], "question": m["question"], "status": "queued",
         "current": {"dataSource": (m.get("entry") or {}).get("dataSource", ""), "resultSummary": (m.get("entry") or {}).get("resultSummary", ""),
                     "resultDetail": (m.get("entry") or {}).get("resultDetail", ""), "maturityLevel": (m.get("entry") or {}).get("maturityBenchmark", "")},
         "checked": {}}
    if saved:
        _apply_response(r, {"status": saved["status"], "suggestion": saved.get("suggestion"), "reason": saved.get("reason")})
    return r


def _apply_response(r, resp):
    if resp["status"] == "suggested":
        s = resp["suggestion"]
        r.update(status="suggested", suggestion=s)
        r["checked"] = {k: bool(s.get(k) if k != "maturityLevel" else s.get("maturityLevel")) and not (r["current"].get(k) or "").strip()
                        and s["confidence"].get(k) != "low" for k in FIELDS}
    else:
        r.update(status="no_evidence", reason=resp.get("reason", ""))


@callback(Output("modal-host", "children", allow_duplicate=True), Output("sg-state", "data"),
          Input("de-suggest", "n_clicks"), State("de-ctx", "data"), prevent_initial_call=True)
def _open(n, dctx_):
    if not n:
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    try:
        a = repository.get_assessment(user, dctx_["aid"], loc, entries=True, unpublish=False)
        dim = next(d for d in a["dimensions"] if d["id"] == dctx_["dim"])
        docs = [d for d in D.list_documents(user, a["id"]) if d["status"] == "ready"]
        if not docs:
            raise repository.NotFound("Upload source documents first: Settings → Documents")
        saved = {s["mbiId"]: s for s in repository.list_saved_suggestions(user, a["id"], dim["id"])}
    except Exception as exc:  # noqa: BLE001
        return modal([html.Div([alert(user_message(exc), "error"),
                                html.Div([html.Button("Close", id="sg-close", n_clicks=0, className="mt-4 px-4 py-2 text-sm font-semibold border rounded-lg"),
                                          html.Button(id="sg-cancel", n_clicks=0, className="hidden")], className="flex justify-end")], className="p-6")]), no_update
    rows, queue = [], []
    for m in dim["mbis"]:
        r = _make_row(m, saved.get(m["id"]))
        if m["id"] not in saved:
            if _answered(m.get("entry")):
                r["status"] = "skipped"
            else:
                queue.append(m["id"])
        rows.append(r)
    state = {"rows": rows, "queue": queue, "docs": len(docs), "tick": time.time()}
    return _shell(rows, len(docs)), state


@callback(Output("sg-state", "data", allow_duplicate=True), Input("sg-state", "data"), State("de-ctx", "data"), prevent_initial_call=True)
def _pump(state, dctx_):
    """Self-chaining: drafts ONE queued indicator per round-trip."""
    if not state or not state.get("queue"):
        raise PreventUpdate
    user = require_user()
    mbi_id = state["queue"][0]
    rows = state["rows"]
    row = next(r for r in rows if r["mbiId"] == mbi_id)
    try:
        resp = ai.suggest(user, dctx_["aid"], dctx_["dim"], mbi_id, current_locale())
        _apply_response(row, resp)
    except Exception as exc:  # noqa: BLE001
        row.update(status="error", error=str(exc) if isinstance(exc, ai.AIError) else user_message(exc))
    return {**state, "rows": rows, "queue": state["queue"][1:], "tick": time.time()}


@callback(Output("sg-rows", "children"), Output("sg-apply", "disabled"), Input("sg-state", "data"), prevent_initial_call=True)
def _render(state):
    if not state:
        raise PreventUpdate
    rows = state["rows"]
    queued = set(state.get("queue", []))
    view = [{**r, "status": ("running" if state["queue"] and r["mbiId"] == state["queue"][0] else "queued")} if r["mbiId"] in queued else r for r in rows]
    return [_row_ui(r) for r in view], bool(queued)


@callback(Output("sg-state", "data", allow_duplicate=True), Input({"type": "sg-redraft", "index": ALL}, "n_clicks"), State("sg-state", "data"), prevent_initial_call=True)
def _redraft(clicks, state):
    if not dctx.triggered_id or not any(clicks) or not state:
        raise PreventUpdate
    mid = dctx.triggered_id["index"]
    if mid in state["queue"]:
        raise PreventUpdate
    return {**state, "queue": state["queue"] + [mid], "tick": time.time()}


@callback(Output("modal-host", "children", allow_duplicate=True), Output("sg-state", "data", allow_duplicate=True),
          Input("sg-close", "n_clicks"), Input("sg-cancel", "n_clicks"), prevent_initial_call=True)
def _close(a, b):
    if not (a or b):
        raise PreventUpdate
    return None, None


@callback(Output("modal-host", "children", allow_duplicate=True), Output("sg-state", "data", allow_duplicate=True),
          Output("de-reload", "data", allow_duplicate=True), Output("de-notice", "children"),
          Input("sg-apply", "n_clicks"), State({"type": "sg-chk", "index": ALL}, "value"), State({"type": "sg-chk", "index": ALL}, "id"),
          State({"type": "sg-val", "index": ALL}, "value"), State({"type": "sg-val", "index": ALL}, "id"),
          State("sg-docreview", "value"), State("de-ctx", "data"), State("sg-state", "data"), prevent_initial_call=True)
def _apply(n, chk_vals, chk_ids, vals, val_ids, docreview, dctx_, state):
    if not n or not state:
        raise PreventUpdate
    user = require_user()
    values = {i["index"]: v for v, i in zip(vals, val_ids)}
    picked: dict[int, dict] = {}
    for v, i in zip(chk_vals, chk_ids):
        if v:
            mid, field = i["index"].split(":")
            picked.setdefault(int(mid), {})[field] = values.get(i["index"], "")
    a = repository.get_assessment(user, dctx_["aid"], current_locale(), entries=True, unpublish=False)
    dim = next(d for d in a["dimensions"] if d["id"] == dctx_["dim"])
    fields_n, ok_ind, failed, review_n = 0, 0, 0, 0
    for mid, fs in picked.items():
        patch = {("maturityBenchmark" if k == "maturityLevel" else k): v for k, v in fs.items()}
        entry = dim["mbis"][mid - 1].get("entry") or {}
        if docreview and not [r for r in entry.get("keyRespondents", []) if r]:
            patch["keyRespondents"] = [DOCUMENT_REVIEW_RESPONDENT]
            review_n += 1
        try:
            repository.save_mbi_entry(user, dctx_["aid"], dctx_["dim"], mid, patch, ai_assisted=True)
            fields_n += len(fs)
            ok_ind += 1
        except Exception:  # noqa: BLE001
            failed += len(fs)
    if failed:
        msg = f"Applied {fields_n} suggested field{'' if fields_n == 1 else 's'}; {failed} could not be saved."
        kind = "warning"
    else:
        note = f" Key Respondents recorded as Document review on {review_n} of them." if review_n else ""
        msg = f"Applied and saved {fields_n} suggested field{'' if fields_n == 1 else 's'} across {ok_ind} indicator{'' if ok_ind == 1 else 's'}.{note}"
        kind = "success"
    return None, None, time.time(), alert(msg, kind, "mt-3 max-w-2xl")

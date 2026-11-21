"""Publish a dimension — /?page=publish&id=…&dim=… (port of …/[dimensionId]/publish/page.tsx)."""
from __future__ import annotations

import time

from dash import Input, Output, State, callback, html, dcc, no_update
from dash.exceptions import PreventUpdate

from services import permissions as P
from services import repository
from utils import framework as F
from utils.components import alert, icon, link
from utils.context import current_locale, require_user, user_message
from utils.i18n import rich, t


def _owner_only(loc, a, dim_id):
    return html.Div(html.Div([
        html.Div(icon("lock", 28, "text-amber-500"), className="w-16 h-16 bg-amber-50 rounded-full flex items-center justify-center mx-auto mb-5"),
        html.H2(t(loc, "DimensionPublish", "ownerOnlyTitle"), className="text-2xl font-bold text-gray-900 mb-2"),
        html.P(t(loc, "DimensionPublish", "ownerOnlyBody"), className="text-gray-500 text-sm mb-8"),
        link(t(loc, "DimensionPublish", "backToDimension"), "dimension", "inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 px-6 rounded-lg text-sm transition-colors",
             id=a["id"], dim=dim_id),
    ], className="bg-white rounded-2xl shadow-md border border-gray-200 max-w-md w-full p-10 text-center"), className="min-h-[60vh] bg-gray-100 flex items-center justify-center px-4")


def _avg(dim):
    done = [m for m in dim["mbis"] if m["status"] == "complete"]
    return (sum((m.get("entry") or {}).get("score") or 0 for m in dim["mbis"]) / len(done)) if done else 0


def published_view(loc, a, dim):
    return html.Div(html.Div([
        html.Div(icon("check-circle", 32, "text-green-500"), className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-5"),
        html.H2(t(loc, "DimensionPublish", "publishedTitle"), className="text-2xl font-bold text-gray-900 mb-2"),
        html.P(rich(loc, "DimensionPublish", "publishedBody", {"dim": lambda s: html.Span(s, className="font-semibold text-gray-700")}, name=dim["name"]),
               className="text-gray-500 text-sm mb-2"),
        html.P(rich(loc, "DimensionPublish", "averageScore", {"b": lambda s: html.Span(s, className="font-bold text-gray-600")}, score=round(_avg(dim))),
               className="text-gray-400 text-xs mb-8"),
        html.Div([
            link(t(loc, "DimensionPublish", "backToDimensions"), "dimensions", "w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors text-center", id=a["id"]),
            link(t(loc, "DimensionPublish", "viewVisualization"), "visualization", "w-full border border-gray-200 text-gray-700 hover:bg-gray-50 font-medium py-2.5 rounded-lg text-sm transition-colors text-center", id=a["id"]),
        ], className="flex flex-col gap-3"),
    ], className="bg-white rounded-2xl shadow-md border border-gray-200 max-w-md w-full p-10 text-center"), className="min-h-[60vh] bg-gray-100 flex items-center justify-center")


def content(ctx, a: dict, dim_id: int):
    loc, user = ctx.locale, ctx.user
    dim = next((d for d in a["dimensions"] if d["id"] == dim_id), None)
    if not dim:
        raise repository.NotFound("Dimension not found")
    if not P.can_manage(user, a):
        return _owner_only(loc, a, dim_id)
    if dim["status"] == "Published":
        return published_view(loc, a, dim)
    total = len(dim["mbis"])
    done = sum(1 for m in dim["mbis"] if m["status"] == "complete")
    prefix = F.display_prefix(a["kind"])
    incomplete = []
    for m in dim["mbis"]:
        if m["status"] == "complete":
            continue
        e = m.get("entry") or {}
        missing = [x for x, cond in (
            (t(loc, "DimensionPublish", "missingKeyRespondents"), not e.get("keyRespondents")),
            (t(loc, "DimensionPublish", "missingDataSource"), not (e.get("dataSource") or "").strip()),
            (t(loc, "DimensionPublish", "missingResultsSummary"), not (e.get("resultSummary") or "").strip()),
            (t(loc, "DimensionPublish", "missingMaturity"), not e.get("maturityBenchmark"))) if cond]
        if missing:
            incomplete.append((m["id"], f"{prefix}{dim_id}.{m['id']}", missing))
    avg = _avg(dim)
    warn = None
    if done < total:
        warn = html.Div([
            html.P(t(loc, "DimensionPublish", "incompleteWarning", completed=done, total=total)),
            html.P(t(loc, "DimensionPublish", "incompleteListTitle"), className="mt-3 text-xs font-semibold text-amber-800") if incomplete else None,
            html.Ul([html.Li([link(code, "dimension", "font-semibold text-amber-900 hover:underline shrink-0", id=a["id"], dim=dim_id, mbi=mid),
                              html.Span(", ".join(miss))], className="text-xs flex gap-2") for mid, code, miss in incomplete], className="mt-1.5 space-y-1") if incomplete else None,
        ], className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-5 text-amber-700 text-sm")
    return html.Div(html.Div([
        dcc.Store(id="pub-ctx", data={"aid": a["id"], "dim": dim_id}),
        link([icon("arrow-left", 14), t(loc, "DimensionPublish", "backToDimension")], "dimension", "inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 mb-6",
             id=a["id"], dim=dim_id),
        html.Div([
            html.H1(t(loc, "DimensionPublish", "title"), className="text-2xl font-bold text-gray-900 mb-1"),
            html.P(rich(loc, "DimensionPublish", "subtitle", {"b": lambda s: html.Span(s, className="font-medium text-gray-700")}, name=dim["name"]), className="text-gray-500 text-sm mb-6"),
            html.Div(html.Div([
                html.Div([html.P(f"{done}/{total}", className="text-2xl font-bold text-indigo-700"), html.P(t(loc, "DimensionPublish", "statMBIsCompleted"), className="text-xs text-gray-500 mt-1")]),
                html.Div([html.P(str(round(avg)), className="text-2xl font-bold text-indigo-700"), html.P(t(loc, "DimensionPublish", "statAverageScore"), className="text-xs text-gray-500 mt-1")]),
                html.Div([html.P("100%" if done == total else f"{round(done / total * 100)}%", className="text-2xl font-bold text-green-600"),
                          html.P(t(loc, "DimensionPublish", "statComplete"), className="text-xs text-gray-500 mt-1")]),
            ], className="grid grid-cols-3 gap-4 text-center"), className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-5"),
            html.Div(html.Div([icon("globe", 18, "text-blue-500 mt-0.5"), html.Div([
                html.P(t(loc, "DimensionPublish", "whatHappensTitle"), className="font-semibold text-blue-800 text-sm mb-1"),
                html.Ul([html.Li("• " + t(loc, "DimensionPublish", f"whatHappensBullet{i}")) for i in (1, 2, 3, 4)], className="text-blue-700 text-xs space-y-1.5"),
            ])], className="flex gap-3"), className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-5"),
            warn,
            dcc.Checklist(id="pub-confirm", options=[{"label": t(loc, "DimensionPublish", "confirmation"), "value": "yes"}], value=[],
                          labelClassName="flex items-start gap-3 cursor-pointer text-sm text-gray-700", inputClassName="mt-0.5 w-4 h-4", className="mb-6"),
            html.Div(id="pub-error"),
            html.Div([
                html.Button([icon("check", 15), t(loc, "DimensionPublish", "publishButton")], id="pub-submit", n_clicks=0, disabled=True,
                            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold px-6 py-2.5 rounded-lg transition-colors text-sm"),
                link(t(loc, "DimensionPublish", "leaveAsDraft"), "dimension", "text-gray-500 hover:text-gray-700 text-sm transition-colors", id=a["id"], dim=dim_id),
            ], className="flex items-center gap-4"),
            dcc.Store(id="pub-complete", data=done == total),
        ], className="max-w-2xl"),
    ], className="px-8 py-6"), className="bg-gray-100", id="pub-root")


@callback(Output("pub-submit", "disabled"), Input("pub-confirm", "value"), State("pub-complete", "data"))
def _enable(v, complete):
    return not (v and complete)


@callback(Output("pub-root", "children"), Output("pub-error", "children"), Input("pub-submit", "n_clicks"), State("pub-ctx", "data"), prevent_initial_call=True)
def _publish(n, pctx):
    if not n:
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    try:
        repository.publish_dimension(user, pctx["aid"], pctx["dim"])
        a = repository.get_assessment(user, pctx["aid"], loc)
    except Exception as exc:  # noqa: BLE001
        return no_update, alert(user_message(exc), "error", "mb-4")
    dim = next(d for d in a["dimensions"] if d["id"] == pctx["dim"])
    return published_view(loc, a, dim), None

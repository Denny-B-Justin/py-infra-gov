"""Global visualization — /?page=dashboard&kind=infragov|pagfa (port of app/[locale]/dashboard/page.tsx).
Only PUBLISHED data (public fields) is ever loaded here."""
from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import repository
from utils import framework as F
from utils.charts import comparison_bars
from utils.components import dropdown, href, icon, legend, link
from utils.context import current_locale, require_user
from utils.countries import fy_range_display
from utils.i18n import t
from utils.layout import app_shell


def _country_rows(data: list[dict], kind: str) -> list[dict]:
    by: dict[str, dict] = {}
    for a in data:
        if a["kind"] != kind:
            continue
        c = by.setdefault(a["country"], {"perDim": {}, "assessments": set()})
        c["assessments"].add(a["id"])
        for did, mbis in a["dims"].items():
            scores = [m["score"] for m in mbis if m["score"]]
            if scores:
                c["perDim"].setdefault(did, []).append(sum(scores) / len(scores))
    rows = []
    for country, d in by.items():
        per = {k: sum(v) / len(v) for k, v in d["perDim"].items()}
        if per:
            rows.append({"country": country, "assessments": len(d["assessments"]), "publishedDims": len(per), "avgScore": sum(per.values()) / len(per)})
    return sorted(rows, key=lambda r: -r["avgScore"])


def _indicators(data, kind, dim_id, loc):
    meta = F.dimension_meta(kind, dim_id, loc)
    return [{"id": i + 1, "code": F.mbi_code(dim_id, i + 1), "question": q["question"]} for i, q in enumerate(meta["indicators"])] if meta else []


def chart_section(loc, kind, data, dim_id, ind_id):
    meta = F.dimension_meta(kind, dim_id, loc)
    inds = _indicators(data, kind, dim_id, loc)
    ind = next((i for i in inds if i["id"] == ind_id), None)
    best: dict[str, dict] = {}
    for a in data:
        mbis = a["dims"].get(dim_id)
        if a["kind"] != kind or not mbis:
            continue
        m = next((x for x in mbis if x["id"] == ind_id), None)
        if not m or m["score"] is None:
            continue
        cur = best.get(a["country"])
        if not cur or a["updatedAt"] > cur["updatedAt"]:
            best[a["country"]] = {"score": m["score"], "updatedAt": a["updatedAt"], "fy": fy_range_display(a["fiscalYears"])}
    bars = sorted([{"country": c, "label": f"{c} ({v['fy']})" if v["fy"] else c, "score": v["score"]} for c, v in best.items()], key=lambda r: -r["score"])
    title = f"{meta['shortName']} · {ind['code']}" if (meta and ind) else (meta["shortName"] if meta else "Cross-country comparison")
    return html.Div([
        html.Div([html.H2(title, className="text-sm font-semibold text-gray-700"), html.Span(t(loc, "GlobalDashboard", "mostRecentCaption"), className="text-xs text-gray-400")],
                 className="flex items-baseline justify-between mb-3"),
        html.P(ind["question"], className="text-xs text-gray-500 mb-3 leading-snug") if ind else None,
        html.Div(t(loc, "GlobalDashboard", "noIndicatorPublished", code=ind["code"]) if ind else t(loc, "GlobalDashboard", "selectIndicatorPrompt"),
                 className="py-12 text-center text-sm text-gray-400 bg-gray-50 rounded-lg") if not bars else comparison_bars(bars, loc),
    ])


def _ind_options(data, kind, dim_id, loc):
    return [{"label": f"{i['code']} — " + (i["question"][:80] + "…" if len(i["question"]) > 80 else i["question"]), "value": i["id"]}
            for i in _indicators(data, kind, dim_id, loc)]


def layout(ctx):
    loc = ctx.locale
    kind = "pagfa" if ctx.params.get("kind") == "pagfa" else "infragov"
    data = repository.published_overview(ctx.user, loc)
    rows = _country_rows(data, kind)
    pillars = F.dimensions_for(kind, loc)
    kinds = {a["kind"] for a in data}
    first_dim = pillars[0]["id"]
    sel = "w-full"
    stat = lambda label, value: html.Div([html.P(value, className="text-2xl font-bold text-indigo-700"), html.P(label, className="text-xs text-gray-500 mt-0.5")],  # noqa: E731
                                         className="bg-white rounded-xl border border-gray-200 p-4")
    body = [html.Div([icon("bar-chart-2", 40, "text-gray-300 mx-auto mb-4 block"), html.P(t(loc, "GlobalDashboard", "emptyTitle"), className="text-gray-500 font-medium"),
                      html.P(t(loc, "GlobalDashboard", "emptyBody"), className="text-gray-400 text-sm mt-1")],
                     className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center")] if not rows else [
        html.Div([
            html.Label([icon("map-pin", 11), t(loc, "GlobalDashboard", "countries")], className="text-[10px] font-bold text-gray-400 uppercase tracking-wide shrink-0 flex items-center gap-1"),
            html.Div(dcc.Dropdown(id="gd-country", options=[{"label": f"{r['country']} ({r['publishedDims']}/{len(pillars)} {t(loc, 'GlobalDashboard', 'countOptionSuffixPillar' if kind == 'pagfa' else 'countOptionSuffixDim')})",
                                                             "value": r["country"]} for r in rows], placeholder=t(loc, "GlobalDashboard", "viewProfile"),
                                  clearable=False, className="ig-select"), className="relative flex-1 min-w-[260px] max-w-md"),
            html.Span(t(loc, "GlobalDashboard", "countLine", count=len(rows)), className="text-xs text-gray-500"),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 mb-6 flex items-center gap-3 flex-wrap"),
        html.Section([
            html.Div([html.Label(t(loc, "GlobalDashboard", "pillarLabel" if kind == "pagfa" else "dimensionLabel"), className="block text-[10px] font-bold text-gray-400 uppercase tracking-wide mb-1.5"),
                      dropdown("gd-dim", [{"label": f"D{d['id']} — {d['name']}", "value": d["id"]} for d in pillars], first_dim, className=sel)], className="mb-4"),
            html.Div([html.Label(t(loc, "GlobalDashboard", "indicatorLabel"), className="block text-[10px] font-bold text-gray-400 uppercase tracking-wide mb-1.5"),
                      dropdown("gd-ind", _ind_options(data, kind, first_dim, loc), 1, className=sel),
                      html.P(t(loc, "GlobalDashboard", "pickIndicatorHint"), className="text-xs text-gray-400 mt-1.5")], className="mb-5"),
            html.Div(chart_section(loc, kind, data, first_dim, 1), id="gd-chart"),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6"),
    ]
    main = html.Main([
        dcc.Store(id="gd-kind", data=kind),
        html.Div([
            html.Div([icon("globe", 16), html.Span(t(loc, "GlobalDashboard", "eyebrow"), className="text-xs font-bold uppercase tracking-wider")], className="flex items-center gap-2 mb-1 text-indigo-600"),
            html.H1(t(loc, "GlobalDashboard", "titlePagfa" if kind == "pagfa" else "titleInfragov"), className="text-3xl font-bold text-gray-900 mb-2"),
            html.P(t(loc, "GlobalDashboard", "subtitlePagfa" if kind == "pagfa" else "subtitleInfragov"), className="text-gray-500 max-w-2xl"),
        ], className="mb-8"),
        html.Div([link("PAG-FA" if fw == "pagfa" else "InfraGov", "dashboard", "px-4 py-1.5 rounded text-xs font-semibold transition-colors "
                       + (("bg-[#37b37f] text-white" if fw == "pagfa" else "bg-indigo-600 text-white") if kind == fw else "text-gray-500 hover:text-gray-700"), kind=fw)
                  for fw in ("infragov", "pagfa")], className="inline-flex items-center bg-white border border-gray-200 rounded-lg p-1 mb-6") if len(kinds) > 1 else None,
        html.Div([stat(t(loc, "GlobalDashboard", "statCountries"), str(len(rows))), stat(t(loc, "GlobalDashboard", "statAssessments"), str(sum(r["assessments"] for r in rows))),
                  stat(t(loc, "GlobalDashboard", "statPublishedPillars" if kind == "pagfa" else "statPublishedDimensions"), str(sum(r["publishedDims"] for r in rows)))],
                 className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8"),
        legend(loc),
        *body,
    ], className="pt-28 px-8 py-8 max-w-7xl mx-auto w-full")
    return app_shell(ctx, main)


@callback(Output("url", "href", allow_duplicate=True), Input("gd-country", "value"), State("gd-kind", "data"), prevent_initial_call=True)
def _country(c, kind):
    if not c:
        raise PreventUpdate
    return href("country", name=c.lower(), kind=kind)


@callback(Output("gd-ind", "options"), Output("gd-ind", "value"), Input("gd-dim", "value"), State("gd-kind", "data"), prevent_initial_call=True)
def _dim(dim_id, kind):
    require_user()
    loc = current_locale()
    opts = _ind_options([], kind, dim_id, loc)
    return opts, (opts[0]["value"] if opts else None)


@callback(Output("gd-chart", "children"), Input("gd-ind", "value"), State("gd-dim", "value"), State("gd-kind", "data"), prevent_initial_call=True)
def _chart(ind, dim_id, kind):
    user = require_user()
    loc = current_locale()
    return chart_section(loc, kind, repository.published_overview(user, loc), dim_id, ind)

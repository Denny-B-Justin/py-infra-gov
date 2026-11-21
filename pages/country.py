"""Country profile — /?page=country&name=<country>&kind=… (port of dashboard/[country]/page.tsx).
Only published data / public fields are shown."""
from __future__ import annotations

from datetime import datetime, timezone

from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import exports, repository
from utils import framework as F
from utils.charts import country_bars
from utils.components import icon, link, score_badge
from utils.context import current_locale, require_user
from utils.countries import fy_range_display
from utils.i18n import t
from utils.layout import app_shell


def _latest(assessments: list[dict], dim_id: int):
    best = None
    for a in assessments:
        mbis = a["dims"].get(dim_id)
        if not mbis or not any(m["score"] for m in mbis):
            continue
        if best and best["updatedAt"] >= a["updatedAt"]:
            continue
        best = {"updatedAt": a["updatedAt"], "fiscalYears": a["fiscalYears"], "mbis": mbis}
    return best


def build(loc, data, slug, kind, comparison, views):
    all_c = [a for a in data if a["country"].lower() == slug]
    country = all_c[0]["country"] if all_c else None
    if not country:
        return None, None, []
    mine = [a for a in all_c if a["kind"] == kind]
    pillars = F.dimensions_for(kind, loc)
    summary = [{"meta": m, "latest": lt} for m in pillars if (lt := _latest(mine, m["id"]))]
    others = sorted({a["country"] for a in data if a["country"].lower() != slug})
    compare = None
    if comparison:
        cas = [a for a in data if a["country"] == comparison and a["kind"] == kind]
        compare = {}
        for m in pillars:
            lt = _latest(cas, m["id"])
            compare[m["id"]] = {"mbis": {x["code"]: x["score"] for x in lt["mbis"]} if lt else {}, "fiscalYears": lt["fiscalYears"] if lt else []}
    return {"country": country, "summary": summary, "others": others, "compare": compare, "kinds": {a["kind"] for a in all_c},
            "count": len(mine), "pillars": pillars}, country, summary


def _text_view(loc, mbis, country, cfy, comparison, comp_fy, comp):
    th = "font-semibold py-1.5"
    return html.Table([
        html.Thead(html.Tr([html.Th("MBI", className=f"{th} w-14"), html.Th("Indicator", className=f"{th} w-2/5"), html.Th("Result summary", className=f"{th} pr-3"),
                            html.Th([country, html.Span(f" ({cfy})", className="font-normal text-gray-400") if cfy else None], className=f"{th} w-36 text-right"),
                            html.Th([comparison, html.Span(f" ({comp_fy})", className="font-normal text-gray-400") if comp_fy else None], className=f"{th} w-36 text-right print:hidden") if comparison else None],
                           className="text-gray-500 text-left")),
        html.Tbody([html.Tr([
            html.Td(m["code"], className="py-2 text-gray-400 font-medium align-top"),
            html.Td(m["question"], className="py-2 text-gray-700 pr-3"),
            html.Td(m["summary"] or "—", className="py-2 text-gray-600 pr-3"),
            html.Td(score_badge(m["score"], loc), className="py-2 text-right"),
            html.Td((score_badge(comp.get(m["code"]), loc, comparison=True) if comp.get(m["code"]) else html.Span("—" if m["code"] in comp else "N/A", className="text-gray-300 text-[10px]")),
                    className="py-2 text-right print:hidden") if comparison else None,
        ], className="border-t border-gray-100 align-top") for m in mbis]),
    ], className="w-full text-xs table-fixed")


def sections(loc, model, comparison, views, expanded):
    out = []
    for item in model["summary"]:
        meta, latest = item["meta"], item["latest"]
        did = meta["id"]
        ce = (model["compare"] or {}).get(did) if comparison else None
        missing = bool(comparison) and ce is not None and not ce["mbis"]
        eff_comp = None if missing else (comparison or None)
        comp = {} if missing or not ce else ce["mbis"]
        cfy, comp_fy = fy_range_display(latest["fiscalYears"]), (fy_range_display(ce["fiscalYears"]) if ce and not missing else "")
        view = views.get(str(did), "text")
        is_open = did in expanded
        text = _text_view(loc, latest["mbis"], model["country"], cfy, eff_comp, comp_fy, comp)
        if view == "text":
            body = text
        else:
            cl = f"{model['country']} ({cfy})" if cfy else model["country"]
            cmpl = (f"{eff_comp} ({comp_fy})" if comp_fy else eff_comp) if eff_comp else None
            body = html.Div([html.Div(country_bars(latest["mbis"], cl, cmpl, comp, loc, t(loc, "CountryProfile", "noData")), className="print:hidden"),
                             html.Div(text, className="hidden print:block")])
        toggle = html.Div([
            html.Button([icon("file-text", 11), "Text"], id={"type": "cp-view", "index": f"{did}:text"}, n_clicks=0,
                        className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold transition-colors " + ("bg-white text-gray-800 shadow-sm" if view == "text" else "text-gray-500 hover:text-gray-700")),
            html.Button([icon("bar-chart-3", 11), "Chart"], id={"type": "cp-view", "index": f"{did}:charts"}, n_clicks=0,
                        className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold transition-colors " + ("bg-white text-gray-800 shadow-sm" if view == "charts" else "text-gray-500 hover:text-gray-700")),
        ], className="flex items-center gap-0.5 bg-gray-100 rounded-md p-0.5 print:hidden") if is_open else None
        out.append(html.Section([
            html.Header([
                html.Button([icon("chevron-down", 14, "text-gray-400 transition-transform print:hidden " + ("" if is_open else "-rotate-90")),
                             html.Span(f"D{did}", className="text-gray-500 font-medium text-sm w-8 shrink-0"), html.H3(meta["name"], className="text-gray-900 font-semibold text-sm")],
                            id={"type": "cp-toggle", "index": did}, n_clicks=0, className="flex items-center gap-3 flex-1 text-left", **{"aria-expanded": "true" if is_open else "false"}),
                toggle,
            ], className="flex items-center justify-between gap-3 px-5 py-3 " + ("border-b border-gray-100" if is_open else "")),
            html.Div([icon("info", 12, "text-amber-600 shrink-0 mt-0.5"), html.P(f"{comparison} has not currently published data for this dimension.", className="text-xs text-amber-800")],
                     className="flex items-start gap-2 px-5 py-2 bg-amber-50 border-b border-amber-100") if missing else None,
            html.Div(body, className="px-5 pb-5 pt-2 " + ("" if is_open else "hidden print:block")),
        ], className="bg-white rounded-xl border border-gray-200 overflow-hidden pdf-card print:break-inside-avoid"))
    return out


def _fw_cls(fw: str, kind: str, present: bool) -> str:
    if kind == fw:
        return "bg-[#37b37f] text-white" if fw == "pagfa" else "bg-indigo-600 text-white"
    return "text-gray-500 hover:text-gray-700" if present else "text-gray-300 cursor-not-allowed pointer-events-none"


def layout(ctx):
    loc = ctx.locale
    slug = (ctx.params.get("name") or "").strip().lower()[:100]
    kind = "pagfa" if ctx.params.get("kind") == "pagfa" else "infragov"
    data = repository.published_overview(ctx.user, loc)
    model, country, summary = build(loc, data, slug, kind, "", {})
    if not country:
        main = html.Main([html.H1(t(loc, "CountryProfile", "countryNotFound"), className="text-2xl font-bold text-gray-900 mb-2"),
                          html.P(t(loc, "CountryProfile", "noPublishedDataFor", slug=slug), className="text-gray-500 mb-6"),
                          link(f"← {t(loc, 'CountryProfile', 'back')}", "dashboard", "text-indigo-600 hover:text-indigo-800 text-sm font-medium")],
                         className="pt-28 px-8 py-8 max-w-4xl mx-auto w-full")
        return app_shell(ctx, main)
    expanded = [summary[0]["meta"]["id"]] if summary else []
    now = datetime.now(timezone.utc)
    head_right = html.Div([
        html.Div([link("PAG-FA" if fw == "pagfa" else "InfraGov", "country",
                       "px-3 py-1.5 rounded text-xs font-semibold transition-colors " + _fw_cls(fw, kind, fw in model["kinds"]),
                       name=slug, kind=fw) for fw in ("infragov", "pagfa")], className="flex items-center bg-white border border-gray-200 rounded-lg p-1") if len(model["kinds"]) > 1 else None,
        html.Div([html.P(t(loc, "CountryProfile", "downloadData"), className="text-[10px] font-bold text-gray-400 uppercase tracking-wide mb-1 text-right"),
                  html.Div([html.Button(icon("file-text", 18), id="cp-pdf", n_clicks=0, title=t(loc, "CountryProfile", "downloadPdf"), **{"aria-label": t(loc, "CountryProfile", "downloadPdfAria")},
                                        className="p-2 rounded-lg border border-gray-200 bg-white text-red-500 hover:bg-red-50 transition-colors"),
                            html.Button(icon("file-spreadsheet", 18), id="cp-csv", n_clicks=0, title=t(loc, "CountryProfile", "downloadCsv"), **{"aria-label": t(loc, "CountryProfile", "downloadCsvAria")},
                                        className="p-2 rounded-lg border border-gray-200 bg-white text-green-600 hover:bg-green-50 transition-colors")],
                           className="flex items-center gap-2")], className="print:hidden"),
    ], className="flex items-end gap-4 flex-wrap")
    main = html.Main([
        dcc.Store(id="cp-state", data={"slug": slug, "kind": kind, "comparison": "", "views": {}, "expanded": expanded}),
        html.Div(html.Div([html.Span(f"InfraGov Assessment Tool · {'PAG-FA' if kind == 'pagfa' else 'InfraGov 2.0'}"),
                           html.Span(f"{now.day} {now.strftime('%b %Y')}", className="text-gray-500 font-normal normal-case tracking-normal")],
                          className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-gray-700"), className="hidden print:block pdf-header"),
        link([icon("arrow-left", 14), t(loc, "CountryProfile", "back")], "dashboard", "inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 mb-6 print:hidden", kind=kind),
        html.Div([
            html.Div([html.Div([icon("map-pin", 14), html.Span(t(loc, "CountryProfile", "countryProfileLabel"), className="text-xs font-bold uppercase tracking-wider")],
                               className="flex items-center gap-2 mb-1 text-indigo-600"),
                      html.H1(country, className="text-3xl font-bold text-gray-900"),
                      html.P(t(loc, "CountryProfile", "pillarsPublishedLine" if kind == "pagfa" else "dimensionsPublishedLine",
                               published=len(summary), total=len(model["pillars"]), count=model["count"]), className="text-gray-500 text-sm mt-1")]),
            head_right,
        ], className="flex items-start justify-between gap-4 mb-6 flex-wrap"),
        html.Div(t(loc, "CountryProfile", "emptyMessage", country=country), className="bg-white rounded-xl border border-gray-200 p-8 text-center text-sm text-gray-500") if not summary else html.Div([
            html.Div([
                html.Label([icon("users", 11), t(loc, "CountryProfile", "compareWith")], className="text-[10px] font-bold text-gray-400 uppercase tracking-wide shrink-0 flex items-center gap-1"),
                html.Div(dcc.Dropdown(id="cp-compare", options=[{"label": t(loc, "CountryProfile", "noOtherCountriesWithData" if not model["others"] else "noComparison"), "value": ""}]
                                      + [{"label": c, "value": c} for c in model["others"]], value="", clearable=False, disabled=not model["others"], className="ig-select"),
                         className="relative flex-1 min-w-[220px] max-w-sm"),
                html.Div(id="cp-legend", className="flex items-center gap-3 text-xs"),
            ], className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 mb-3 flex items-center gap-3 flex-wrap print:hidden"),
            html.P([icon("info", 11, "text-gray-500"), "Data visualized below represents the country's most recent assessment."], className="flex items-center gap-1.5 text-xs text-gray-500 mb-4 print:hidden"),
            html.Div(sections(loc, model, "", {}, expanded), id="cp-sections", className="space-y-4"),
        ]),
    ], className="pt-28 px-8 py-8 max-w-5xl mx-auto w-full print:pt-0")
    return app_shell(ctx, main)


@callback(Output("cp-state", "data"), Output("cp-sections", "children"), Output("cp-legend", "children"),
          Input("cp-compare", "value"), Input({"type": "cp-view", "index": ALL}, "n_clicks"), Input({"type": "cp-toggle", "index": ALL}, "n_clicks"),
          State("cp-state", "data"), prevent_initial_call=True)
def _update(comparison, views_n, toggles, state):
    trig = dctx.triggered_id
    if trig is None:
        raise PreventUpdate
    if isinstance(trig, dict) and not any((views_n or []) + (toggles or [])):
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    state = dict(state)
    if trig == "cp-compare":
        state["comparison"] = comparison or ""
    elif trig["type"] == "cp-view":
        did, v = trig["index"].split(":")
        state["views"] = {**state.get("views", {}), did: v}
    else:
        exp = set(state.get("expanded", []))
        exp.symmetric_difference_update({trig["index"]})
        state["expanded"] = sorted(exp)
    data = repository.published_overview(user, loc)
    model, country, _ = build(loc, data, state["slug"], state["kind"], state["comparison"], state["views"])
    if state["comparison"] not in (model["others"] if model else []):
        state["comparison"] = ""
        model, country, _ = build(loc, data, state["slug"], state["kind"], "", state["views"])
    leg = [html.Span([html.Span(className="w-2.5 h-2.5 rounded-full", style={"backgroundColor": F.PRIMARY_COLOR}), country], className="flex items-center gap-1.5 text-gray-600"),
           html.Span([html.Span(className="w-2.5 h-2.5 rounded-full", style={"backgroundColor": F.COMPARE_COLOR}), state["comparison"]], className="flex items-center gap-1.5 text-gray-600")] if state["comparison"] else None
    return state, sections(loc, model, state["comparison"], state["views"], set(state["expanded"])), leg


@callback(Output("download", "data", allow_duplicate=True), Input("cp-csv", "n_clicks"), State("cp-state", "data"), prevent_initial_call=True)
def _csv(n, state):
    if not n:
        raise PreventUpdate
    user = require_user()
    loc = current_locale()
    model, country, summary = build(loc, repository.published_overview(user, loc), state["slug"], state["kind"], state["comparison"], {})
    if not country:
        raise PreventUpdate
    content, name = exports.country_csv(country, state["comparison"], summary, model["compare"], loc)
    return dict(content=content, filename=name, type="text/csv")

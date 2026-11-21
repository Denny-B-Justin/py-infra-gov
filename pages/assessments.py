"""Assessments list — /?page=assessments (port of app/[locale]/assessments/page.tsx)."""
from __future__ import annotations

from datetime import datetime

import constants as C
from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html
from dash.exceptions import PreventUpdate

from pages import pages_constants as PC
from services import permissions as P
from services import repository
from utils.components import framework_chip, href, icon, link
from utils.context import current_locale, require_user
from utils.countries import fy_range_display
from utils.i18n import t
from utils.layout import app_shell


def _date(iso: str, fmt: str = "%d/%m/%Y") -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "")).strftime(fmt)
    except ValueError:
        return ""


def _seg(label, active, key, active_cls="bg-indigo-600 text-white"):
    return html.Button(label, id={"type": "al-ctl", "index": key}, n_clicks=0, className="px-3 py-1.5 rounded text-xs font-semibold transition-colors "
                       + (active_cls if active else "text-gray-500 hover:text-gray-700"))


def body(loc: str, rows: list[dict], view: str, flt: str, fw: str, can_create: bool):
    visible = [r for r in rows if (flt != "mine" or r["mine"]) and (fw == "all" or r["kind"] == fw)]
    both = len({r["kind"] for r in rows}) > 1
    controls = [html.Div([_seg(t(loc, "Assessments", "filterAll"), flt == "all", "filter:all"),
                          _seg(t(loc, "Assessments", "filterMine"), flt == "mine", "filter:mine")],
                         className="flex items-center bg-white border border-gray-200 rounded-lg p-1")]
    if both:
        controls.append(html.Div([
            _seg("All frameworks", fw == "all", "fw:all", "bg-gray-800 text-white"),
            _seg("InfraGov", fw == "infragov", "fw:infragov"),
            _seg("PAG-FA", fw == "pagfa", "fw:pagfa", "bg-[#37b37f] text-white"),
        ], className="flex items-center bg-white border border-gray-200 rounded-lg p-1"))
    controls.append(html.Div([
        html.Button(icon("layout-grid", 16), id={"type": "al-ctl", "index": "view:grid"}, n_clicks=0, className="p-1.5 rounded transition-colors "
                    + ("bg-gray-100 text-gray-800" if view == "grid" else "text-gray-400 hover:text-gray-600")),
        html.Button(icon("list", 16), id={"type": "al-ctl", "index": "view:list"}, n_clicks=0, className="p-1.5 rounded transition-colors "
                    + ("bg-gray-100 text-gray-800" if view == "list" else "text-gray-400 hover:text-gray-600")),
    ], className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg p-1"))
    header = html.Div([html.H1(t(loc, "Assessments", "heading"), className="text-3xl font-bold text-gray-900"),
                       html.Div(controls, className="flex items-center gap-3")], className="flex items-center justify-between mb-6 flex-wrap gap-3")
    if not visible:
        content = html.Div([
            html.Div(icon("layout-grid", 28, "text-indigo-400"), className="w-16 h-16 bg-indigo-50 rounded-full flex items-center justify-center mx-auto mb-4"),
            html.H3(t(loc, "Assessments", "emptyMineTitle" if flt == "mine" else "emptyAllTitle"), className="text-lg font-semibold text-gray-800 mb-1"),
            html.P(t(loc, "Assessments", "emptyMineBody" if flt == "mine" else "emptyAllBody"), className="text-gray-500 text-sm mb-6"),
            link([icon("plus", 16), t(loc, "Assessments", "createAssessment")], "new-assessment",
                 "inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors") if can_create else None,
        ], className="text-center py-24 bg-white rounded-xl border border-gray-200")
    elif view == "grid":
        content = html.Div([
            link([
                html.Div([html.Span(P.role_label(r["role"]), className="inline-block text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded "
                                    + PC.ROLE_COLORS.get(r["role"], "bg-gray-400")), framework_chip(r["kind"])],
                         className="mb-3 flex items-center justify-between gap-2"),
                html.H3(r["title"], className="text-indigo-700 font-semibold text-sm group-hover:text-indigo-900 mb-0.5 transition-colors leading-snug"),
                html.P(fy_range_display(r["fiscalYears"]), className="text-xs text-indigo-400 font-medium mb-1"),
                html.P([icon("calendar", 11), _date(r["createdAt"])], className="text-gray-400 text-xs mb-4 flex items-center gap-1"),
                html.Div([html.Span(f"{r['published']}/{r['total']}", className="text-3xl font-bold text-indigo-700 leading-none"),
                          html.Span(t(loc, "Assessments", "dimensionsPublished"), className="text-xs text-gray-500 leading-tight")],
                         className="flex items-center gap-2"),
            ], "dimensions", "bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md hover:border-indigo-200 transition-all group block", id=r["id"])
            for r in visible
        ], className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4")
    else:
        th = "text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide"
        content = html.Div(html.Table([
            html.Thead(html.Tr([html.Th(t(loc, "Assessments", "columnAssessment"), className=th.replace("px-4", "px-5")),
                                html.Th(t(loc, "Assessments", "columnRole"), className=th), html.Th("Framework", className=th),
                                html.Th(t(loc, "Assessments", "columnCreated"), className=th),
                                html.Th(t(loc, "Assessments", "columnPublished"), className=th), html.Th(className="px-4 py-3")]),
                       className="bg-gray-50 border-b border-gray-200"),
            html.Tbody([html.Tr([
                html.Td([link(r["title"], "dimensions", "text-indigo-700 font-medium hover:text-indigo-900", id=r["id"]),
                         html.P(f"{r['country']} · {fy_range_display(r['fiscalYears'])} — {r['department']}", className="text-xs text-gray-400")],
                        className="px-5 py-3.5"),
                html.Td(html.Span(P.role_label(r["role"]), className="text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded "
                                  + PC.ROLE_COLORS.get(r["role"], "bg-gray-400")), className="px-4 py-3.5"),
                html.Td(framework_chip(r["kind"]), className="px-4 py-3.5"),
                html.Td(_date(r["createdAt"]), className="px-4 py-3.5 text-gray-500"),
                html.Td(f"{r['published']}/{r['total']}", className="px-4 py-3.5 font-semibold text-gray-700"),
                html.Td(link(icon("chevron-right", 16), "dimensions", "text-gray-400", id=r["id"]), className="px-4 py-3.5"),
            ], className="border-b border-gray-100 hover:bg-indigo-50/40 transition-colors " + ("" if i % 2 == 0 else "bg-gray-50/50"))
                for i, r in enumerate(visible)]),
        ], className="w-full text-sm"), className="bg-white rounded-xl border border-gray-200 overflow-hidden")
    return [header, content]


def layout(ctx):
    loc = ctx.locale
    rows = repository.list_assessments(ctx.user)
    can_create = P.can_create_assessment(ctx.user)
    main = html.Main([
        dcc.Store(id="al-state", data={"view": "grid", "filter": "all", "fw": "all"}),
        html.Div(link([icon("plus", 16), t(loc, "Assessments", "newAssessment")], "new-assessment",
                      "flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors shadow-sm"),
                 className="flex items-center justify-end mb-2") if can_create else None,
        html.Div(body(loc, rows, "grid", "all", "all", can_create), id="al-body"),
    ], className="pt-28 px-8 py-8")
    return app_shell(ctx, main)


@callback(Output("al-state", "data"), Output("al-body", "children"),
          Input({"type": "al-ctl", "index": ALL}, "n_clicks"), State("al-state", "data"), prevent_initial_call=True)
def _controls(clicks, state):
    trig = dctx.triggered_id
    if not trig or not any(clicks):
        raise PreventUpdate
    user = require_user()
    key, val = trig["index"].split(":", 1)
    state = dict(state or {})
    state[key] = val
    rows = repository.list_assessments(user)
    loc = current_locale()
    return state, body(loc, rows, state.get("view", "grid"), state.get("filter", "all"), state.get("fw", "all"), P.can_create_assessment(user))

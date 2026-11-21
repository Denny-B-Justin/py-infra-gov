"""New assessment — /?page=new-assessment[&kind=pagfa] (port of assessments/new/page.tsx)."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import constants as C
from services import permissions as P
from services import repository
from services.db import get_db, jload
from utils.components import alert, dropdown, href, icon, link
from utils.context import current_locale, require_user, user_message
from utils.countries import countries, current_fy_label, find_country, fy_display, fy_period_description, generate_fy_options
from utils.i18n import t
from utils.layout import app_shell

LABEL = "block text-sm font-medium text-gray-700 mb-1.5"
INPUT = ("w-full px-4 py-2.5 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-500 "
         "appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent")


def _fw_buttons(loc: str, fw: str):
    def btn(kind, ic, title_key, desc_key):
        on = fw == kind
        if kind == "pagfa":
            frame = "border-[#37b37f] bg-[#37b37f]/10" if on else "border-gray-200 hover:border-gray-300 bg-white"
            ic_c, title_c = ("text-[#37b37f]", "text-[#266F50]") if on else ("text-gray-500", "text-gray-800")
        else:
            frame = "border-indigo-500 bg-indigo-50" if on else "border-gray-200 hover:border-gray-300 bg-white"
            ic_c, title_c = ("text-indigo-600", "text-indigo-700") if on else ("text-gray-500", "text-gray-800")
        return html.Button([
            icon(ic, 14, f"mb-1.5 {ic_c}"),
            html.Span(t(loc, "NewAssessment", title_key), className=f"block text-sm font-semibold mb-1 {title_c}"),
            html.P(t(loc, "NewAssessment", desc_key), className="text-xs text-gray-600 leading-snug"),
        ], id={"type": "na-fw", "index": kind}, n_clicks=0, type="button", **{"aria-pressed": "true" if on else "false"},
            className=f"flex flex-col items-start text-left p-3 rounded-lg border-2 transition-all {frame}")
    return [btn("infragov", "layers", "frameworkInfragovTitle", "frameworkInfragovDesc"),
            btn("pagfa", "landmark", "frameworkPagfaTitle", "frameworkPagfaDesc")]


def layout(ctx):
    if not P.can_create_assessment(ctx.user):
        return dcc.Location(id="na-bounce", href=href("assessments"), refresh=False)
    loc = ctx.locale
    kind = "pagfa" if ctx.params.get("kind") == "pagfa" else "infragov"
    main = html.Main(html.Div([
        html.Div([
            link([icon("arrow-left", 14), t(loc, "NewAssessment", "back")], "assessments",
                 "inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-800 transition-colors mb-4"),
            html.H1(t(loc, "NewAssessment", "title"), className="text-2xl font-bold text-gray-900"),
            html.P(t(loc, "NewAssessment", "subtitle"), className="text-gray-600 text-sm mt-1"),
        ], className="mb-6"),
        dcc.Store(id="na-fw", data=kind),
        html.Div([
            html.Div([
                html.Div([html.Label(t(loc, "NewAssessment", "frameworkLabel"), className="block text-sm font-medium text-gray-700"),
                          link(t(loc, "NewAssessment", "frameworkMoreInfo"), "about", "text-xs font-medium text-indigo-600 hover:text-indigo-800 underline-offset-2 hover:underline", new_tab=True, section="frameworks")],
                         className="flex items-baseline justify-between mb-2 gap-3"),
                html.Div(_fw_buttons(loc, kind), id="na-fw-buttons", className="grid grid-cols-2 gap-3"),
            ]),
            html.Div([
                html.Label(t(loc, "NewAssessment", "countryLabel"), className=LABEL),
                dropdown("na-country", [{"label": c["name"], "value": c["name"]} for c in countries()], None,
                         t(loc, "NewAssessment", "countryPlaceholder"), searchable=True),
                html.P(id="na-fy-hint", className="text-xs text-gray-600 mt-1.5 flex items-center gap-1.5"),
            ]),
            html.Div([
                html.Label(t(loc, "NewAssessment", "reportingFiscalYear"), className="block text-sm font-medium text-gray-700 mb-2"),
                dropdown("na-fy", [], None, ""),
                html.Div(id="na-conflict"),
            ], id="na-fy-block", className="hidden"),
            html.Div(id="na-title"),
            html.Div([
                html.Label(t(loc, "NewAssessment", "departmentLabel"), htmlFor="na-dept", className=LABEL),
                dcc.Input(id="na-dept", type="text", placeholder=t(loc, "NewAssessment", "departmentPlaceholder"),
                          maxLength=C.FIELD_LIMITS["department"], className=INPUT),
            ]),
            html.Div([
                html.Label([t(loc, "NewAssessment", "descriptionLabel"), " ",
                            html.Span(t(loc, "NewAssessment", "descriptionOptional"), className="text-gray-600 font-normal")], htmlFor="na-desc", className=LABEL),
                dcc.Textarea(id="na-desc", rows=3, placeholder=t(loc, "NewAssessment", "descriptionPlaceholder"),
                             maxLength=C.FIELD_LIMITS["description"], className=INPUT.replace("appearance-none ", "") + " resize-none"),
            ]),
            html.Div(id="na-error"),
            html.Div([
                html.Button(t(loc, "NewAssessment", "create"), id="na-submit", n_clicks=0, disabled=True,
                            className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm"),
                link(t(loc, "NewAssessment", "cancel"), "assessments",
                     "px-5 py-2.5 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors text-sm text-center"),
            ], className="flex gap-3 pt-2"),
        ], className="space-y-5"),
    ], className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-lg p-8"),
        className="pt-28 flex items-start justify-center py-12 px-4")
    return app_shell(ctx, main)


@callback(Output("na-fw", "data"), Output("na-fw-buttons", "children"),
          Input({"type": "na-fw", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def _fw(clicks):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    kind = dctx.triggered_id["index"]
    return kind, _fw_buttons(current_locale(), kind)


@callback(Output("na-fy", "options"), Output("na-fy", "value"), Output("na-fy-hint", "children"), Output("na-fy-block", "className"),
          Input("na-country", "value"), prevent_initial_call=True)
def _country(name):
    c = find_country(name)
    if not c:
        return [], None, None, "hidden"
    loc = current_locale()
    opts = [{"label": fy, "value": fy} for fy in generate_fy_options(c)]
    hint = [icon("calendar", 11), t(loc, "NewAssessment", "fiscalYearHintLabel"), " ", html.Span(fy_period_description(c), className="font-medium")]
    return opts, current_fy_label(c), hint, ""


@callback(Output("na-title", "children"), Output("na-conflict", "children"), Output("na-submit", "disabled"),
          Input("na-country", "value"), Input("na-fy", "value"), Input("na-fw", "data"), Input("na-dept", "value"))
def _derive(country, fy, kind, dept):
    require_user()
    c = find_country(country)
    if not c or not fy:
        return None, None, True
    loc = current_locale()
    title = f"{c['name']} {fy_display(fy)}" + (" (PAG-FA)" if kind == "pagfa" else "")
    rows = get_db().query(f"SELECT fiscal_years FROM {C.T['assessments']} WHERE country = :c AND kind = :k", {"c": c["name"], "k": kind or "infragov"})
    conflict = any(fy in jload(r["fiscal_years"]) for r in rows)
    title_block = html.Div([
        html.Label(t(loc, "NewAssessment", "assessmentTitleLabel"), className=LABEL),
        html.Div([icon("lock", 12, "text-gray-500"), html.Span(title, className="truncate font-medium")],
                 className="flex items-center gap-2 px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-900"),
        html.P(t(loc, "NewAssessment", "autoTitleHint"), className="text-xs text-gray-600 mt-1"),
    ])
    warn = html.Div([icon("alert-triangle", 13, "mt-0.5"), html.P(t(loc, "NewAssessment", "conflictWarning", country=c["name"], year=fy), className="text-xs leading-relaxed")],
                    className="flex items-start gap-1.5 mt-2 text-amber-700") if conflict else None
    return title_block, warn, conflict or not (dept or "").strip()


@callback(Output("na-error", "children"), Output("url", "href", allow_duplicate=True),
          Input("na-submit", "n_clicks"),
          State("na-fw", "data"), State("na-country", "value"), State("na-fy", "value"), State("na-dept", "value"), State("na-desc", "value"),
          prevent_initial_call=True)
def _create(n, kind, country, fy, dept, desc):
    if not n:
        raise PreventUpdate
    user = require_user()
    try:
        aid = repository.create_assessment(user, kind=kind or "infragov", country=country or "", fiscal_year=fy or "",
                                           department=dept or "", description=desc or "")
    except Exception as exc:  # noqa: BLE001
        return alert(user_message(exc), "error"), no_update
    return None, href("dimensions", id=aid)

"""Assessment visualization — /?page=visualization&id=… (port of …/[id]/visualization/page.tsx)."""
from __future__ import annotations

from dash import Input, Output, State, callback, html

from services import repository
from utils.charts import indicator_bars
from utils.components import dropdown, empty, icon, legend, link
from utils.context import current_locale, require_user
from utils.i18n import t


def chart_card(loc, dim):
    rows = [{"label": m["code"], "question": m["question"], "score": (m.get("entry") or {}).get("score")} for m in dim["mbis"]]
    return html.Div([
        html.H2(f"D{dim['id']}: {dim['name']}", className="text-base font-semibold text-gray-800 mb-5"),
        indicator_bars(rows, loc, t(loc, "AssessmentVisualization", "noMaturityYet"), "viz-chart"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6")


def content(ctx, a: dict):
    loc = ctx.locale
    published = [d for d in a["dimensions"] if d["status"] == "Published"]
    body = []
    if not published:
        body.append(html.Div([
            icon("bar-chart-2", 40, "text-gray-300 mx-auto mb-4 block"),
            html.P(t(loc, "AssessmentVisualization", "emptyTitle"), className="text-gray-400 font-medium"),
            html.P(t(loc, "AssessmentVisualization", "emptyBody"), className="text-gray-300 text-sm mt-1"),
            link(t(loc, "AssessmentVisualization", "goToDimensions"), "dimensions", "inline-block mt-5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2 rounded-lg transition-colors", id=a["id"]),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center"))
    else:
        body += [
            html.Div([
                html.Label(t(loc, "AssessmentVisualization", "publishedDimensionLabel"), className="text-[10px] font-bold text-gray-400 uppercase tracking-wide shrink-0"),
                html.Div(dropdown("viz-dim", [{"label": f"D{d['id']} — {d['name']}", "value": d["id"]} for d in published], published[0]["id"]),
                         className="relative flex-1 min-w-[260px] max-w-md"),
                html.Span(t(loc, "AssessmentVisualization", "countLine", published=len(published), total=len(a["dimensions"])), className="text-xs text-gray-400"),
            ], className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 mb-4 flex items-center gap-3 flex-wrap"),
            html.Div(chart_card(loc, published[0]), id="viz-card"),
        ]
    return html.Div([
        html.Div(link([icon("arrow-left", 14), t(loc, "AssessmentVisualization", "back")], "dimensions",
                      "flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 transition-colors", id=a["id"]), className="flex items-center gap-3 mb-6"),
        html.Div([html.H1(t(loc, "AssessmentVisualization", "title"), className="text-3xl font-bold text-gray-900"),
                  html.P(a["title"], className="text-gray-500 text-sm mt-1")], className="mb-6"),
        html.Div([
            html.P(t(loc, "AssessmentVisualization", "summary"), className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3"),
            html.Div([
                html.Div([html.P(str(len(published)), className="text-2xl font-bold text-indigo-700"), html.P(t(loc, "AssessmentVisualization", "publishedDimensions"), className="text-xs text-gray-500 mt-0.5")],
                         className="bg-gray-50 rounded-lg p-3 text-center"),
                html.Div([html.P(str(len(a["dimensions"]) - len(published)), className="text-2xl font-bold text-green-600"), html.P(t(loc, "AssessmentVisualization", "draftDimensions"), className="text-xs text-gray-500 mt-0.5")],
                         className="bg-gray-50 rounded-lg p-3 text-center"),
            ], className="grid grid-cols-2 sm:grid-cols-4 gap-3"),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 mb-6"),
        legend(loc, t(loc, "AssessmentVisualization", "noData")),
        html.Div(body, **{"data-aid": a["id"]}, id="viz-root"),
    ], className="p-8")


@callback(Output("viz-card", "children"), Input("viz-dim", "value"), State("url", "search"), prevent_initial_call=True)
def _pick(dim_id, search):
    from urllib.parse import parse_qs

    user = require_user()
    loc = current_locale()
    aid = (parse_qs((search or "").lstrip("?")).get("id") or [""])[0]
    a = repository.get_assessment(user, aid, loc)
    dim = next(d for d in a["dimensions"] if d["id"] == dim_id and d["status"] == "Published")
    return chart_card(loc, dim)

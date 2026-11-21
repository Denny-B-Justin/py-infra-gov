"""Printable assessment report — /?page=report&id=… (port of …/[id]/report/page.tsx)."""
from __future__ import annotations

from datetime import datetime, timezone

from dash import html

from utils import framework as F
from utils.components import icon, link, score_badge
from utils.countries import fy_range_display


def layout(ctx, a: dict):
    loc = ctx.locale
    published = [d for d in a["dimensions"] if d["status"] == "Published"]
    fy = fy_range_display(a["fiscalYears"])
    now = datetime.now(timezone.utc)
    today = f"{now.day} {now.strftime('%b %Y')}"
    sections = []
    for d in published:
        sections.append(html.Section([
            html.Header([html.Span(f"{F.display_prefix(a['kind'])}{d['id']}", className="text-gray-500 font-medium text-sm w-8 shrink-0"),
                         html.H2(d["name"], className="text-gray-900 font-semibold text-sm")],
                        className="flex items-center gap-3 px-5 py-3 border-b border-gray-100"),
            html.Div(html.Table([
                html.Thead(html.Tr([html.Th("MBI", className="font-semibold py-1.5 w-14"), html.Th("Indicator", className="font-semibold py-1.5"),
                                    html.Th("Maturity", className="font-semibold py-1.5 w-36 text-right")], className="text-gray-500 text-left")),
                html.Tbody([html.Tr([html.Td(m["code"], className="py-2 text-gray-400 font-medium"), html.Td(m["question"], className="py-2 text-gray-700 pr-3"),
                                     html.Td(score_badge((m.get("entry") or {}).get("score"), loc), className="py-2 text-right")],
                                    className="border-t border-gray-100 align-top") for m in d["mbis"]]),
            ], className="w-full text-xs table-fixed"), className="px-5 pb-5 pt-2"),
        ], className="bg-white rounded-xl border border-gray-200 overflow-hidden pdf-card"))
    return html.Main([
        html.Div([
            link([icon("arrow-left", 14), "Back to assessment"], "dimensions", "inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800", id=a["id"]),
            html.Button([icon("printer", 14), "Print"], id="report-print", n_clicks=0,
                        className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"),
        ], className="flex items-center justify-between mb-5 print:hidden"),
        html.Div(html.Div([html.Span(f"InfraGov Assessment Tool · {'PAG-FA' if a['kind'] == 'pagfa' else 'InfraGov 2.0'}"),
                           html.Span(today, className="text-gray-500 font-normal normal-case tracking-normal")],
                          className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-gray-700"), className="hidden print:block pdf-header"),
        html.Header([
            html.Div([icon("file-text", 14), html.Span("Assessment report", className="text-xs font-bold uppercase tracking-wider")], className="flex items-center gap-2 mb-1 text-gray-500"),
            html.H1(a["title"], className="text-3xl font-bold text-gray-900"),
            html.P(" · ".join(x for x in (a["country"], fy, a.get("department")) if x), className="text-gray-500 text-sm mt-1"),
            html.P(f"{len(published)} of {len(a['dimensions'])} {'pillars' if a['kind'] == 'pagfa' else 'dimensions'} published", className="text-gray-400 text-xs mt-1"),
        ], className="mb-8"),
        html.Div("No dimensions have been published yet.", className="bg-white rounded-xl border border-gray-200 p-8 text-center text-sm text-gray-500") if not published
        else html.Div(sections, className="space-y-4"),
    ], className="px-8 py-6 max-w-4xl mx-auto w-full ig-autoprint")

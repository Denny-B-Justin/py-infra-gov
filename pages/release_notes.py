"""Release notes — /?page=release-notes (port of app/[locale]/revision-notes/page.tsx)."""
from __future__ import annotations

import constants as C
from dash import html

from pages import pages_constants as PC
from utils.components import icon, whitelist_markup
from utils.layout import public_footer, public_header


def layout(ctx):
    legend = [html.Span("Release types:", className="font-semibold text-gray-300")] + [
        html.Span([html.Span(t, className=f"inline-flex items-center text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full {cls}"),
                   html.Span(desc, className="text-gray-400")], className="inline-flex items-center gap-1.5")
        for t, (cls, desc) in PC.RELEASE_TYPE_BADGE.items()
    ]
    articles = []
    for i, r in enumerate(PC.releases()):
        cls, desc = PC.RELEASE_TYPE_BADGE.get(r["type"], PC.RELEASE_TYPE_BADGE["Minor"])
        articles.append(html.Article([
            html.Header([
                html.Div([
                    html.H2(f"v{r['version']}", className="text-lg font-bold text-white"),
                    html.Span(r["type"], title=desc, className=f"inline-flex items-center text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full {cls}"),
                    html.Span(r["date"], className="text-sm text-gray-400"),
                ], className="flex items-center gap-3 flex-wrap"),
                html.Span([icon("sparkles", 10), "Latest"], className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-indigo-300 bg-indigo-500/15 border border-indigo-400/30 px-2 py-0.5 rounded-full") if i == 0 else None,
            ], className="flex items-center justify-between gap-3 mb-4 pb-3 border-b border-white/10 flex-wrap"),
            html.Ul([html.Li([html.Span(className="mt-2 w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0", **{"aria-hidden": "true"}),
                              html.Span(whitelist_markup(e))], className="flex gap-3 text-sm text-gray-300 leading-relaxed")
                     for e in r["entries"]], className="space-y-3"),
        ]))
    return html.Div([
        public_header(ctx.user),
        html.Header([
            html.Div([icon("history", 16), html.Span("Revision notes", className="text-xs font-bold uppercase tracking-wider")],
                     className="flex items-center gap-2 mb-2 text-indigo-400"),
            html.H1("Revision Notes", className="text-3xl font-bold text-white mb-2"),
            html.P(["What's changed in the InfraGov Assessment Tool, in reverse-chronological order. Spotted something missing or have a feature request? Email ",
                    html.A(C.FEEDBACK_EMAIL, href=f"mailto:{C.FEEDBACK_EMAIL}", className="text-indigo-400 hover:text-indigo-300 font-medium"), "."],
                   className="text-gray-400 text-base leading-relaxed max-w-2xl"),
            html.Div(legend, className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-400"),
        ], className="px-8 pt-16 pb-6 max-w-6xl mx-auto w-full"),
        html.Main(html.Div(html.Div(articles, className="space-y-12"), className="max-w-3xl mx-auto px-8 py-10"),
                  className="border-t border-white/10 flex-1"),
        public_footer(),
    ], className="min-h-screen bg-[#0d1117] flex flex-col")

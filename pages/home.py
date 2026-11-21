"""Landing page — /?page=home (port of app/[locale]/page.tsx)."""
from __future__ import annotations

from dash import html

from pages import pages_constants as PC
from utils.components import asset, icon, link
from utils.layout import public_footer, public_header

FADE_GRID = {
    "backgroundImage": "linear-gradient(rgba(255,255,255,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.055) 1px, transparent 1px)",
    "backgroundSize": "60px 60px",
    "maskImage": "linear-gradient(to bottom, black 0%, black 30%, transparent 100%)",
    "WebkitMaskImage": "linear-gradient(to bottom, black 0%, black 30%, transparent 100%)",
}


def _cta(extra: str):
    return link([PC.CTA_LABEL, icon("arrow-up-right-solid", 20, "w-5 h-5")], "login",
                f"inline-flex items-center gap-3 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-[3px] transition-colors text-base {extra}")


def features():
    """Feature tabs — hover/focus switching is handled client-side (assets/app.js)."""
    rows = []
    for i, f in enumerate(PC.FEATURES):
        is_active = i == 0
        rows.append(html.Div([
            html.Span(f["num"], className="ig-feature-num text-sm font-mono font-bold mt-0.5 shrink-0 w-6 transition-colors duration-200 "
                      + ("text-indigo-400" if is_active else "text-gray-600")),
            html.Div(html.P(f["text"], className="ig-feature-text text-sm leading-relaxed transition-colors duration-200 "
                            + ("text-white" if is_active else "text-gray-400")), className="flex-1"),
        ], tabIndex=0, **{"data-feature": str(i)},
            className="ig-feature flex items-start gap-5 px-6 py-5 cursor-pointer border-l-2 transition-colors duration-200 "
            + ("border-t border-white/10 " if i > 0 else "")
            + ("border-l-indigo-400 bg-white/[0.06]" if is_active else "border-l-transparent hover:bg-white/[0.03]")))
    images = [html.Div(html.Img(src=asset(f["image"]), alt=f"InfraGov Assessment Tool — feature {f['num']}",
                                className="absolute inset-0 w-full h-full object-cover object-left-top"),
                       className="ig-feature-img absolute inset-0 transition-opacity duration-500 ease-in-out " + ("opacity-100" if i == 0 else "opacity-0"),
                       **{"data-feature-img": str(i)})
              for i, f in enumerate(PC.FEATURES)]
    return html.Div([html.Div(rows, className="w-1/2 flex flex-col"),
                     html.Div(images, className="w-1/2 relative rounded-xl overflow-hidden min-h-[320px]")],
                    className="ig-features flex gap-20 items-stretch")


def faq():
    """Accordion built on <details>; app.js keeps only one item open."""
    items = []
    for q, a in PC.FAQS:
        items.append(html.Details([
            html.Summary([html.Span(q, className="font-bold text-gray-900 text-base pr-8"),
                          icon("chevron-down", 20, "ig-chevron text-gray-500 transition-transform duration-200")],
                         className="w-full flex items-center justify-between py-5 text-left list-none cursor-pointer"),
            html.Div(a, className="pb-5 text-sm text-gray-600 leading-relaxed"),
        ], className="ig-accordion border-b border-gray-300"))
    return html.Div(items, className="border-t border-gray-300")


def layout(ctx):
    return html.Div([
        public_header(ctx.user),
        html.Section([
            html.Div(className="absolute inset-0 pointer-events-none", style=FADE_GRID, **{"aria-hidden": "true"}),
            html.Div([
                html.Div([
                    html.Span(PC.HERO_EYEBROW, className="inline-block bg-indigo-500/20 text-indigo-300 border border-indigo-400/30 text-xs font-semibold px-3 py-1 rounded-full mb-7 tracking-widest uppercase"),
                    html.H1(PC.HERO_TITLE, className="text-3xl md:text-4xl font-bold leading-tight mb-6 font-fira"),
                    html.P(PC.HERO_BODY, className="text-lg text-gray-300 mb-10 leading-relaxed"),
                    _cta("px-7 py-3.5 shadow-lg"),
                ], className="flex-1"),
                html.Div(html.Div(html.Video(src=asset("img/welcome-intro.mp4"), poster=asset("img/welcome-intro-poster.jpg"),
                                             controls=True, preload="metadata", className="w-full h-full object-cover"),
                                  className="relative aspect-video rounded-2xl overflow-hidden bg-black shadow-2xl"),
                         className="flex-1 shrink-0"),
            ], className="relative z-10 max-w-6xl mx-auto flex items-center gap-16"),
        ], className="relative overflow-hidden bg-[#111827] text-white pt-20 pb-24 px-6"),
        html.Section(html.Div([
            html.H2(PC.FEATURES_HEADING, className="text-2xl font-bold text-white mb-12 font-fira"),
            features(),
            html.Div(html.Img(src=asset("img/hero-infrastructure.jpg"), alt="Aerial view of infrastructure",
                              className="w-full h-96 object-cover object-top rounded-xl shadow-2xl"), className="mt-36 -mb-48 relative z-10"),
        ], className="max-w-6xl mx-auto"), id="about", className="pt-16 pb-0 px-6 bg-[#0d1117]"),
        html.Section(html.Div([
            html.H2(PC.FAQ_HEADING, className="text-2xl font-bold text-gray-900 mb-8 font-fira"),
            faq(),
        ], className="max-w-5xl mx-auto"), className="pt-72 pb-24 px-6 bg-gray-50 relative z-0"),
        html.Section([
            html.P(PC.SECOND_CTA_TEXT, className="text-gray-500 text-sm mb-6 max-w-md mx-auto"),
            _cta("px-8 py-4 shadow-md"),
        ], className="py-20 px-6 bg-white text-center"),
        public_footer(),
    ], className="min-h-screen flex flex-col bg-white")



"""About This Tool — /?page=about (port of app/[locale]/about/page.tsx)."""
from __future__ import annotations

import constants as C
from dash import html

from pages import pages_constants as PC
from utils import framework as F
from utils.components import asset, fmt, icon
from utils.layout import public_footer, public_header


def _card(blocks):
    out = []
    for b in blocks:
        if b[0] == "p":
            out.append(html.P(fmt(b[1])))
        elif b[0] == "ol":
            out.append(html.Ol([html.Li(fmt(x)) for x in b[1]], className="list-decimal list-outside ml-5 space-y-1.5 text-gray-300"))
        elif b[0] == "ul":
            out.append(html.Ul([html.Li(fmt(x)) for x in b[1]], className="list-disc list-outside ml-5 space-y-2"))
    return html.Div(out, className="text-sm text-gray-300 leading-relaxed space-y-3")


def _levels():
    cards = []
    for score, name, headline, desc in PC.ABOUT_LEVELS:
        fg = "#FFFFFF"
        cards.append(html.Article([
            html.Header([
                html.Span(str(score), className="inline-flex items-center justify-center w-9 h-9 rounded-full font-bold text-base",
                          style={"backgroundColor": "rgba(255,255,255,0.25)", "color": fg}),
                html.Div([html.H3(name, className="font-bold text-base leading-tight"),
                          html.P(headline, className="text-xs opacity-90 leading-snug mt-0.5")]),
            ], className="flex items-center gap-4 px-5 py-4", style={"backgroundColor": F.score_color(score), "color": fg}),
            html.Div(html.P(desc, className="text-sm text-gray-300 leading-relaxed"), className="px-5 py-4"),
        ], className="bg-white/[0.04] rounded-xl border border-white/10 overflow-hidden"))
    return html.Div(cards, className="space-y-4 mb-6")


def _section(sec: dict, i: int):
    body = [html.H2(sec["heading"], className="text-lg font-bold text-white mb-3"),
            html.P(fmt(sec["lead"], "font-semibold"), className="text-gray-400 text-sm leading-relaxed mb-5 max-w-2xl")]
    for b in sec["blocks"]:
        kind = b[0]
        if kind == "card":
            body.append(_card(b[1]))
        elif kind == "h3":
            body.append(html.Div(html.H3(b[2], className="text-base font-bold text-white mb-2"), id=b[1], className="mt-6 scroll-mt-24"))
        elif kind == "h2":
            body.append(html.H2(b[1], className="text-lg font-bold text-white mb-3"))
        elif kind == "levels":
            body.append(_levels())
        elif kind == "contact":
            a_cls = "text-indigo-400 hover:text-indigo-300 font-medium"
            body.append(html.Div([
                html.P("Spotted a bug, missing feature, or unclear copy? Have an idea for a new dimension or visualisation? Please get in touch."),
                html.P(["Email ", html.A(C.FEEDBACK_EMAIL, href=f"mailto:{C.FEEDBACK_EMAIL}", className=a_cls),
                        " with as much detail as you can — the page you were on, what you were trying to do, what you saw instead. Screenshots help a lot."]),
                html.P(["For broader PIM-PAM news and release notes, visit ",
                        html.A("pim-pam.net", href=C.PIM_PAM_URL, target="_blank", rel="noopener noreferrer", className=a_cls), "."]),
            ], className="text-sm text-gray-300 leading-relaxed space-y-3"))
    return html.Section(body, id=sec["id"], className="scroll-mt-24 " + ("mt-16 pt-10 border-t border-white/10" if i > 0 else ""))


def layout(ctx):
    active = ctx.params.get("section") or PC.ABOUT_SECTIONS[0]["id"]
    nav = [html.A([icon(s["icon"], 14, "ig-spy-icon transition-colors " + ("text-indigo-300" if s["id"] == active else "text-gray-500 group-hover:text-indigo-300")),
                   s["label"]], href=f"#{s['id']}", **{"data-spy": s["id"]},
                  className="ig-spy group flex items-center gap-2.5 py-1.5 text-sm text-left transition-colors "
                  + ("text-indigo-300 font-semibold" if s["id"] == active else "text-gray-300 hover:text-indigo-300"))
           for s in PC.ABOUT_SECTIONS]
    return html.Div([
        public_header(ctx.user),
        html.Header([
            html.Div([icon("book-open", 16), html.Span("About this tool", className="text-xs font-bold uppercase tracking-wider")],
                     className="flex items-center gap-2 mb-2 text-indigo-400"),
            html.H1(PC.ABOUT_INTRO_TITLE, className="text-3xl font-bold text-white mb-2"),
            html.P(PC.ABOUT_INTRO_BODY, className="text-gray-400 text-base leading-relaxed max-w-2xl"),
        ], className="px-8 pt-16 pb-6 max-w-6xl mx-auto w-full"),
        html.Main(html.Div(html.Div([
            html.Aside(html.Nav(nav, className="flex flex-col gap-0.5"), className="py-6 md:py-8 md:pr-6 md:sticky md:top-20 md:self-start"),
            html.Div(
                [html.Div(html.Video(src=asset("img/welcome-intro.mp4"), poster=asset("img/welcome-intro-poster.jpg"), controls=True,
                                     preload="metadata", className="w-full h-full object-cover"),
                          className="mb-10 relative aspect-video rounded-xl overflow-hidden bg-black border border-white/10")]
                + [_section(s, i) for i, s in enumerate(PC.ABOUT_SECTIONS)],
                className="min-w-0 py-6 md:py-8 md:pl-8 md:border-l md:border-white/10"),
        ], className="grid grid-cols-1 md:grid-cols-[240px_1fr] h-full"), className="max-w-6xl mx-auto px-8 h-full"),
            className="border-t border-white/10 flex-1"),
        public_footer(),
    ], className="min-h-screen bg-[#0d1117] flex flex-col ig-about")

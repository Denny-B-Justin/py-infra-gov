"""
Reusable design elements (badges, icons, buttons, modals, text formatting).

All class names are Tailwind utility classes copied from the original
components; `assets/style.css` is compiled from these files so the Dash app
renders with the same design tokens.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

import dash
from dash import dcc, html

from utils import framework as F

# ---------------------------------------------------------------- links


def href(page: str, **params: Any) -> str:
    """Relative URL for a page in the ?page=<name> scheme (prefix-aware)."""
    q = {"page": page}
    q.update({k: v for k, v in params.items() if v not in (None, "")})
    return dash.get_relative_path("/") + "?" + urlencode(q)


def asset(path: str) -> str:
    return dash.get_asset_url(path)


def link(children, page: str, className: str = "", new_tab: bool = False, el_id=None, **params):
    """Internal link. `params` become query parameters (e.g. id=<assessment>)."""
    url = href(page, **params)
    kw = {"id": el_id} if el_id else {}
    if new_tab:
        return html.A(children, href=url, target="_blank", rel="noopener noreferrer", className=className, **kw)
    return dcc.Link(children, href=url, className=className, **kw)


def ext_link(children, url: str, className: str = ""):
    return html.A(children, href=url, target="_blank", rel="noopener noreferrer", className=className)


# ---------------------------------------------------------------- icons


def icon(name: str, size: int = 16, className: str = "", **kw):
    """Lucide icon rendered as a CSS mask so it inherits `currentColor`."""
    return html.Span(
        className=f"ig-icon shrink-0 {className}".strip(),
        style={"width": f"{size}px", "height": f"{size}px", "--icon": f"url({asset('icons/' + name + '.svg')})"},
        **{"aria-hidden": "true"},
        **kw,
    )


def spinner(size: int = 16, className: str = ""):
    return icon("loader-2", size, f"animate-spin {className}")


# ---------------------------------------------------------------- text


_FMT = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])")


def fmt(text: str, strong_class: str = "font-semibold text-white") -> list:
    """Render the tiny safe markup used in pages_constants (no HTML)."""
    out, pos = [], 0
    for m in _FMT.finditer(text):
        if m.start() > pos:
            out.append(text[pos:m.start()])
        if m.group(1) is not None:
            out.append(html.Span(m.group(1), className=strong_class))
        elif m.group(2) is not None:
            out.append(html.Strong(m.group(2)))
        else:
            out.append(html.Em(m.group(3)))
        pos = m.end()
    out.append(text[pos:])
    return out


_TAGS = re.compile(r"<(strong|code)>(.*?)</\1>", re.S)


def whitelist_markup(text: str) -> list:
    """Render release-note entries: only <strong> and <code> survive."""
    out, pos = [], 0
    for m in _TAGS.finditer(text):
        if m.start() > pos:
            out.append(re.sub(r"<[^>]+>", "", text[pos:m.start()]))
        inner = re.sub(r"<[^>]+>", "", m.group(2))
        out.append(html.Strong(inner) if m.group(1) == "strong" else html.Code(inner, className="text-indigo-200"))
        pos = m.end()
    out.append(re.sub(r"<[^>]+>", "", text[pos:]))
    return out


def initials(name: str) -> str:
    return "".join(p[0] for p in (name or "").split() if p)[:2]


# ---------------------------------------------------------------- badges


def framework_chip(kind: str, className: str = ""):
    cls = ("bg-[#37b37f]/10 text-[#266F50] border-[#37b37f]/40" if kind == "pagfa"
           else "bg-indigo-50 text-indigo-700 border-indigo-200")
    return html.Span(F.framework_label(kind),
                     className=f"inline-block text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border {cls} {className}")


def score_badge(score: int | None, locale: str = "en", className: str = "", comparison: bool = False):
    if not score:
        return html.Span("—", className="text-gray-300")
    bg = F.comparison_color(score) if comparison else F.score_color(score)
    return html.Span(
        f"{score} {F.score_label(score, locale)}",
        className=f"inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold whitespace-nowrap {className}",
        style={"backgroundColor": bg, "color": "#FFFFFF"},
    )


def maturity_level_badge(level: str):
    if not level:
        return html.Span("—", className="text-gray-300")
    return html.Span(
        f"{F.maturity_to_score(level)} {level}",
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold whitespace-nowrap",
        style={"backgroundColor": F.MATURITY_COLORS[level], "color": F.MATURITY_TEXT_COLORS[level]},
    )


def status_pill(status: str, label: str):
    cls = {"Published": "bg-green-100 text-green-700", "Validated": "bg-blue-100 text-blue-700"}.get(status, "bg-gray-100 text-gray-700")
    return html.Span(
        [icon("check-circle", 11) if status == "Published" else None, label],
        className=f"inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold {cls}",
    )


def legend(locale: str, show_no_data: str | None = None):
    items = [
        html.Div([html.Div(className="w-3 h-3 rounded-full", style={"backgroundColor": F.score_color(s)}),
                  html.Span(f"{s} — {F.score_label(s, locale)}", className="text-xs text-gray-600 font-medium")],
                 className="flex items-center gap-1.5")
        for s in (1, 2, 3, 4)
    ]
    if show_no_data:
        items.append(html.Div([html.Div(className="w-3 h-3 rounded-full bg-gray-200"),
                               html.Span(show_no_data, className="text-xs text-gray-400")], className="flex items-center gap-1.5"))
    return html.Div(items, className="flex items-center gap-4 mb-6 flex-wrap")


def alert(message, kind: str = "error", className: str = ""):
    if not message:
        return None
    cls = {
        "error": "bg-red-50 border-red-200 text-red-700",
        "success": "bg-green-50 border-green-200 text-green-700",
        "warning": "bg-amber-50 border-amber-200 text-amber-800",
        "info": "bg-indigo-50 border-indigo-200 text-indigo-800",
    }[kind]
    ic = {"error": "alert-triangle", "success": "check-circle", "warning": "alert-triangle", "info": "info"}[kind]
    return html.Div([icon(ic, 14, "mt-0.5"), html.Div(message)],
                    className=f"px-4 py-3 border rounded-lg text-sm flex items-start gap-2 {cls} {className}", role="alert")


def modal(children, id_: str | dict | None = None, className: str = "max-w-lg", close_id=None):
    inner = html.Div(children, className=f"bg-white rounded-xl shadow-2xl w-full {className} max-h-[90vh] overflow-y-auto")
    kw = {"id": id_} if id_ else {}
    return html.Div(inner, className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4", role="dialog",
                    **{"aria-modal": "true"}, **kw)


def side_panel(title: str, subtitle: str | None, body, close_id: str, footer=None):
    return html.Div(
        html.Div([
            html.Div([
                html.Div([html.H3(title, className="font-semibold text-gray-800 text-sm flex items-center gap-2"),
                          html.P(subtitle, className="text-xs text-gray-500 mt-0.5") if subtitle else None]),
                html.Button(icon("x", 16), id=close_id, n_clicks=0, className="text-gray-400 hover:text-gray-600 p-1", **{"aria-label": "Close"}),
            ], className="flex items-start justify-between px-4 py-3 border-b border-gray-200"),
            html.Div(body, className="flex-1 overflow-y-auto"),
            footer,
        ], className="h-full bg-white border-l border-gray-200 shadow-xl flex flex-col"),
        className="fixed right-0 top-14 h-[calc(100vh-56px)] w-96 z-40",
    )


def empty(title: str, body: str = "", icon_name: str = "bar-chart-2"):
    return html.Div([
        icon(icon_name, 40, "text-gray-300 mx-auto mb-4 block"),
        html.P(title, className="text-gray-400 font-medium"),
        html.P(body, className="text-gray-300 text-sm mt-1") if body else None,
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center")


def dropdown(id_, options, value=None, placeholder: str = "", className: str = "", **kw):
    """Single-select dropdown styled like the original native <select>."""
    kw.setdefault("searchable", len(options) > 12)
    return dcc.Dropdown(id=id_, options=options, value=value, placeholder=placeholder, clearable=False,
                        className=f"ig-select {className}", **kw)

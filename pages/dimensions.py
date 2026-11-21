"""Dimensions list — /?page=dimensions&id=<assessment> (port of assessments/[id]/dimensions/page.tsx)."""
from __future__ import annotations

from dash import html

from pages import pages_constants as PC
from pages.shared_panels import panel_stores
from services import permissions as P
from utils.components import href, icon, initials, link
from utils.i18n import t


def content(ctx, a: dict):
    loc, user = ctx.locale, ctx.user
    is_owner = P.can_manage(user, a)
    th = "px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide"
    rows = []
    for i, d in enumerate(a["dimensions"]):
        total = len(d["mbis"])
        complete = sum(1 for m in d["mbis"] if m["status"] == "complete")
        all_done = complete == total
        published = d["status"] == "Published"
        can_view = d["canView"]
        my_role = P.role_for_dimension(user, a, d["id"])
        ind_bg = "bg-green-100 text-green-800" if all_done else ("bg-amber-50 text-amber-700" if complete else "bg-gray-100 text-gray-600")
        collabs = d["collaborators"]
        if not collabs:
            avatars = html.Span("—", className="text-xs text-gray-300")
        else:
            avatars = html.Div(
                [html.Div(initials(c["name"]), className="w-6 h-6 rounded-full bg-indigo-100 border-2 border-white flex items-center justify-center text-[10px] font-bold text-indigo-700")
                 for c in collabs[:4]]
                + ([html.Div(f"+{len(collabs) - 4}", className="w-6 h-6 rounded-full bg-gray-100 border-2 border-white flex items-center justify-center text-[10px] font-bold text-gray-500")] if len(collabs) > 4 else []),
                className="flex items-center -space-x-1.5", title=", ".join(f"{c['name']} ({c['role']})" for c in collabs))
        if published:
            status = html.Span([icon("check-circle", 11), t(loc, "DimensionsList", "statusPublished")],
                               className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700")
        elif all_done and is_owner:
            status = link(t(loc, "DimensionsList", "statusReady"), "publish",
                          "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700 hover:bg-indigo-200 transition-colors cursor-pointer",
                          id=a["id"], dim=d["id"])
        else:
            status = html.Span(t(loc, "DimensionsList", "statusDraft"), className="text-xs text-gray-400")
        name_cell = (link(d["name"], "dimension", "text-gray-800 font-medium hover:text-indigo-700 ig-row-link", id=a["id"], dim=d["id"])
                     if can_view else html.Span(d["name"], className="text-gray-800 font-medium"))
        rows.append(html.Tr([
            html.Td(str(d["id"]), className="px-4 py-3 text-gray-400 font-medium"),
            html.Td(name_cell, className="px-4 py-3"),
            html.Td(html.Span(f"{complete}/{total}", className=f"inline-block px-3 py-0.5 rounded-full text-xs font-bold {ind_bg}"), className="px-4 py-3 text-center"),
            html.Td(html.Span(P.role_label(my_role), className="text-xs font-semibold px-2 py-0.5 rounded-full " + PC.ROLE_BADGE.get(my_role, "bg-gray-100 text-gray-600")), className="px-4 py-3"),
            html.Td(avatars, className="px-4 py-3"),
            html.Td(status, className="px-4 py-3 text-center"),
            html.Td(icon("chevron-right", 14, "text-gray-300") if can_view else icon("lock", 12, "text-gray-400"), className="px-4 py-3"),
        ], className=("bg-white" if i % 2 == 0 else "bg-gray-50/50") + " border-b border-gray-100 transition-colors "
            + ("hover:bg-indigo-50/40 cursor-pointer ig-clickable-row" if can_view else "cursor-not-allowed opacity-60"),
            title=None if can_view else "Not shared with you — only people assigned to this dimension can open it",
            **({"data-href": href("dimension", id=a["id"], dim=d["id"])} if can_view else {})))
    return html.Div([
        html.Div([
            link([icon("arrow-left", 14), t(loc, "DimensionsList", "back")], "assessments",
                 "flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 transition-colors"),
            html.Div([
                html.Button([icon("users", 15), t(loc, "DimensionsList", "sharing")], id={"type": "panel-open", "index": "sharing"}, n_clicks=0,
                            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold transition-colors border bg-white text-gray-700 border-gray-200 hover:bg-gray-50"),
                link([icon("bar-chart-2", 15), t(loc, "DimensionsList", "visualization")], "visualization",
                     "flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors shadow-sm", id=a["id"]),
            ], className="flex items-center gap-2"),
        ], className="flex items-center justify-between mb-6"),
        html.H1(t(loc, "DimensionsList", "heading"), className="text-3xl font-bold text-gray-900 mb-1"),
        html.P(t(loc, "DimensionsList", "subheading"), className="text-sm text-gray-500 mb-6"),
        html.Div(html.Table([
            html.Thead(html.Tr([
                html.Th(t(loc, "DimensionsList", "colNum"), className=f"text-left {th} w-10"),
                html.Th(t(loc, "DimensionsList", "colDimension"), className=f"text-left {th}"),
                html.Th(t(loc, "DimensionsList", "colIndicators"), className=f"text-center {th} w-28"),
                html.Th(t(loc, "DimensionsList", "colYourRole"), className=f"text-left {th} w-36"),
                html.Th(t(loc, "DimensionsList", "colContributors"), className=f"text-left {th} w-36"),
                html.Th(t(loc, "DimensionsList", "colStatus"), className=f"text-center {th} w-28"),
                html.Th(className="w-10"),
            ]), className="bg-gray-50 border-b border-gray-200"),
            html.Tbody(rows),
        ], className="w-full text-sm"), className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm"),
        *panel_stores(a["id"]),
    ], className="p-8")

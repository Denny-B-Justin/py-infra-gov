"""Page chrome: public header/footer, authenticated navbar, assessment sidebar, footers."""
from __future__ import annotations

import constants as C
from dash import html

from pages import pages_constants as PC
from utils import framework as F
from utils.components import asset, ext_link, href, icon, initials, link
from utils.i18n import t

GRID_BG = {
    "backgroundImage": "linear-gradient(rgba(255,255,255,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.055) 1px, transparent 1px)",
    "backgroundSize": "60px 60px",
}


def logo(className: str = "h-11 w-auto"):
    return html.Img(src=asset("img/infragov-assessment-tool-logo.png"), alt="InfraGov Assessment Tool", className=className)


def pim_pam_badge(size: int = 24, part_cls: str = "text-gray-400 text-[10px] group-hover:text-gray-300",
                  name_cls: str = "text-white text-xs font-medium group-hover:text-gray-200"):
    return ext_link([
        html.Div(html.Img(src=asset("img/logo.png"), alt="Pim Pam", className="w-full h-full object-contain"),
                 className="shrink-0", style={"width": f"{size}px", "height": f"{size}px"}),
        html.Div([html.Span("Part of", className=f"{part_cls} transition-colors"),
                  html.Span("pim-pam.net", className=f"{name_cls} transition-colors")], className="flex flex-col leading-tight"),
    ], C.PIM_PAM_URL, "flex items-center gap-2 shrink-0 group")


def public_header(user: dict | None):
    logged = bool(user)
    return html.Header([
        link(logo(), "assessments" if logged else "home", "flex items-center hover:opacity-90 transition-opacity"),
        html.Nav([
            link("About", "about", "text-gray-300 hover:text-white text-sm transition-colors"),
            link("Release Notes", "release-notes", "text-gray-300 hover:text-white text-sm transition-colors"),
        ], className="ml-8 flex gap-6"),
        html.Div([
            link("Dashboard" if logged else "Sign in", "assessments" if logged else "login",
                 "text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-[3px] transition-colors font-medium"),
            html.Div(className="w-px h-5 bg-white/20"),
            pim_pam_badge(),
        ], className="ml-auto flex items-center gap-4"),
    ], className="bg-[#111827] text-white h-14 flex items-center px-6 sticky top-0 z-50 border-b border-white/10")


def public_footer():
    return html.Footer([
        html.Div(className="absolute inset-0 pointer-events-none", style=GRID_BG, **{"aria-hidden": "true"}),
        html.Div([
            html.Div([
                logo(),
                pim_pam_badge(32, "text-gray-500 text-[10px] group-hover:text-gray-400",
                              "text-gray-300 text-xs font-medium group-hover:text-white"),
            ], className="flex items-start justify-between mb-4"),
            html.P(PC.FOOTER_BLURB, className="text-sm text-gray-400 mb-8 max-w-md leading-relaxed"),
            html.Div([
                link("Start Assessment", "login", "hover:text-white transition-colors"),
                link("About", "about", "hover:text-white transition-colors"),
                link("Release Notes", "release-notes", "hover:text-white transition-colors"),
            ], className="flex flex-wrap gap-6 text-sm"),
            html.Div(PC.FOOTER_COPYRIGHT, className="mt-8 text-xs text-gray-500"),
        ], className="relative z-10 max-w-6xl mx-auto"),
    ], className="relative overflow-hidden bg-[#111827] text-gray-400 py-12 px-6 mt-auto")


def simple_header():
    """Logo-only header used by login / reset / join pages."""
    return html.Header(link(logo(), "home", "flex items-center hover:opacity-90 transition-opacity"),
                       className="bg-[#111827] text-white h-14 flex items-center px-6 shadow-lg")


def dashboard_footer(locale: str):
    return html.Footer([
        link(t(locale, "DashboardFooter", "aboutThisTool"), "about", "hover:text-gray-700 transition-colors", new_tab=True),
        ext_link(t(locale, "DashboardFooter", "partOfPimPam"), C.PIM_PAM_URL, "hover:text-gray-700 transition-colors"),
    ], className="px-8 py-4 mt-auto text-xs text-gray-500 flex items-center justify-between border-t border-gray-200 print:hidden")


def _menu_item(children, page: str, **params):
    return link(children, page, "flex items-center gap-2 px-4 py-2 text-sm hover:bg-gray-50 transition-colors", **params)


def navbar(ctx) -> html.Header:
    """Authenticated top navigation (port of components/Navbar.tsx)."""
    user, locale, page = ctx.user, ctx.locale, ctx.page
    on_assess = page in ("assessments", "new-assessment", "dimensions", "dimension", "publish", "visualization", "details", "report")
    on_viz = page in ("dashboard", "country")
    countries = ctx.nav_countries
    chip = None
    if ctx.assessment_kind:
        chip = html.Span(
            "PAG-FA" if ctx.assessment_kind == "pagfa" else "InfraGov",
            title="Framework for this assessment",
            className="ml-3 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider "
            + ("bg-[#37b37f]/20 text-[#9ce0bd] border border-[#37b37f]/40" if ctx.assessment_kind == "pagfa"
               else "bg-indigo-500/20 text-indigo-200 border border-indigo-500/40"),
        )

    def fw_row(fw: str):
        lst = countries.get(fw, [])
        flyout = [
            link(t(locale, "Navbar", "showAllCountries"), "dashboard",
                 "block px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 hover:text-indigo-700 transition-colors", kind=fw),
        ]
        if not lst:
            flyout.append(html.P("No countries have published data yet.", className="px-4 py-3 text-xs text-gray-500 text-center"))
        else:
            flyout.append(html.Div(
                [html.Div("1 country" if len(lst) == 1 else f"{len(lst)} countries",
                          className="px-4 py-1.5 text-[10px] font-bold text-gray-500 uppercase tracking-wide")]
                + [link(c, "country", "block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-indigo-700 transition-colors",
                        name=c.lower(), kind=fw) for c in lst],
                className="border-t border-gray-100 mt-1 pt-1"))
        return html.Div([
            html.Div([
                html.Span([
                    html.Span(className="inline-block w-2 h-2 rounded-full " + ("bg-[#37b37f]" if fw == "pagfa" else "bg-indigo-600")),
                    html.Span("PAG-FA" if fw == "pagfa" else "InfraGov", className="font-medium text-gray-800"),
                    html.Span(f"({len(lst)})", className="text-xs text-gray-400"),
                ], className="flex items-center gap-2"),
                icon("chevron-right", 12, "text-gray-400"),
            ], className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors group-hover:bg-gray-50", tabIndex=0),
            html.Div(flyout, className="hidden group-hover:block group-focus-within:block absolute left-full top-0 -mt-1 ml-1 bg-white text-gray-800 rounded-lg shadow-xl min-w-[220px] max-h-[420px] overflow-y-auto py-1 border border-gray-100 z-20"),
        ], className="relative group", role="menuitem")

    viz_menu = html.Details([
        html.Summary([icon("globe", 13), t(locale, "Navbar", "globalVisualization"), icon("chevron-down", 12, "text-gray-400")],
                     className="flex items-center gap-1.5 text-sm transition-colors list-none cursor-pointer "
                     + ("text-white font-medium" if on_viz else "text-gray-300 hover:text-white")),
        html.Div([fw_row("infragov"), fw_row("pagfa")], role="menu",
                 className="absolute left-0 top-10 bg-white text-gray-800 rounded-lg shadow-xl min-w-[200px] py-1 border border-gray-100 z-20"),
    ], className="relative ig-menu")

    lang_menu = html.Details([
        html.Summary([icon("languages", 14), locale, icon("chevron-down", 12, "text-gray-400")],
                     className="flex items-center gap-1.5 px-2 py-1.5 rounded text-xs text-gray-300 hover:text-white hover:bg-white/10 transition-colors uppercase tracking-wide font-semibold list-none cursor-pointer",
                     **{"aria-label": t(locale, "Navbar", "language")}),
        html.Div([html.Div(t(locale, "Navbar", "language"), className="px-4 py-2 border-b border-gray-100 text-[10px] font-bold text-gray-400 uppercase tracking-wide")]
                 + [html.Button([html.Span(C.LOCALE_LABELS[code]), html.Span(code, className="text-[10px] uppercase tracking-wide text-gray-400")],
                                id={"type": "nav-lang", "index": code}, n_clicks=0,
                                className="w-full flex items-center justify-between gap-3 px-4 py-2 text-sm hover:bg-gray-50 transition-colors "
                                + ("font-semibold text-indigo-700" if code == locale else "text-gray-700"))
                    for code in C.LOCALES],
                 className="absolute right-0 top-10 bg-white text-gray-800 rounded-lg shadow-xl min-w-[160px] py-1 border border-gray-100 z-20"),
    ], className="relative ig-menu")

    user_menu = html.Details([
        html.Summary([
            html.Div(initials(user.get("name", "")) or "U", className="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center text-xs font-semibold"),
            icon("chevron-down", 14, "text-gray-400"),
        ], className="flex items-center gap-2 p-1.5 rounded-full hover:bg-white/10 transition-colors list-none cursor-pointer"),
        html.Div([
            html.Div([html.P(user.get("name"), className="text-sm font-semibold"),
                      html.P(user.get("email"), className="text-xs text-gray-500 truncate")], className="px-4 py-3 border-b border-gray-100"),
            _menu_item([icon("user", 14, "text-gray-400"), t(locale, "Navbar", "profile")], "account"),
            _menu_item([icon("settings", 14, "text-gray-400"), t(locale, "Navbar", "accountSettings")], "account", tab="security"),
            html.Div(html.Button([icon("log-out", 14), t(locale, "Navbar", "signOut")], id="nav-logout", n_clicks=0,
                                 className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-gray-50 text-red-600 transition-colors"),
                     className="border-t border-gray-100 mt-1 pt-1"),
        ], className="absolute right-0 top-10 bg-white text-gray-800 rounded-lg shadow-xl w-56 py-1 border border-gray-100 z-20"),
    ], className="relative ig-menu")

    nav_links = [
        link(t(locale, "Navbar", "assessments"), "assessments",
             "text-sm transition-colors " + ("text-white font-medium" if on_assess else "text-gray-300 hover:text-white")),
        viz_menu,
        link(t(locale, "Navbar", "aboutThisTool"), "about", "text-sm transition-colors text-gray-300 hover:text-white", new_tab=True),
        link(t(locale, "Navbar", "revisionNotes"), "release-notes", "text-sm transition-colors text-gray-300 hover:text-white", new_tab=True),
    ]
    if user.get("role") == C.ROLE_ADMIN:
        nav_links.append(link("Admin", "admin", "text-sm transition-colors " + ("text-white font-medium" if page == "admin" else "text-gray-300 hover:text-white")))

    return html.Header([
        html.Div([
            link(logo(), "assessments", "flex items-center hover:opacity-90 transition-opacity"),
            chip,
            html.Nav(nav_links, className="ml-8 flex gap-6 items-center"),
        ], className="flex items-center gap-2 flex-1"),
        html.Div([
            lang_menu,
            html.Button(icon("help-circle", 18), id="nav-help", n_clicks=0, className="p-2 text-gray-300 hover:text-white transition-colors",
                        **{"aria-label": "Open tutorial"}),
            html.Div(ctx.bell, id="nav-bell"),
            user_menu,
        ], className="flex items-center gap-3"),
    ], className="bg-[#111827] text-white h-14 flex items-center px-6 fixed top-0 left-0 right-0 z-50 shadow-lg print:hidden")


def tutorial_modal(open_: bool):
    if not open_:
        return None
    return html.Div(html.Div([
        html.Button(icon("x", 16), id="tutorial-close-x", n_clicks=0, **{"aria-label": "Close"},
                    className="absolute top-3 right-3 z-10 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 text-white flex items-center justify-center transition-colors"),
        html.Div(html.Video(src=asset("img/welcome-intro.mp4"), poster=asset("img/welcome-intro-poster.jpg"), controls=True,
                            preload="metadata", className="w-full h-full object-cover"), className="relative aspect-video bg-black"),
        html.Div([
            html.H2(PC.TUTORIAL_TITLE, className="text-xl font-bold text-gray-900 mb-3 leading-tight"),
            html.P(PC.TUTORIAL_BODY, className="text-sm text-gray-700 leading-relaxed mb-4"),
            link(["Learn more about this tool", icon("arrow-right", 14)], "about",
                 "inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors", new_tab=True),
        ], className="p-6"),
        html.Div(html.Button("Got it, let's go", id="tutorial-close", n_clicks=0,
                             className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"),
                 className="px-6 pb-6 flex justify-end"),
    ], className="relative bg-white rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden"),
        className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4", role="dialog",
        **{"aria-modal": "true", "aria-label": "Welcome to InfraGov"})


def sidebar(ctx, a: dict, can_delete: bool):
    locale, page = ctx.locale, ctx.page
    items = [
        (t(locale, "AssessmentSidebar", "dimensions"), "dimensions", "layout-grid", ("dimensions", "dimension", "publish")),
        (t(locale, "AssessmentSidebar", "visualization"), "visualization", "bar-chart-2", ("visualization",)),
        (t(locale, "AssessmentSidebar", "details"), "details", "settings", ("details",)),
    ]
    nav = []
    for label, pg, ic, active_pages in items:
        active = page in active_pages
        nav.append(link([icon(ic, 16, "text-indigo-600" if active else "text-gray-400"), label], pg,
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 text-sm font-medium transition-colors "
                        + ("bg-indigo-50 text-indigo-700" if active else "text-gray-600 hover:bg-gray-50 hover:text-gray-900"), id=a["id"]))
    return html.Aside([
        html.Div([html.P(t(locale, "AssessmentSidebar", "assessment"), className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1"),
                  html.P(a.get("title") or t(locale, "AssessmentSidebar", "loading"), className="text-sm font-semibold text-gray-800 leading-snug")],
                 className="px-4 mb-5"),
        html.Nav(nav, className="flex-1 px-2"),
        html.Div(html.Button([icon("trash-2", 14), t(locale, "AssessmentSidebar", "deleteAssessment")], id={"type": "del-open", "index": "sidebar"}, n_clicks=0,
                             className="flex items-center gap-2 text-red-500 hover:text-red-700 text-sm transition-colors"),
                 className="px-4 mt-4 border-t border-gray-100 pt-4") if can_delete else None,
    ], className="w-52 min-h-screen bg-white border-r border-gray-200 fixed top-14 left-0 flex flex-col pt-5 pb-6 print:hidden")


def app_shell(ctx, content, footer: bool = True):
    """Navbar + content for top-level authenticated pages."""
    return html.Div([navbar(ctx), content, dashboard_footer(ctx.locale) if footer else None],
                    className="min-h-screen flex flex-col bg-gray-100")


def assessment_shell(ctx, a: dict, content, can_delete: bool):
    return html.Div([
        navbar(ctx),
        sidebar(ctx, a, can_delete),
        html.Div([content, dashboard_footer(ctx.locale)], className="ml-52 pt-28 flex-1 flex flex-col print:ml-0 print:pt-0"),
    ], className="min-h-screen flex flex-col bg-gray-100", **{"data-framework": a.get("kind", "infragov")})

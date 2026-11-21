"""
pages/pages_constants.py — page-level content and UI constants.

Copy, labels, colour maps and route names used by the page modules. Copy is
taken verbatim from the original Next.js pages so the Dash app reads the
same. Inline emphasis uses a tiny safe markup rendered by
`utils.components.fmt` (never raw HTML):
    **text**  → white/semibold highlight (About page) or bold elsewhere
    __text__  → <strong>
    _text_    → <em>
"""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------- routes
# Every page is addressed as /?page=<name>. Extra parameters are listed so the
# router can validate them (anything else in the query string is ignored).
PAGE_HOME = "home"
PAGES = {
    # name               : (requires_login, admin_only, allowed params)
    "home":              (False, False, ()),
    "about":             (False, False, ("section",)),
    "release-notes":     (False, False, ()),
    "login":             (False, False, ("token", "next")),
    "forgot-password":   (False, False, ()),
    "reset-password":    (False, False, ("token",)),
    "join":              (True,  False, ("token",)),
    "assessments":       (True,  False, ()),
    "new-assessment":    (True,  False, ("kind",)),
    "dimensions":        (True,  False, ("id",)),
    "dimension":         (True,  False, ("id", "dim", "mbi")),
    "publish":           (True,  False, ("id", "dim")),
    "visualization":     (True,  False, ("id",)),
    "details":           (True,  False, ("id", "tab")),
    "report":            (True,  False, ("id",)),
    "dashboard":         (True,  False, ("kind",)),
    "country":           (True,  False, ("name", "kind")),
    "account":           (True,  False, ("tab",)),
    "admin":             (True,  True,  ()),
}
PUBLIC_ONLY_PAGES = ("login", "forgot-password")  # signed-in users are sent on

# ---------------------------------------------------------------- colours
ROLE_COLORS = {  # solid role chips on assessment cards
    "Admin": "bg-purple-500", "Owner": "bg-green-500", "Contributor": "bg-orange-400",
    "Reviewer": "bg-blue-400", "Viewer": "bg-gray-400",
}
ROLE_BADGE = {  # soft role pills
    "Admin": "bg-purple-100 text-purple-700", "Owner": "bg-green-100 text-green-700",
    "Contributor": "bg-orange-100 text-orange-700", "Reviewer": "bg-blue-100 text-blue-700",
    "Viewer": "bg-gray-100 text-gray-600",
}
ROLE_BADGE_BORDERED = {  # admin users list
    "Admin": "bg-purple-100 text-purple-800 border border-purple-200",
    "Owner": "bg-green-100 text-green-800 border border-green-200",
    "Contributor": "bg-orange-100 text-orange-800 border border-orange-200",
    "Reviewer": "bg-blue-100 text-blue-800 border border-blue-200",
    "Viewer": "bg-gray-100 text-gray-700 border border-gray-200",
}
ROLE_DESCRIPTIONS = {
    "Contributor": "Can enter and edit MBI data, comment, view all results",
    "Reviewer": "Can view and comment but cannot edit",
    "Viewer": "Can view results but cannot comment or edit",
}
FIELD_LABELS = {
    "keyRespondents": "Key Respondents", "dataSource": "Data Source", "resultSummary": "Result Summary",
    "resultDetail": "Result Detail", "maturityBenchmark": "Maturity Level", "files": "Attachments",
}

# ---------------------------------------------------------------- landing page
HERO_EYEBROW = "InfraGov Assessment Tool"
HERO_TITLE = "Complete, review and disseminate InfraGov 2.0 benchmarking — across 16 dimensions and 119 indicators"
HERO_BODY = ("The InfraGov Assessment Tool lets country teams self-assess infrastructure governance against the "
             "InfraGov 2.0 framework, module by module and share validated results once review and quality control are complete.")
CTA_LABEL = "Start your assessment"
FEATURES_HEADING = "Key functionality of the InfraGov Assessment Tool:"
FEATURES = [
    {"num": "01", "text": "Assess one, several, or all 16 InfraGov 2.0 dimensions — rated Incipient to Advanced", "image": "img/dimensions.png"},
    {"num": "02", "text": "Run a specialized assessment, such as a PAG-FA (Public Asset Governance Functional Assessment)", "image": "img/pag.png"},
    {"num": "03", "text": "Save, resume, and version each assessment by its cut-off date", "image": "img/save.png"},
    {"num": "04", "text": "Work as a team with flexible read and write permissions", "image": "img/permissions.png"},
    {"num": "05", "text": "Complete review and quality control, then publish a public version", "image": "img/publish.png"},
]
FAQ_HEADING = "Frequently asked questions"
FAQS = [
    ("What does the InfraGov Assessment Tool do?",
     "The InfraGov Assessment Tool on pim-pam.net allows country users to complete, review, and disseminate InfraGov 2.0 benchmarking. You assess infrastructure governance against the framework's 119 maturity indicators, organised across 16 dimensions, rating each on a four-level maturity scale. For any given year you can complete one, several, or all sixteen dimensions, or run a specialized assessment such as a PAG Functional Assessment. Results are visualised by dimension, module by module."),
    ("Who is the CBD application intended for?",
     "It is built for whoever the working team includes — Bank staff, consultants and firms, and country counterparts. A versatile read- and write-permissioning system lets teams configure who can view, edit, and review, so different contributors can work on the same assessment in the way that suits them."),
    ("What kind of data does the application use?",
     "The assessment is built on evidence you provide for each indicator: the key respondent, the data source, a result summary, optional supporting detail, and a maturity benchmark. The tool derives a maturity level from the benchmark you assign. Each completed assessment is anchored to a cut-off date that captures the latest formal policy changes and data — for example, the PAG Functional Assessment for Serbia captures data through March 2026 and is termed InfraGov 2.0 PAG-FA 2026."),
    ("How can I use it in my policy work?",
     "The dashboard gives a single-country view of maturity across every dimension you've assessed — a practical working interface for identifying strengths, gaps, and reform priorities. Once the team has completed the relevant reviews and quality control, a public version can be provided, allowing validated benchmarks to be compared across countries while work in progress stays private."),
    ("Do I need technical skills to use it?",
     "No. Each indicator comes with its definition; you record the supporting evidence and select a maturity level from four clear options, and the tool handles the calculation and visualisation. You can save your work, resume later, and manage everything through the team's permission settings."),
]
SECOND_CTA_TEXT = "Ready to begin? Sign in to access the full benchmarking tool."
FOOTER_BLURB = "Complete, review and disseminate InfraGov 2.0 benchmarking across 16 dimensions and 119 indicators."
FOOTER_COPYRIGHT = "© 2026 InfraGov Assessment Tool. All rights reserved."

# ---------------------------------------------------------------- tutorial
TUTORIAL_TITLE = "Welcome to the InfraGov Assessment Tool"
TUTORIAL_BODY = ("Benchmark your public investment management against InfraGov 2.0, a framework of 16 dimensions, each "
                 "scored through a set of indicators. Select the dimensions relevant to your assessment and publish your "
                 "results to compare with other regions.")

# ---------------------------------------------------------------- about page
ABOUT_LEVELS = [
    (1, "Incipient", "The earliest stage of development.",
     "The country has recognised the need to act in this area, but systematic processes are not yet in place. Activities tend to be ad-hoc, fragmented, or dependent on individuals. Capacity is limited and outcomes are difficult to predict. Incipient is not a failure — it is a starting point that highlights where attention is most needed."),
    (2, "Nascent", "Foundational work is underway.",
     "Basic structures, policies, or processes are emerging. Some elements of good practice are visible, but application is inconsistent across institutions or projects. Capacity is growing, though gaps remain in coverage, depth, or institutional reach."),
    (3, "Emerging", "Consistent processes and growing capacity.",
     "Established procedures are applied with reasonable consistency. Most elements of good practice are in place and outcomes are generally positive, though gaps remain — typically in coverage of less-prominent projects, in depth of analysis, or in the quality of supporting data. The country is on a credible trajectory toward Advanced."),
    (4, "Advanced", "At the leading edge of practice.",
     "Systems are fully developed, consistently applied, and routinely reviewed for improvement. The country exhibits leading practice across the indicator and would serve as a useful benchmark for peers in the region or globally."),
]

# Each section: id, label, icon, heading, lead, blocks. A block is one of
#   ("p", text) | ("ol", [items]) | ("ul", [items]) | ("h3", id, title) | ("levels",) | ("h2", text) | ("contact",)
ABOUT_SECTIONS = [
    {"id": "overview", "label": "Overview", "icon": "compass", "heading": "What this tool is for",
     "lead": "The InfraGov Assessment Tool is a structured benchmarking workspace for the governance of public investment management (PIM). Teams in ministries of finance, planning agencies, and partner institutions use it to assess where their country sits on the InfraGov 2.0 framework, build an evidence base behind each indicator, and publish results that can be compared across countries.",
     "blocks": [("card", [
         ("p", "An assessment covers **16 dimensions** of PIM governance and **119 indicators** within them. Each indicator is benchmarked at one of four maturity levels and supported by a short evidence record."),
         ("p", "Work is done in _Draft_ with role-based collaboration. When the team is ready, a dimension is _Published_ by the assessment Owner — at which point it appears on the public global dashboard for cross-country comparison and can be downloaded by anyone."),
         ("p", "The other tabs walk through how each part of the tool fits together. Start anywhere; nothing assumes you've read the previous tab."),
     ])]},
    {"id": "frameworks", "label": "Frameworks", "icon": "layers", "heading": "Which framework to assess against",
     "lead": "The Assessment Tool supports two complementary maturity-assessment frameworks. Pick one at the start of every new assessment — the choice shapes which dimensions / pillars and indicators the assessment is scored against. The two frameworks can be run independently for the same country in the same year.",
     "blocks": [
         ("h3", "frameworks-infragov", "InfraGov 2.0"),
         ("card", [
             ("p", "__16 dimensions__ grouped into Core PIM systems, Cross-cutting “3Is”, and Special Agendas (CAPSS), spanning the full project lifecycle from strategic guidance and preliminary screening through to operations and ex post review."),
             ("p", "Used to benchmark the maturity of a country's Public Investment Management (PIM) systems against international good practice. Each indicator is scored on the four-tier Incipient → Nascent → Emerging → Advanced scale."),
             ("p", "InfraGov 2.0 is the successor to the original InfraGov diagnostic and is the default framework for new country assessments. Run this when the question is “how well does this country plan, appraise, deliver, and learn from infrastructure projects?”"),
         ]),
         ("h3", "frameworks-pagfa", "Public Asset Governance Functional Assessment (PAG-FA)"),
         ("card", [
             ("p", "__8 pillars__ and around 40 indicators covering the governance of public assets across their full lifecycle: accounting and valuation, cadastres and registries, strategic planning and resourcing, efficiency and revenue mobilisation, accountability and controls, digital government, climate resilience, and capacity and skills."),
             ("p", "Used to benchmark how well a country identifies, records, maintains, and gets value from the public assets it already owns — land, buildings, infrastructure, and the cadastral and accounting systems underpinning them. Same Incipient → Advanced maturity scale as InfraGov 2.0."),
             ("p", "Run this when the question is “how well does this country govern the public assets it already has, regardless of how they were originally procured?” A country can hold one InfraGov 2.0 and one PAG-FA assessment for the same fiscal year — they answer different questions."),
         ]),
     ]},
    {"id": "maturity", "label": "Maturity levels", "icon": "layers", "heading": "The four maturity levels",
     "lead": "The ladder describes a journey of progress, not a pass/fail judgment. Each level captures both the practices in place and the institutional capacity behind them. The same definitions apply across every dimension and indicator — what varies is the specific evidence that justifies a given level.",
     "blocks": [("levels",), ("h2", "Why an ordinal ladder, not a score"), ("card", [
         ("p", "The four-step ladder is deliberately ordinal — it tells you where a country sits in a sequence of development stages, not how many points it has earned. A move from Nascent to Emerging is a meaningful institutional milestone; an arithmetic difference of “one point” is not."),
         ("p", "Numerical scores derive from the labels for visualisation and comparison only. When the dashboards aggregate them they do so to support comparison, not to produce a definitive ranking — numerical averages should be read as a rough centre-of-gravity for the underlying labels."),
     ])]},
    {"id": "assessments", "label": "Assessments", "icon": "clipboard-list", "heading": "Creating an assessment",
     "lead": "A new assessment is anchored on one country and one __reporting fiscal year__. The platform derives the rest — title, period window — automatically so each assessment is unambiguous.",
     "blocks": [("card", [
         ("p", "**One assessment per country per fiscal year.** The system blocks creating a second assessment for the same country covering the same year."),
         ("p", "**Quantitative indicators** require comparable data over time. When the assessment will report on quantitative indicators (e.g. “What share of projects undergo independent review?”), the period automatically expands to a three-fiscal-year window ending in the selected year — so a 2026 anchor reports as 2024–2026 instead of just 2026."),
         ("p", "**The title is generated** as “Country InfraGov Assessment · Period” and is shown read-only on the form. It also appears on the assessments list and details pages."),
     ])]},
    {"id": "dimensions", "label": "Dimensions & indicators", "icon": "layout-grid", "heading": "Working through indicators",
     "lead": "Each of the 16 dimensions contains a handful of indicators (MBIs). Indicator text follows a __Statement: question__ format — the statement is the area being benchmarked, the question guides what evidence to capture.",
     "blocks": [("card", [
         ("p", "Every indicator has five fields:"),
         ("ol", [
             "**Key Respondents** — the people or roles who provided the information. Reusable across all assessments for the country.",
             "**Data Source** — the document, report, or evidence backing the entry. Supports file attachments.",
             "**Results Summary** — a short public-facing summary (max 200 chars). Becomes visible on the global dashboard.",
             "**Maturity Benchmark** — pick the level (Incipient through Advanced) that best describes current practice.",
             "**Result Detail** — internal-only notes, analysis, and supporting evidence. Hidden from Reviewers and never published.",
         ]),
         ("p", "Save data on any indicator at any time — work is autosaved into Draft until the dimension is published."),
     ])]},
    {"id": "publishing", "label": "Publishing", "icon": "globe", "heading": "Going from Draft to Published",
     "lead": "Each dimension is published independently. Once every indicator in a dimension is complete, the assessment Owner can publish it. Drafts stay private; Published dimensions appear on the global dashboard for everyone with an account.",
     "blocks": [("card", [
         ("p", "**Owner-only.** Publishing and unpublishing are restricted to the assessment Owner (or a platform Admin). Contributors and Reviewers can't flip the state."),
         ("p", "**Locked when Published.** A published dimension is read-only. To revise answers, the Owner must Unpublish first — which moves the dimension back to Draft and reopens the form. The data temporarily disappears from the public dashboard until republished."),
         ("p", "**What goes public:** Fields 1–3 (Key Respondents, Data Source, Results Summary) plus the maturity level. Field 4 (Result Detail) is always private to the assessment team."),
         ("p", "**Summary view.** Once a dimension is complete, the form is replaced with a clean read-only summary table. The same summary is used for both the prepare-to-publish review and the post-publication view."),
     ])]},
    {"id": "roles", "label": "Roles & permissions", "icon": "users", "heading": "Who can do what",
     "lead": "Roles are set per dimension, so a single user can be a Contributor on one dimension and a Reviewer on another in the same assessment. The assessment Owner controls assignments.",
     "blocks": [("card", [("ul", [
         "**Admin** — platform-level role. Sees and can manage every assessment.",
         "**Owner** — the user who created the assessment. Manages collaborators, edits any dimension, and is the only role that can publish or unpublish.",
         "**Contributor** — can edit indicators in the dimensions they're assigned to, including the private Field 4.",
         "**Reviewer** — read-only access plus the ability to leave comments. Cannot edit indicator data and cannot see Field 4 (Result Detail).",
         "**Viewer** — default role for any team member who hasn't been explicitly assigned. Read-only, no comments.",
     ])])]},
    {"id": "comparing", "label": "Comparing countries", "icon": "scale", "heading": "Reading the dashboards",
     "lead": "The Global Visualization page lists countries that have published dimensions and lets you focus on a specific indicator across them. Clicking through to a country opens its profile — every published dimension expanded by default, with an optional side-by-side comparison.",
     "blocks": [("card", [("ul", [
         "**Most recent wins.** When a country has multiple assessments, the dashboards always display the most recently updated published data per dimension.",
         "**Source FY is shown.** Every score on the country page and the global chart is labelled with the fiscal year it was drawn from, so you can see at a glance whether you're comparing like for like.",
         "**Text or Chart.** On the country page, switch between the table view (full indicator text + maturity badges) and the bar-chart view. Both apply to every dimension at once.",
         "**Comparison gaps** — when the comparison country hasn't published a particular dimension, an amber notice flags it explicitly and the comparison column / series is dropped for that dimension so you never see implicit zeros.",
         "**Colour cues** on badges and bars follow the maturity ladder — blue (Incipient) through teal toward green (Advanced). Colour conveys position, not a verdict.",
     ])])]},
    {"id": "downloads", "label": "Downloading data", "icon": "download", "heading": "Exporting a country profile",
     "lead": "The country page has a small _Download data_ cluster at the top right with two icons — one for PDF, one for Excel-compatible CSV.",
     "blocks": [("card", [
         ("p", "**PDF.** Opens the browser's native print dialog — pick “Save as PDF” for a file. The navbar, controls, and download buttons are hidden from the print so the resulting document shows only the country's data: header, every dimension's body, and any comparison-gap notices."),
         ("p", "**CSV.** One row per indicator across every published dimension, with the home country's score + maturity level. When a comparison country is selected, two more columns hold their score and level (“N/A” for dimensions the comparison hasn't published). The file carries a UTF-8 BOM so Excel preserves accented characters cleanly."),
         ("p", "Whatever view you have selected (Text or Chart) is what gets included in the PDF, and whatever comparison is selected is what goes into both files."),
     ])]},
    {"id": "feedback", "label": "Feedback", "icon": "message-square", "heading": "Giving feedback",
     "lead": "The tool is under active development — feedback from real assessment teams is what drives improvements.",
     "blocks": [("contact",)]},
]
ABOUT_INTRO_TITLE = "About This Tool"
ABOUT_INTRO_BODY = ("A short guide to the InfraGov Assessment Tool — how assessments are set up, what the maturity ladder "
                    "means, how publishing works, and how to read the comparison views.")

# ---------------------------------------------------------------- release notes
RELEASE_TYPE_BADGE = {
    "Major": ("bg-indigo-500/15 text-indigo-300 border border-indigo-400/30", "Significant updates to the platform"),
    "Minor": ("bg-sky-500/15 text-sky-300 border border-sky-400/30", "Smaller UI/UX changes"),
    "Patch": ("bg-emerald-500/15 text-emerald-300 border border-emerald-400/30", "Focused bug fixes"),
    "Operational": ("bg-amber-500/15 text-amber-300 border border-amber-400/30", "Pre-release / testing milestone"),
}


def releases() -> list[dict]:
    """Release notes extracted verbatim from app/[locale]/revision-notes/page.tsx.
    Entries contain only <strong>/<code> tags, rendered by a whitelist parser."""
    with open(_DATA / "releases.json", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- misc copy
ACCOUNT_NOTIFICATION_ITEMS = [
    ("emailNotifications", "Email notifications", "Master toggle for all email notifications"),
    ("inviteNotifications", "Team invitations", "Get notified when you're invited to an assessment"),
    ("publicationNotifications", "Publication events", "Get notified when a dimension is published or unpublished"),
    ("weeklyDigest", "Weekly activity digest", "Summary of assessment activity every Monday"),
]
DOC_ACCEPT = ".pdf,.docx,.xlsx,.xls,.csv"

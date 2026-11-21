"""Country fiscal-year configuration (port of lib/countries.ts)."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@lru_cache(maxsize=1)
def countries() -> list[dict]:
    with open(_DATA / "countries.json", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def profile_countries() -> list[str]:
    """Shorter list used by the Account → Profile form in the original app."""
    with open(_DATA / "account_countries.json", encoding="utf-8") as fh:
        return json.load(fh)


def country_names() -> list[str]:
    return [c["name"] for c in countries()]


def find_country(name: str | None) -> dict | None:
    for c in countries():
        if c["name"] == name:
            return c
    return None


def fy_period_description(c: dict) -> str:
    if c["fyLabelStyle"] == "single":
        return "1 Jan – 31 Dec"
    sm = MONTHS[c["fyStartMonth"] - 1]
    em = MONTHS[(c["fyStartMonth"] - 2 + 12) % 12]
    if c["fyStartDay"] > 1:
        return f"{c['fyStartDay']} {sm} – {em}"
    return f"{sm} – {em}"


def fy_label(c: dict, base_year: int) -> str:
    if c["fyLabelStyle"] == "single":
        return str(base_year)
    return f"{str(base_year)[-2:]}/{str(base_year + 1)[-2:]}"


def current_fy_base_year(c: dict, today: date | None = None) -> int:
    today = today or date.today()
    if c["fyLabelStyle"] == "single":
        return today.year
    started = today.month > c["fyStartMonth"] or (today.month == c["fyStartMonth"] and today.day >= c["fyStartDay"])
    return today.year if started else today.year - 1


def current_fy_label(c: dict) -> str:
    return fy_label(c, current_fy_base_year(c))


def generate_fy_options(c: dict, count: int = 12) -> list[str]:
    base = current_fy_base_year(c)
    return [fy_label(c, base + 2 - i) for i in range(count)]


def fy_to_sort_key(label: str) -> int:
    try:
        if "/" in label:
            return 2000 + int(label.split("/")[1])
        return int(label)
    except (ValueError, IndexError):
        return 0


def fy_display(label: str) -> str:
    return str(fy_to_sort_key(label))


def fy_range_display(fiscal_years: list[str] | None) -> str:
    if not fiscal_years:
        return ""
    ends = sorted(fy_to_sort_key(x) for x in fiscal_years)
    if len(ends) == 1:
        return str(ends[0])
    return f"{ends[0]}-{ends[-1]}"

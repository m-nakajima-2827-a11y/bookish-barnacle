"""UTM naming rules and a simplified GA4 default channel grouping.

The channel grouping mirrors the order of GA4's default channel group rules for the
cases this agent produces; confirm edge cases in GA4's own documentation.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VALID_VALUE = re.compile(r"^[a-z0-9]+(?:[_\-.][a-z0-9]+)*$")
SOCIAL_SOURCES = {"instagram", "l.instagram.com", "facebook", "m.facebook.com", "fb", "x", "twitter", "t.co",
                  "linkedin", "lnkd.in", "line", "tiktok", "note", "threads"}
SEARCH_SOURCES = {"google", "yahoo", "bing", "duckduckgo"}
SOCIAL_MEDIUMS = {"social", "social-network", "social-media", "sm", "social network", "social media"}
EMAIL_VALUES = {"email", "e-mail", "e_mail", "e mail"}
PAID = re.compile(r"^(.*cp.*|ppc|retargeting|paid.*)$")


def channel_group(source: str | None, medium: str | None) -> str:
    s, m = (source or "").lower(), (medium or "").lower()
    if not s and not m or (s == "(direct)" and m in {"(none)", "(not set)", ""}):
        return "Direct"
    if s in SEARCH_SOURCES and PAID.match(m):
        return "Paid Search"
    if s in SOCIAL_SOURCES and PAID.match(m):
        return "Paid Social"
    if m in {"display", "banner", "cpm"}:
        return "Display"
    if PAID.match(m):
        return "Paid Other"
    if s in SOCIAL_SOURCES or m in SOCIAL_MEDIUMS:
        return "Organic Social"
    if m == "organic" or s in SEARCH_SOURCES and m in {"", "organic"}:
        return "Organic Search"
    if s in EMAIL_VALUES or m in EMAIL_VALUES:
        return "Email"
    if m in {"referral", "app", "link"}:
        return "Referral"
    return "Unassigned"


def check_value(name: str, value: str) -> list[str]:
    errors = []
    if value != value.lower():
        errors.append(f"{name}: 大文字が含まれています（GA4では Instagram と instagram が別集計になります）")
    if any(ord(ch) > 127 for ch in value):
        errors.append(f"{name}: 全角・日本語は使えません（文字化け・計測ミスの原因）")
    if " " in value:
        errors.append(f"{name}: 空白は使えません")
    if not errors and not VALID_VALUE.match(value):
        errors.append(f"{name}: 半角英小文字・数字・_・- のみ使用できます")
    return errors


def build_url(base_url: str, params: dict[str, str]) -> str:
    parts = urlsplit(base_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_")]
    query += [(k, v) for k, v in params.items() if v]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

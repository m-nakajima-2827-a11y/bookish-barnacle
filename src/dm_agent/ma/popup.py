"""Popup display decision (表示条件: セグメント・URL・実名/匿名・表示頻度・期間)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..store import parse_ts
from .store import Profile

if TYPE_CHECKING:
    from ..runtime import AgentRuntime


def decide(rt: "AgentRuntime", p: Profile, url: str) -> dict[str, Any] | None:
    now = rt.now()
    candidates = []
    for pop in rt.ma.popups.values():
        c = pop["conditions"]
        if pop.get("status") != "active":
            continue
        if c.get("start_at") and now < parse_ts(c["start_at"]) or c.get("end_at") and now > parse_ts(c["end_at"]):
            continue
        if c.get("url_contains") and not any(u in url for u in c["url_contains"]):
            continue
        if any(u in url for u in c.get("url_excludes", [])):
            continue
        if c.get("segment_id") and c["segment_id"] not in p.segments:
            continue
        if c.get("audience") == "anonymous" and p.identified or c.get("audience") == "identified" and not p.identified:
            continue
        views = [a for a in p.activities if a["type"] == "popup_view" and a.get("popup_id") == pop["popup_id"]]
        freq = c.get("frequency", "once_per_day")
        if freq == "once_per_visitor" and views:
            continue
        if freq == "once_per_day" and any(now - parse_ts(a["timestamp"]) < timedelta(days=1) for a in views):
            continue
        if len(views) >= c.get("max_impressions", 10**9):
            continue
        if any(a["type"] == "popup_click" and a.get("popup_id") == pop["popup_id"] for a in p.activities) and c.get("hide_after_click", True):
            continue
        candidates.append(pop)
    if not candidates:
        return None
    pop = sorted(candidates, key=lambda x: -x.get("priority", 0))[0]
    return {"popup_id": pop["popup_id"], "type": pop["type"], "content": pop["content"],
            "show_after_seconds": pop["conditions"].get("show_after_seconds", 0)}

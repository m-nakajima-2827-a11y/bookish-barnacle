"""Outbound connectors: ad platforms, MA email, CRM tasks.

`Mock*` classes keep state in memory and record every call so workflows can be
tested end-to-end without touching real accounts. Implement the same methods
against Google Ads / Yahoo! 広告 / Meta Marketing / LinkedIn Marketing APIs, the MA tool
(HubSpot, Marketo, SATORI, etc.) and the CRM (Salesforce, HubSpot CRM, etc.) to go live.
IDs sent to ad platforms are hashed (SHA-256).
"""

from __future__ import annotations

import hashlib
from typing import Any


def hash_id(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


class MockAdPlatform:
    def __init__(self, name: str, campaigns: list[dict[str, Any]] | None = None):
        self.name = name
        self.campaigns = {c["campaign_id"]: c for c in (campaigns or [])}
        self.audiences: dict[str, set[str]] = {}
        self.calls: list[tuple[Any, ...]] = []

    def upsert_exclusion_audience(self, segment_id, hashed_ids):
        before = self.audiences.get(segment_id, set())
        self.audiences[segment_id] = before | set(hashed_ids)
        self.calls.append(("upsert_exclusion_audience", segment_id))
        for c in self.campaigns.values():
            ex = c.setdefault("excluded_segments", [])
            if segment_id not in ex:
                ex.append(segment_id)
        return {"added": len(self.audiences[segment_id] - before), "size": len(self.audiences[segment_id])}

    def get_campaigns(self):
        return list(self.campaigns.values())

    def set_daily_budget(self, campaign_id, amount):
        self.campaigns[campaign_id]["daily_budget"] = amount
        self.calls.append(("set_daily_budget", campaign_id, amount))

    def set_bidding(self, campaign_id, strategy, target):
        self.campaigns[campaign_id].update(bidding_strategy=strategy, bidding_target=target)
        self.calls.append(("set_bidding", campaign_id, strategy))

    def pause_creative(self, campaign_id, creative_id):
        self.campaigns[campaign_id]["creatives"][creative_id]["status"] = "paused"
        self.calls.append(("pause_creative", campaign_id, creative_id))


class MockEmail:
    """MA tool email sender."""

    def __init__(self):
        self.sent: list[dict[str, Any]] = []

    def send(self, lead_id: str, message: dict[str, Any]) -> dict[str, Any]:
        self.sent.append({"lead_id": lead_id, "message": message})
        return {"status": "accepted", "message_id": f"mail-{len(self.sent):06d}"}


class MockCRM:
    """CRM task / owner assignment for inside sales."""

    def __init__(self):
        self.tasks: list[dict[str, Any]] = []

    def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task = {"task_id": f"task-{len(self.tasks) + 1:05d}", **task}
        self.tasks.append(task)
        return task

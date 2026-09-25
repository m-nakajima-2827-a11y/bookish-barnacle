"""Outbound connectors (ad platforms, messaging channels).

`Mock*` classes keep state in memory and record every call so workflows can be
tested end-to-end without touching real accounts. Implement the same methods
against the Google Ads / Meta Marketing / LINE / X Ads APIs and MA tools to go live.
Customer IDs are always sent hashed (SHA-256), never in the clear.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol


def hash_id(customer_id: str) -> str:
    return hashlib.sha256(customer_id.strip().lower().encode()).hexdigest()


class AdPlatform(Protocol):
    name: str

    def upsert_exclusion_audience(self, segment_id: str, hashed_ids: list[str]) -> dict[str, Any]: ...
    def get_campaigns(self) -> list[dict[str, Any]]: ...
    def set_daily_budget(self, campaign_id: str, amount: float) -> None: ...
    def set_bidding(self, campaign_id: str, strategy: str, target_roas: float | None, target_cpa: float | None) -> None: ...
    def pause_creative(self, campaign_id: str, creative_id: str) -> None: ...


class MessagingChannel(Protocol):
    def send(self, channel: str, hashed_customer_id: str, message: dict[str, Any]) -> dict[str, Any]: ...


class MockAdPlatform:
    def __init__(self, name: str, campaigns: list[dict[str, Any]] | None = None):
        self.name = name
        self.campaigns = {c["campaign_id"]: c for c in (campaigns or [])}
        self.audiences: dict[str, set[str]] = {}
        self.calls: list[tuple[str, Any]] = []

    def upsert_exclusion_audience(self, segment_id, hashed_ids):
        before = self.audiences.get(segment_id, set())
        self.audiences[segment_id] = before | set(hashed_ids)
        self.calls.append(("upsert_exclusion_audience", segment_id))
        # Apply exclusion to every campaign that targets this segment's intent.
        for c in self.campaigns.values():
            if segment_id in c.get("exclude_segment_candidates", []):
                c.setdefault("excluded_segments", [])
                if segment_id not in c["excluded_segments"]:
                    c["excluded_segments"].append(segment_id)
        return {"added": len(self.audiences[segment_id] - before), "size": len(self.audiences[segment_id])}

    def get_campaigns(self):
        return list(self.campaigns.values())

    def set_daily_budget(self, campaign_id, amount):
        self.campaigns[campaign_id]["daily_budget"] = amount
        self.calls.append(("set_daily_budget", campaign_id, amount))

    def set_bidding(self, campaign_id, strategy, target_roas, target_cpa):
        c = self.campaigns[campaign_id]
        c.update(bidding_strategy=strategy, target_roas=target_roas, target_cpa=target_cpa)
        self.calls.append(("set_bidding", campaign_id, strategy))

    def pause_creative(self, campaign_id, creative_id):
        self.campaigns[campaign_id]["creatives"][creative_id]["status"] = "paused"
        self.calls.append(("pause_creative", campaign_id, creative_id))


class MockMessaging:
    def __init__(self):
        self.sent: list[dict[str, Any]] = []

    def send(self, channel, hashed_customer_id, message):
        rec = {"channel": channel, "to": hashed_customer_id, "message": message}
        self.sent.append(rec)
        return {"status": "accepted", "message_id": f"msg-{len(self.sent):06d}"}

"""In-memory CDP (customer data platform) store.

Production deployments replace this with a DWH/CDP adapter (BigQuery, Snowflake,
Treasure Data, etc.) implementing the same methods.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_key(customer_id: str, tp: dict[str, Any]) -> str:
    raw = json.dumps([customer_id, tp["channel"], tp["timestamp"], tp["event_type"], tp.get("payload", {})],
                     sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class CustomerProfile:
    customer_id: str
    first_seen: str | None = None
    last_seen: str | None = None
    channels: dict[str, int] = field(default_factory=dict)
    purchased_categories: dict[str, str] = field(default_factory=dict)  # category -> last purchase ts
    total_revenue: float = 0.0
    purchase_count: int = 0
    open_carts: dict[str, str] = field(default_factory=dict)  # sku -> cart_add ts
    consent: dict[str, bool] = field(default_factory=dict)  # outreach channel -> opted in
    segments: set[str] = field(default_factory=set)
    scores: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["segments"] = sorted(self.segments)
        return d


class CDPStore:
    def __init__(self, catalog: dict[str, Any]):
        self.catalog = catalog
        self.profiles: dict[str, CustomerProfile] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self._seen_keys: set[str] = set()
        self.outreach_log: list[dict[str, Any]] = []
        self.ad_spend: list[dict[str, Any]] = []  # {date, platform, campaign_id, cost, impressions, clicks, conversions, revenue}

    def profile(self, customer_id: str) -> CustomerProfile:
        if customer_id not in self.profiles:
            self.profiles[customer_id] = CustomerProfile(customer_id=customer_id)
            self.events[customer_id] = []
        return self.profiles[customer_id]

    def category_of(self, sku: str | None) -> str | None:
        return self.catalog.get("sku_category", {}).get(sku or "")

    def ingest(self, customer_id: str, touchpoints: list[dict[str, Any]]) -> dict[str, Any]:
        p = self.profile(customer_id)
        accepted, duplicates, derived = 0, 0, []
        for tp in sorted(touchpoints, key=lambda t: parse_ts(t["timestamp"])):
            key = event_key(customer_id, tp)
            if key in self._seen_keys:
                duplicates += 1
                continue
            self._seen_keys.add(key)
            accepted += 1
            ev = {**tp, "payload": tp.get("payload", {}), "event_id": key}
            self.events[customer_id].append(ev)
            ts = tp["timestamp"]
            if p.first_seen is None or parse_ts(ts) < parse_ts(p.first_seen):
                p.first_seen = ts
            if p.last_seen is None or parse_ts(ts) > parse_ts(p.last_seen):
                p.last_seen = ts
            p.channels[tp["channel"]] = p.channels.get(tp["channel"], 0) + 1
            payload = ev["payload"]
            if "consent" in payload:  # e.g. {"consent": {"app_push": true}} from membership/app settings
                p.consent.update(payload["consent"])
            if tp["event_type"] == "cart_add" and payload.get("sku"):
                p.open_carts[payload["sku"]] = ts
            if tp["event_type"] == "store_purchase":
                p.purchase_count += 1
                p.total_revenue += float(payload.get("amount", 0))
                skus = payload.get("skus") or ([payload["sku"]] if payload.get("sku") else [])
                for sku in skus:
                    p.open_carts.pop(sku, None)
                    cat = self.category_of(sku)
                    if cat:
                        p.purchased_categories[cat] = ts
                        p.segments.add(f"purchased_{cat}")
                        derived.append({"type": "category_purchased", "category": cat, "timestamp": ts})
        self.events[customer_id].sort(key=lambda e: parse_ts(e["timestamp"]))
        return {"accepted": accepted, "duplicates": duplicates, "derived_signals": derived}

    def segment_members(self, segment_id: str) -> list[str]:
        return sorted(cid for cid, p in self.profiles.items() if segment_id in p.segments)

    def save(self, path: Path) -> None:
        data = {
            "profiles": {k: v.to_dict() for k, v in self.profiles.items()},
            "events": self.events,
            "outreach_log": self.outreach_log,
            "ad_spend": self.ad_spend,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, catalog: dict[str, Any]) -> "CDPStore":
        store = cls(catalog)
        if not path.exists():
            return store
        data = json.loads(path.read_text(encoding="utf-8"))
        for cid, d in data["profiles"].items():
            d["segments"] = set(d["segments"])
            store.profiles[cid] = CustomerProfile(**d)
        store.events = data["events"]
        store._seen_keys = {e["event_id"] for evs in store.events.values() for e in evs}
        store.outreach_log = data.get("outreach_log", [])
        store.ad_spend = data.get("ad_spend", [])
        return store

"""Lead / account store (MA・CRM の統合ビュー).

Production deployments replace this with adapters to the MA tool / CRM / DWH
(e.g. HubSpot, Salesforce, Marketo, BigQuery) implementing the same methods.
No personal data (names, emails, phone numbers) is stored — only IDs and firmographics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

CONVERSION_EVENTS = {"whitepaper_download", "webinar_registration", "contact_request"}
HIGH_INTENT_EVENTS = {"webinar_attendance", "pricing_page_view", "case_study_view"}
STAGES = ["lead", "mql", "hot", "sql", "opportunity", "customer", "recycled", "disqualified"]


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_key(lead_id: str, tp: dict[str, Any]) -> str:
    raw = json.dumps([lead_id, tp["channel"], tp["timestamp"], tp["event_type"], tp.get("payload", {})],
                     sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Lead:
    lead_id: str
    account_id: str | None = None
    industry: str | None = None
    employee_band: str | None = None
    job_role: str | None = None
    fiscal_year_end_month: int | None = None
    email_opt_in: bool = False
    unsubscribed: bool = False
    first_seen: str | None = None
    last_seen: str | None = None
    first_touch: dict[str, Any] | None = None
    last_touch: dict[str, Any] | None = None
    stage: str = "lead"
    stage_history: list[dict[str, str]] = field(default_factory=list)
    score: dict[str, Any] = field(default_factory=dict)
    consumed_assets: list[str] = field(default_factory=list)
    nurture: dict[str, Any] | None = None
    handoff: dict[str, Any] | None = None
    opportunity: dict[str, Any] | None = None
    lost_reason: str | None = None

    def set_stage(self, stage: str, at: str, reason: str) -> bool:
        if stage == self.stage:
            return False
        self.stage_history.append({"from": self.stage, "to": stage, "at": at, "reason": reason})
        self.stage = stage
        return True


def touch_from_event(ev: dict[str, Any]) -> dict[str, Any]:
    p = ev.get("payload", {})
    utm = p.get("utm") or {}
    return {"channel": ev["channel"], "timestamp": ev["timestamp"], "event_type": ev["event_type"],
            "source": utm.get("source"), "medium": utm.get("medium"), "campaign": utm.get("campaign"),
            "content": utm.get("content"), "landing_page": p.get("landing_page")}


class LeadStore:
    def __init__(self):
        self.leads: dict[str, Lead] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self._seen: set[str] = set()
        self.email_log: list[dict[str, Any]] = []
        self.utm_registry: dict[str, dict[str, Any]] = {}
        self.ad_stats: list[dict[str, Any]] = []      # {date, platform, campaign_id, utm_campaign, cost, impressions, clicks, platform_leads}
        self.ga4_sessions: list[dict[str, Any]] = []  # {date, source, medium, campaign, landing_page, sessions, engaged_sessions, key_events}
        self.gsc_queries: list[dict[str, Any]] = []   # {date, query, clicks, impressions, position}

    def lead(self, lead_id: str) -> Lead:
        if lead_id not in self.leads:
            self.leads[lead_id] = Lead(lead_id=lead_id)
            self.events[lead_id] = []
        return self.leads[lead_id]

    def account_leads(self, account_id: str | None) -> list[Lead]:
        return [l for l in self.leads.values() if account_id and l.account_id == account_id]

    def ingest(self, lead_id: str, touchpoints: list[dict[str, Any]], account: dict[str, Any] | None = None,
               consent: dict[str, Any] | None = None) -> dict[str, Any]:
        ld = self.lead(lead_id)
        for k, v in (account or {}).items():
            setattr(ld, k, v)
        if consent:
            if "email_opt_in" in consent:
                ld.email_opt_in = consent["email_opt_in"]
            if consent.get("unsubscribed"):
                ld.unsubscribed = True
        accepted, dup, signals = 0, 0, []
        for tp in sorted(touchpoints, key=lambda t: parse_ts(t["timestamp"])):
            key = event_key(lead_id, tp)
            if key in self._seen:
                dup += 1
                continue
            self._seen.add(key)
            accepted += 1
            ev = {**tp, "payload": tp.get("payload", {}), "event_id": key}
            self.events[lead_id].append(ev)
            ts, p, et = tp["timestamp"], ev["payload"], tp["event_type"]
            if ld.first_seen is None or parse_ts(ts) < parse_ts(ld.first_seen):
                ld.first_seen = ts
            if ld.last_seen is None or parse_ts(ts) > parse_ts(ld.last_seen):
                ld.last_seen = ts
            touch = touch_from_event(ev)
            if touch["source"] or touch["landing_page"]:
                if ld.first_touch is None or parse_ts(ts) < parse_ts(ld.first_touch["timestamp"]):
                    ld.first_touch = touch
                if ld.last_touch is None or parse_ts(ts) >= parse_ts(ld.last_touch["timestamp"]):
                    ld.last_touch = touch
            if p.get("asset_id") and p["asset_id"] not in ld.consumed_assets:
                ld.consumed_assets.append(p["asset_id"])
            if et in CONVERSION_EVENTS:
                signals.append({"type": "lead_converted", "event_type": et, "timestamp": ts})
            elif et in HIGH_INTENT_EVENTS:
                signals.append({"type": "high_intent_activity", "event_type": et, "timestamp": ts})
            elif et == "sales_call" and ld.handoff and not ld.handoff.get("first_contact_at"):
                ld.handoff["first_contact_at"] = ts
            elif et == "meeting_booked":
                ld.opportunity = {"created_at": ts, "amount": float(p.get("amount", 0)), "status": "open"}
                ld.set_stage("opportunity", ts, "商談設定")
                signals.append({"type": "opportunity_created", "timestamp": ts})
            elif et == "deal_won":
                ld.opportunity = {**(ld.opportunity or {"created_at": ts}), "status": "won",
                                  "amount": float(p.get("amount", (ld.opportunity or {}).get("amount", 0)))}
                ld.set_stage("customer", ts, "受注")
                signals.append({"type": "deal_won", "timestamp": ts})
            elif et == "deal_lost":
                if ld.opportunity:
                    ld.opportunity["status"] = "lost"
                ld.lost_reason = p.get("lost_reason")
                ld.set_stage("recycled", ts, f"失注: {ld.lost_reason or '理由未記録'}")
                signals.append({"type": "deal_lost", "lost_reason": ld.lost_reason, "timestamp": ts})
        self.events[lead_id].sort(key=lambda e: parse_ts(e["timestamp"]))
        return {"accepted": accepted, "duplicates": dup, "signals": signals}

    def segment_members(self, segment_id: str) -> list[str]:
        """Built-in segments used for ad exclusion."""
        rules = {
            "customers": lambda l: l.stage == "customer",
            "open_opportunities": lambda l: l.stage in {"sql", "opportunity"},
            "disqualified": lambda l: l.stage == "disqualified",
            "hot_leads": lambda l: l.stage == "hot",
        }
        match = rules.get(segment_id)
        return sorted(l.lead_id for l in self.leads.values() if match and match(l))

    def save(self, path: Path) -> None:
        data = {"leads": {k: asdict(v) for k, v in self.leads.items()}, "events": self.events,
                "email_log": self.email_log, "utm_registry": self.utm_registry, "ad_stats": self.ad_stats,
                "ga4_sessions": self.ga4_sessions, "gsc_queries": self.gsc_queries}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LeadStore":
        s = cls()
        if not path.exists():
            return s
        data = json.loads(path.read_text(encoding="utf-8"))
        s.leads = {k: Lead(**v) for k, v in data["leads"].items()}
        s.events = data["events"]
        s._seen = {e["event_id"] for evs in s.events.values() for e in evs}
        for k in ("email_log", "utm_registry", "ad_stats", "ga4_sessions", "gsc_queries"):
            setattr(s, k, data.get(k, getattr(s, k)))
        return s

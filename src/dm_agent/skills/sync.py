"""① sync_lead_activity"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime import AgentRuntime


def sync_lead_activity(rt: "AgentRuntime", lead_id: str, touchpoints: list[dict[str, Any]],
                       account: dict[str, Any] | None = None, consent: dict[str, Any] | None = None) -> dict[str, Any]:
    result = rt.store.ingest(lead_id, touchpoints, account=account, consent=consent)
    ld = rt.store.leads[lead_id]
    # One re-score per batch is enough; other signals fire individually.
    fired_rescore = False
    for sig in result["signals"]:
        if sig["type"] in {"lead_converted", "high_intent_activity"}:
            if fired_rescore:
                continue
            fired_rescore = True
        rt.emit(sig["type"], lead_id=lead_id, **{k: v for k, v in sig.items() if k != "type"})
    return {
        "lead_id": lead_id,
        "accepted_events": result["accepted"],
        "duplicate_events_skipped": result["duplicates"],
        "signals": result["signals"],
        "lead": {
            "account_id": ld.account_id, "industry": ld.industry, "employee_band": ld.employee_band,
            "job_role": ld.job_role, "stage": ld.stage, "email_opt_in": ld.email_opt_in,
            "unsubscribed": ld.unsubscribed, "first_touch": ld.first_touch,
            "consumed_assets": ld.consumed_assets, "account_contacts": len(rt.store.account_leads(ld.account_id)),
        },
    }

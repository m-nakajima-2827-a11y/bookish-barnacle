"""① sync_omnichannel_customer_data"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime import AgentRuntime


def sync_omnichannel_customer_data(rt: "AgentRuntime", customer_id: str, touchpoints: list[dict[str, Any]]) -> dict[str, Any]:
    result = rt.store.ingest(customer_id, touchpoints)
    profile = rt.store.profiles[customer_id]
    # Emit domain events so the workflow layer can react (ad suppression, follow-up scheduling).
    for sig in result["derived_signals"]:
        rt.emit("category_purchased", customer_id=customer_id, **{k: v for k, v in sig.items() if k != "type"})
    return {
        "customer_id": customer_id,
        "accepted_events": result["accepted"],
        "duplicate_events_skipped": result["duplicates"],
        "derived_signals": result["derived_signals"],
        "profile": {
            "last_seen": profile.last_seen,
            "channels": profile.channels,
            "purchase_count": profile.purchase_count,
            "total_revenue": profile.total_revenue,
            "purchased_categories": sorted(profile.purchased_categories),
            "open_carts": sorted(profile.open_carts),
            "segments": sorted(profile.segments),
        },
    }

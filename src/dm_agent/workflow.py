"""Event-driven automation playbook: store purchase → ad suppression → prediction → cross-sell outreach.

Deterministic rules run without an LLM so that routine, high-volume reactions are
fast, cheap, and auditable. The LLM agent (llm_agent.py) handles open-ended
requests and exceptions on top of the same tools.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .runtime import AgentRuntime


def install_default_playbook(rt: AgentRuntime) -> None:
    wf = rt.policy["workflow"]

    def on_category_purchased(rt: AgentRuntime, origin: str, customer_id: str, category: str, timestamp: str) -> None:
        # Step 2: stop paying to retarget someone who already bought.
        for platform in wf["exclusion_platforms"]:
            rt.execute("optimize_ad_and_social_campaigns",
                       {"platform": platform, "action": "sync_audience_exclusion",
                        "target_segment_id": f"purchased_{category}"}, origin="playbook")
        # Step 3: re-score intent after the follow-up delay.
        rt.schedule(rt.now() + timedelta(days=wf["post_purchase_followup_days"]),
                    "predict_customer_intent_and_churn",
                    {"customer_id": customer_id,
                     "prediction_targets": ["category_affinity", "optimal_channel", "purchase_propensity"]})

    def on_prediction(rt: AgentRuntime, origin: str, customer_id: str, result: dict[str, Any]) -> None:
        # Step 4: cross-sell on high affinity via the best consented channel.
        # Only the playbook's own scheduled follow-up auto-sends; ad-hoc predictions stay read-only.
        if origin != "scheduler":
            return
        high = [a for a in result.get("category_affinity", []) if a["level"] == "high"]
        channel = (result.get("optimal_channel") or {}).get("channel")
        if not high or not channel:
            return
        products = [pid for a in high for pid in a["recommended_products"]]
        rt.execute("trigger_personalized_outreach", {
            "customer_id": customer_id, "selected_channel": channel,
            "campaign_scenario": "cross_sell_recommendation", "offer_type": wf["cross_sell_offer_type"],
            "payload_details": {"product_ids": products, "categories": [a["category"] for a in high],
                                "discount_rate": wf["cross_sell_discount_rate"]}}, origin="playbook")

    rt.on("category_purchased", on_category_purchased)
    rt.on("prediction_completed", on_prediction)

"""② predict_customer_intent_and_churn

Baseline = transparent rule/score model so the agent works on day one and every
score is explainable. Swap `ModelBackend` for a trained model (e.g. GBDT on CDP
features, served via Vertex AI / SageMaker) once enough labelled history exists.
All scores are estimates, not guarantees, and are labelled as such in the output.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..cdp import parse_ts

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

ENGAGEMENT_EVENTS = {"page_view", "app_open", "ad_click", "cart_add"}
CHANNEL_SIGNAL = {"app_push": "mobile_app", "line_official": "sns", "email": "email", "sms": None}
CHANNEL_PRIORITY = ["app_push", "line_official", "email", "sms"]


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def predict_customer_intent_and_churn(rt: "AgentRuntime", customer_id: str, prediction_targets: list[str],
                                      analysis_window_days: int | None = None) -> dict[str, Any]:
    cfg = rt.policy["prediction"]
    window = analysis_window_days or cfg["default_analysis_window_days"]
    p = rt.store.profiles.get(customer_id)
    if p is None:
        return {"error": "unknown_customer", "customer_id": customer_id}
    now = rt.now()
    events = [e for e in rt.store.events[customer_id] if now - timedelta(days=window) <= parse_ts(e["timestamp"]) <= now]
    days_since_last = (now - parse_ts(p.last_seen)).days if p.last_seen else None
    recent14 = [e for e in events if now - parse_ts(e["timestamp"]) <= timedelta(days=14)]
    engagement14 = sum(e["event_type"] in ENGAGEMENT_EVENTS for e in recent14)
    purchases = [e for e in events if e["event_type"] == "store_purchase"]

    out: dict[str, Any] = {
        "customer_id": customer_id,
        "analysis_window_days": window,
        "as_of": now.isoformat(),
        "model": "rule_based_baseline_v1",
        "note": "スコアは行動ログに基づく推定値（目安）です。",
        "features": {"events_in_window": len(events), "engagement_14d": engagement14,
                     "purchases_in_window": len(purchases), "days_since_last_activity": days_since_last},
    }
    segments: list[str] = []

    if "purchase_propensity" in prediction_targets:
        recency = days_since_last if days_since_last is not None else window
        x = -1.5 + 0.25 * min(engagement14, 10) + 0.8 * bool(p.open_carts) + 0.4 * min(len(purchases), 3) - 0.05 * recency
        score = round(_sigmoid(x), 3)
        aov = p.total_revenue / p.purchase_count if p.purchase_count else 0
        out["purchase_propensity"] = {"score_30d": score, "drivers": {
            "engagement_14d": engagement14, "open_cart": bool(p.open_carts), "recency_days": recency}}
        out["ltv_180d_estimate"] = {"value": round(aov * score * 3), "basis": "平均購買単価×購入確率×想定購買機会3回（目安）"}
        if score >= 0.6:
            segments.append("high_purchase_intent")

    if "churn_risk" in prediction_targets:
        inactive = cfg["churn_inactive_days"]
        recency = days_since_last if days_since_last is not None else inactive
        last30 = sum(now - parse_ts(e["timestamp"]) <= timedelta(days=30) for e in events)
        prev30 = sum(timedelta(days=30) < now - parse_ts(e["timestamp"]) <= timedelta(days=60) for e in events)
        trend = (last30 - prev30) / max(prev30, 1)
        score = round(min(1.0, max(0.0, recency / inactive * 0.8 + (0.2 if trend < -0.5 else 0.0))), 3)
        level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
        out["churn_risk"] = {"score": score, "level": level, "activity_trend_30d_vs_prev": round(trend, 2)}
        if level == "high":
            segments.append("churn_risk_high")

    if "category_affinity" in prediction_targets:
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        rules = rt.catalog.get("cross_sell_rules", {})
        for cat, ts in p.purchased_categories.items():
            age = (now - parse_ts(ts)).days
            if age > window:
                continue
            for rel in rules.get(cat, []):
                bonus = 0.2 if age <= 14 else 0.0
                scores[rel] = scores.get(rel, 0) + 0.5 + bonus
                reasons.setdefault(rel, []).append(f"{cat}購入（{age}日前）の併売ルール")
        for e in events:
            if e["event_type"] in {"page_view", "cart_add", "ad_click"}:
                cat = e["payload"].get("category") or rt.store.category_of(e["payload"].get("sku"))
                if cat:
                    w = 0.3 if e["event_type"] == "cart_add" else 0.1
                    scores[cat] = scores.get(cat, 0) + w
                    reasons.setdefault(cat, []).append(f"{e['event_type']}（{e['channel']}）")
        for cat in p.purchased_categories:  # already owned → not a recommendation target
            scores.pop(cat, None)
        threshold = cfg["high_affinity_threshold"]
        ranked = sorted(({"category": c, "score": round(min(s, 1.0), 3),
                          "level": "high" if s >= threshold else "medium" if s >= 0.3 else "low",
                          "reasons": reasons[c][:3],
                          "recommended_products": rt.catalog.get("category_products", {}).get(c, [])}
                         for c, s in scores.items()), key=lambda r: -r["score"])
        out["category_affinity"] = ranked
        segments += [f"cross_sell_{r['category']}" for r in ranked if r["level"] == "high"]

    if "optimal_channel" in prediction_targets:
        consented = [c for c in CHANNEL_PRIORITY if p.consent.get(c)]
        def signal(c: str) -> int:
            src = CHANNEL_SIGNAL[c]
            return p.channels.get(src, 0) if src else 0
        ranked_ch = sorted(consented, key=lambda c: (-signal(c), CHANNEL_PRIORITY.index(c)))
        out["optimal_channel"] = {
            "channel": ranked_ch[0] if ranked_ch else None,
            "ranking": [{"channel": c, "engagement_signal": signal(c)} for c in ranked_ch],
            "note": None if ranked_ch else "配信同意済みチャネルがないため、個別配信は行えません",
        }

    out["segments"] = segments
    p.segments.update(segments)
    p.scores = {k: out[k] for k in ("purchase_propensity", "churn_risk", "optimal_channel") if k in out}
    rt.emit("prediction_completed", customer_id=customer_id, result=out)
    return out

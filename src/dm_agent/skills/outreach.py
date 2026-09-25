"""④ trigger_personalized_outreach"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..connectors import hash_id

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

# Copy templates are drafts; brand/legal review is required before going live.
TEMPLATES = {
    "abandoned_cart": ("カートに商品が残っています", "お選びいただいた商品はまだカートに残っています。{offer}"),
    "post_store_visit_followup": ("ご来店ありがとうございました", "店舗でご覧いただいた商品をオンラインでもご確認いただけます。{offer}"),
    "churn_prevention": ("お久しぶりです", "新商品が入荷しています。{offer}"),
    "cross_sell_recommendation": ("ご購入商品と一緒に使えるアイテム", "先日のご購入品と相性の良いアイテムをご紹介します。{offer}"),
}
OFFER_TEXT = {
    "store_coupon": "直営店・ECどちらでも使える{rate}OFFクーポンをお届けします（{until}まで）。",
    "ec_free_shipping": "ECでのご注文は送料無料です（{until}まで）。",
    "point_multiplier": "期間中のお買い物でポイント{mult}倍（{until}まで）。",
    "personalized_content": "",
}


def _coupon_code(customer_id: str, scenario: str, issued: str) -> str:
    return "CP-" + hashlib.sha256(f"{customer_id}|{scenario}|{issued}".encode()).hexdigest()[:10].upper()


def trigger_personalized_outreach(rt: "AgentRuntime", customer_id: str, selected_channel: str, campaign_scenario: str,
                                  offer_type: str | None = None, payload_details: dict[str, Any] | None = None) -> dict[str, Any]:
    g = rt.guardrails
    now = rt.now()
    details = dict(payload_details or {})
    discount = details.get("discount_rate")
    base = {"customer_id": customer_id, "channel": selected_channel, "campaign_scenario": campaign_scenario,
            "offer_type": offer_type, "mode": "dry_run" if g.dry_run else "live"}

    violations = g.check_outreach(rt.store, customer_id, selected_channel, campaign_scenario, now, discount)
    if violations:
        rt.store.outreach_log.append({**base, "status": "blocked", "reasons": violations, "sent_at": now.isoformat()})
        return {**base, "status": "blocked", "reasons": violations}

    if g.in_quiet_hours(selected_channel, now):
        at = g.next_send_time(now)
        rt.schedule(at, "trigger_personalized_outreach", {
            "customer_id": customer_id, "selected_channel": selected_channel, "campaign_scenario": campaign_scenario,
            **({"offer_type": offer_type} if offer_type else {}), "payload_details": details})
        return {**base, "status": "scheduled", "scheduled_at": at.isoformat(), "reason": "配信停止時間帯のため翌朝に送信予約"}

    p = rt.store.profiles[customer_id]
    if campaign_scenario == "abandoned_cart" and not details.get("product_ids"):
        details["product_ids"] = sorted(p.open_carts)
    valid_days = details.get("valid_days", rt.policy["outreach"]["default_coupon_valid_days"])
    until = details.get("expires_at") or (now + timedelta(days=valid_days)).astimezone(g.tz).date().isoformat()
    details["expires_at"] = until
    if offer_type == "store_coupon":
        discount = discount if discount is not None else 0.1
        details["discount_rate"] = discount
        details["coupon_code"] = _coupon_code(customer_id, campaign_scenario, now.isoformat())
        details["redeemable_at"] = ["physical_store_pos", "web", "mobile_app"]

    title, body = TEMPLATES[campaign_scenario]
    offer = OFFER_TEXT.get(offer_type or "personalized_content", "").format(
        rate=f"{discount:.0%}" if discount else "", until=until, mult=details.get("point_multiplier", 2))
    message = {"title": title, "body": body.format(offer=offer).strip(), **details}

    record = {**base, "message": message, "sent_at": now.isoformat()}
    if g.dry_run:
        record["status"] = "planned"
    else:
        record["delivery"] = rt.messaging.send(selected_channel, hash_id(customer_id), message)
        record["status"] = "sent"
    rt.store.outreach_log.append(record)
    return record

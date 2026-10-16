"""Email delivery: guardrails, business hours, merge fields, click/open tracking, unsubscribe link."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

from ..utm import build_url
from .store import Profile, mask_email

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

TRANSACTIONAL = {"auto_reply"}  # フォーム送信への自動返信（請求された資料の送付）


def _token(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def _asset(rt, asset_id):
    return next((a for a in rt.client["content_library"] if a["asset_id"] == asset_id), None)


def deliver(rt: "AgentRuntime", p: Profile, spec: dict[str, Any]) -> dict[str, Any]:
    """spec: subject, body, asset_id?, link_url?, campaign?, category(step|bulk|auto_reply|single), scenario_id?, step?"""
    g, now, ma = rt.guardrails, rt.now(), rt.ma
    category = spec.get("category", "single")
    asset = _asset(rt, spec.get("asset_id")) if spec.get("asset_id") else None
    base = {"profile_id": p.profile_id, "customer_id": p.customer_id, "category": category,
            "subject": spec.get("subject") or (asset and asset["title"]), "asset_id": spec.get("asset_id"),
            "scenario_id": spec.get("scenario_id"), "mode": "dry_run" if g.dry_run else "live"}
    email = p.contact.get("email")
    reasons = []
    if not email:
        reasons.append("no_email_address: メールアドレス未登録（匿名客）です")
    ld = rt.store.leads.get(p.customer_id or "")
    reasons += g.check_email(ma.emails, p.profile_id, opted_in=p.email_opt_in, unsubscribed=p.unsubscribed,
                             stage=ld.stage if ld else None, asset_id=spec.get("asset_id"), now=now,
                             transactional=category in TRANSACTIONAL)
    if reasons:
        rec = {**base, "status": "blocked", "reasons": reasons, "at": now.isoformat()}
        ma.emails.append(rec)
        return rec
    if category not in TRANSACTIONAL and rt.policy["email"]["send_in_business_hours_only"] and not g.in_business_hours(now):
        at = g.next_business_open(now)
        rt.schedule(at, "_ma_deliver_email", {"profile_id": p.profile_id, "spec": spec})
        return {**base, "status": "scheduled", "scheduled_at": at.isoformat(), "reason": "営業時間外のため翌営業日に配信予約"}

    email_id = ma.next_id("E")
    token = _token(email_id, p.profile_id, now.isoformat())
    domain = rt.client["ma"]["tracking_domain"]
    target = spec.get("link_url") or (asset and asset["url"])
    if target:
        target = build_url(target, {"utm_source": "ma_email", "utm_medium": "email",
                                    "utm_campaign": spec.get("campaign") or (spec.get("scenario_id") or category).lower(),
                                    "utm_content": (spec.get("asset_id") or email_id).lower()})
    merge = {"company_name": p.attributes.get("company_name", ""), "name": p.contact.get("name", "")}
    body = spec.get("body") or (f"{asset['title']}をご案内します。" if asset else "")
    body = re.sub(r"\{\{(\w+)\}\}", lambda m: str(merge.get(m.group(1), "")), body)
    if target:
        body += f"\n{domain}/c/{token}"
    sender = rt.client["sender"]
    footer = rt.policy["email"]["required_footer"].format(unsubscribe_url=f"{domain}/u/{token}",
                                                         sender_name=sender["name"], sender_address=sender["address"])
    message = {"subject": base["subject"], "body": f"{body}\n\n--\n{footer}", "open_pixel": f"{domain}/o/{token}.gif"}
    rec = {**base, "email_id": email_id, "token": token, "to": mask_email(email), "link_target": target,
           "sent_at": now.isoformat(), "opens": 0, "clicks": 0, "lead_id": p.customer_id}
    if g.dry_run:
        rec["status"] = "planned"
    else:
        rec["delivery"] = rt.email.send(email, message)
        rec["status"] = "sent"
    ma.emails.append(rec)
    ma.email_tokens[token] = len(ma.emails) - 1
    return {**rec, "preview": {"subject": message["subject"], "body": message["body"].replace(email, mask_email(email))}}

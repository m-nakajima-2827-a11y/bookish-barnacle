"""③ trigger_nurture_action — nurturing emails, content recommendation, sales handoff, recontact."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ..store import parse_ts
from ..utm import build_url

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

STAGE_TO_FUNNEL = {"lead": "awareness", "recycled": "awareness", "mql": "consideration", "hot": "decision"}
FUNNEL_ORDER = ["awareness", "consideration", "decision"]
STOP_NURTURE_STAGES = {"sql", "opportunity", "customer", "disqualified"}


def _asset(rt: "AgentRuntime", asset_id: str | None) -> dict[str, Any] | None:
    return next((a for a in rt.client["content_library"] if a["asset_id"] == asset_id), None)


def _track_for(rt: "AgentRuntime", industry: str | None, requested: str | None) -> str:
    if requested:
        return requested
    return industry if industry in rt.client["nurture_tracks"] else "general"


def _recommend(rt: "AgentRuntime", ld) -> list[dict[str, Any]]:
    target = STAGE_TO_FUNNEL.get(ld.stage, "consideration")
    pool = [a for a in rt.client["content_library"] if a["asset_id"] not in ld.consumed_assets
            and a["industry"] in {ld.industry, "general"}]
    return sorted(pool, key=lambda a: (abs(FUNNEL_ORDER.index(a["stage"]) - FUNNEL_ORDER.index(target)),
                                       a["industry"] == "general"))[:3]


def _send_email(rt, ld, base, asset, details, origin_step: str | None):
    g, now = rt.guardrails, rt.now()
    if origin_step and ld.stage in STOP_NURTURE_STAGES:
        return {**base, "status": "skipped", "reason": f"ステージが {ld.stage} のため育成メールを停止（営業対応を優先）"}
    if origin_step and not origin_step.endswith("#0") and asset and asset["asset_id"] in ld.consumed_assets:
        return {**base, "status": "skipped", "reason": f"{asset['asset_id']} は閲覧・DL済みのため送信不要"}
    v = g.check_email(rt.store, ld, asset and asset["asset_id"], now)
    if v:
        rt.store.email_log.append({"lead_id": ld.lead_id, "status": "blocked", "reasons": v, "sent_at": now.isoformat(),
                                   "asset_id": asset and asset["asset_id"]})
        return {**base, "status": "blocked", "reasons": v}
    if rt.policy["email"]["send_in_business_hours_only"] and not g.in_business_hours(now):
        at = g.next_business_open(now)
        rt.schedule(at, "trigger_nurture_action", {"lead_id": ld.lead_id, "action": base["action"],
                                                   **({"content_asset_id": asset["asset_id"]} if asset else {}),
                                                   "payload_details": details})
        return {**base, "status": "scheduled", "scheduled_at": at.isoformat(), "reason": "営業時間外のため翌営業日の配信に予約"}
    sender = rt.client["sender"]
    link = None
    if asset:
        link = build_url(asset["url"], {"utm_source": "ma_email", "utm_medium": "email",
                                        "utm_campaign": f"nurture_{details.get('track', 'adhoc')}",
                                        "utm_content": asset["asset_id"].lower()})
    body = details.get("body") or (f"{asset['title']}をご案内します。\n{link}" if asset else "")
    footer = rt.policy["email"]["required_footer"].format(unsubscribe_url=sender["unsubscribe_url"],
                                                         sender_name=sender["name"], sender_address=sender["address"])
    message = {"subject": details.get("subject") or (asset["title"] if asset else "ご案内"),
               "body": f"{body}\n\n--\n{footer}", "link": link}
    rec = {"lead_id": ld.lead_id, "asset_id": asset and asset["asset_id"], "sent_at": now.isoformat(),
           "track_step": origin_step, "message": message}
    if g.dry_run:
        rec["status"] = "planned"
    else:
        rec["delivery"] = rt.email.send(ld.lead_id, message)
        rec["status"] = "sent"
    rt.store.email_log.append(rec)
    return {**base, **rec}


def _budget_planning_date(rt: "AgentRuntime", ld, today: date) -> tuple[date, str]:
    cfg = rt.client["recontact"]
    fye = ld.fiscal_year_end_month or cfg["default_fiscal_year_end_month"]
    fy_start = fye % 12 + 1
    month = (fy_start - 1 - cfg["budget_planning_months_before_fy_start"]) % 12 + 1
    d = date(today.year, month, 1)
    if d <= today:
        d = date(today.year + 1, month, 1)
    basis = (f"決算{fye}月 → 期初{fy_start}月の{cfg['budget_planning_months_before_fy_start']}か月前を"
             f"予算編成時期と仮定（{'決算月は登録値' if ld.fiscal_year_end_month else '決算月は未登録のため既定値'}）")
    return d, basis


def trigger_nurture_action(rt: "AgentRuntime", lead_id: str, action: str, nurture_track: str | None = None,
                           content_asset_id: str | None = None, payload_details: dict[str, Any] | None = None) -> dict[str, Any]:
    ld = rt.store.leads.get(lead_id)
    g, now = rt.guardrails, rt.now()
    details = dict(payload_details or {})
    base = {"lead_id": lead_id, "action": action, "mode": "dry_run" if g.dry_run else "live"}
    if ld is None:
        return {**base, "error": "unknown_lead"}
    asset = _asset(rt, content_asset_id)
    if content_asset_id and asset is None:
        return {**base, "error": f"unknown content_asset_id {content_asset_id}"}

    if action == "enroll_nurture_track":
        if ld.stage in STOP_NURTURE_STAGES:
            return {**base, "status": "blocked", "reasons": [f"ステージ {ld.stage} のリードは育成シナリオに登録できません"]}
        if ld.nurture and ld.nurture.get("status") == "active":
            return {**base, "status": "skipped", "reason": f"登録済み（{ld.nurture['track']}）"}
        track = _track_for(rt, ld.industry, nurture_track)
        steps = rt.client["nurture_tracks"][track]
        ld.nurture = {"track": track, "enrolled_at": now.isoformat(), "status": "active"}
        planned = []
        for i, step in enumerate(steps):
            args = {"lead_id": lead_id, "action": "send_email", "content_asset_id": step["asset_id"],
                    "payload_details": {"subject": step["subject"], "track": track, "track_step": f"{track}#{i}"}}
            if step["day"] == 0:
                first = rt.execute("trigger_nurture_action", args, origin="nurture_track")
                planned.append({"day": 0, "asset_id": step["asset_id"], "status": first.get("status"),
                                "reason": first.get("reason") or first.get("reasons")})
            else:
                at = g.next_business_open(now + timedelta(days=step["day"]))
                rt.schedule(at, "trigger_nurture_action", args)
                planned.append({"day": step["day"], "asset_id": step["asset_id"], "status": "scheduled", "at": at.isoformat()})
        return {**base, "status": "enrolled", "nurture_track": track, "steps": planned,
                "note": "営業対応ステージ（SQL以降）に進んだ時点で残りの配信は自動停止します"}

    if action in {"send_email", "invite_webinar"}:
        if action == "invite_webinar" and asset is None:
            asset = _asset(rt, rt.client["social"]["webinar_asset_id"])
        return _send_email(rt, ld, base, asset, details, details.get("track_step"))

    if action == "recommend_content":
        recs = _recommend(rt, ld)
        return {**base, "status": "ok", "stage": ld.stage, "consumed_assets": ld.consumed_assets,
                "recommendations": [{"asset_id": a["asset_id"], "title": a["title"], "type": a["type"],
                                     "funnel_stage": a["stage"]} for a in recs],
                "note": "送信する場合は action=send_email と content_asset_id を指定してください"}

    if action == "sales_handoff":
        allowed = rt.policy["sales_handoff"]["allow_stages"]
        if ld.stage not in allowed:
            return {**base, "status": "blocked",
                    "reasons": [f"ステージが {ld.stage} です。営業引き渡しは {allowed} のリードのみ（先に score_and_qualify_leads を実行）"]}
        sla = rt.policy["sales_handoff"]["first_contact_sla_minutes"]
        due = g.add_business_minutes(now, sla)
        recent = [f"{e['timestamp'][:16]} {e['channel']}:{e['event_type']}"
                  + (f"({e['payload'].get('asset_id')})" if e["payload"].get("asset_id") else "")
                  for e in rt.store.events[lead_id][-6:]]
        consumed = [a["title"] for a in rt.client["content_library"] if a["asset_id"] in ld.consumed_assets]
        task = {"type": "first_contact", "lead_id": lead_id, "account_id": ld.account_id, "due_at": due.isoformat(),
                "sla_minutes": sla, "priority": "high",
                "context": {"industry": ld.industry, "employee_band": ld.employee_band, "job_role": ld.job_role,
                            "score": ld.score, "first_touch": ld.first_touch, "recent_activity": recent,
                            "consumed_content": consumed,
                            "account_contacts": len(rt.store.account_leads(ld.account_id)),
                            "talk_points_hypothesis": [f"「{t}」に関心がある可能性（閲覧履歴からの仮説）" for t in consumed[:3]],
                            "note": details.get("handoff_note")}}
        if g.dry_run:
            task["status"] = "planned"
        else:
            task = {**rt.crm.create_task(task), "status": "created"}
            ld.handoff = {"at": now.isoformat(), "due_at": due.isoformat(), "task_id": task["task_id"]}
            ld.set_stage("sql", now.isoformat(), "インサイドセールスへ引き渡し")
            if ld.nurture:
                ld.nurture["status"] = "stopped"
            rt.emit("lead_handed_off", lead_id=lead_id)
        return {**base, "status": task["status"], "task": task,
                "rule": f"初回接触は営業時間内{sla}分以内（期限 {due.astimezone(g.tz):%m/%d %H:%M}）"}

    if action == "schedule_recontact":
        today = now.astimezone(g.tz).date()
        if details.get("recontact_date"):
            d, basis = date.fromisoformat(details["recontact_date"]), "指定日"
        else:
            d, basis = _budget_planning_date(rt, ld, today)
        due = g.next_business_open(datetime.combine(d, time(0, 0), g.tz))
        task = {"type": "recontact", "lead_id": lead_id, "account_id": ld.account_id, "due_at": due.isoformat(),
                "priority": "normal", "context": {"lost_reason": ld.lost_reason, "basis": basis,
                                                  "note": details.get("handoff_note")}}
        if g.dry_run:
            task["status"] = "planned"
        else:
            task = {**rt.crm.create_task(task), "status": "created"}
        return {**base, "status": task["status"], "recontact_date": d.isoformat(), "basis": basis, "task": task}

    return {**base, "error": f"unsupported action {action}"}

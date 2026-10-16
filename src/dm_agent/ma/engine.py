"""MA engine: identity (匿名→実名), scoring, tags, segments, scenarios, and the bridge to the lead store."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlsplit

from ..store import parse_ts
from .store import Profile

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

# SATORI の公開FAQに記載の既定値（ウェブアクセス+5、メール内リンククリック+10、開封+1、配信停止−30）。
# form_submit / popup_click / push_click は本実装での追加（初期値は仮置き）。
DEFAULT_COMMON_SCORES = {"web_access": 5, "email_click": 10, "email_open": 1, "unsubscribe": -30,
                         "form_submit": 0, "popup_click": 0, "push_click": 0}
SCORE_LIMIT = 100_000


# --- identity ---------------------------------------------------------------------------------
def profile_for_cookie(rt: "AgentRuntime", cookie: str) -> Profile:
    ma = rt.ma
    pid = ma.cookie_index.get(cookie)
    if pid and pid in ma.profiles:
        return ma.profiles[pid]
    p = Profile(profile_id=f"anon:{cookie}", cookies=[cookie], created_at=rt.now().isoformat())
    ma.profiles[p.profile_id] = p
    ma.cookie_index[cookie] = p.profile_id
    return p


def ensure_customer(rt: "AgentRuntime", customer_id: str) -> Profile:
    ma = rt.ma
    p = ma.by_customer(customer_id)
    if p is None:
        p = Profile(profile_id=customer_id, customer_id=customer_id, created_at=rt.now().isoformat())
        ma.profiles[customer_id] = p
    return p


def find_by_email(rt: "AgentRuntime", email: str) -> Profile | None:
    pid = rt.ma.email_index.get(email.strip().lower())
    return rt.ma.profiles.get(pid) if pid else None


def set_contact(rt: "AgentRuntime", p: Profile, contact: dict[str, Any]) -> None:
    p.contact.update({k: v for k, v in contact.items() if v})
    if p.contact.get("email"):
        rt.ma.email_index[p.contact["email"].strip().lower()] = p.profile_id


def identify(rt: "AgentRuntime", cookie: str | None, customer: Profile) -> int:
    """Merge the anonymous history behind `cookie` into `customer` (実名化). Returns merged activity count."""
    if not cookie:
        return 0
    ma = rt.ma
    anon_id = ma.cookie_index.get(cookie)
    ma.cookie_index[cookie] = customer.profile_id
    if cookie not in customer.cookies:
        customer.cookies.append(cookie)
    if not anon_id or anon_id == customer.profile_id or anon_id not in ma.profiles:
        return 0
    anon = ma.profiles.pop(anon_id)
    if anon.identified:  # cookie used by another known customer (shared PC) — keep histories apart
        ma.profiles[anon_id] = anon
        ma.cookie_index[cookie] = anon_id
        return 0
    customer.activities = sorted(anon.activities + customer.activities, key=lambda a: a["timestamp"])
    customer.score = _clamp(customer.score + anon.score)
    customer.score_log += anon.score_log
    customer.tags += [t for t in anon.tags if t not in customer.tags]
    customer.push_subscribed |= anon.push_subscribed
    for c in anon.cookies:
        ma.cookie_index[c] = customer.profile_id
        if c not in customer.cookies:
            customer.cookies.append(c)
    for e in ma.enrollments.values():
        if e["profile_id"] == anon_id:
            e["profile_id"] = customer.profile_id
    forward_to_lead(rt, customer, [a for a in anon.activities if a["type"] in LEAD_FORWARD])
    return len(anon.activities)


# --- scoring ------------------------------------------------------------------------------------
def _clamp(v: int) -> int:
    return max(-SCORE_LIMIT, min(SCORE_LIMIT, v))


def _url_matches(rule: dict[str, Any], url: str | None, utm: dict[str, Any] | None) -> bool:
    if not url and not utm:
        return False
    if rule.get("url_filter") and rule["url_filter"] not in (url or ""):
        return False
    if rule.get("param_filter"):
        k, _, v = rule["param_filter"].partition("=")
        params = dict(parse_qsl(urlsplit(url or "").query))
        params.update({f"utm_{a}": b for a, b in (utm or {}).items()})
        if params.get(k) != v:
            return False
    return True


def apply_points(p: Profile, points: int, reason: str, at: str) -> None:
    if points:
        p.score = _clamp(p.score + points)
        p.score_log.append({"at": at, "points": points, "reason": reason})


def score_activity(rt: "AgentRuntime", p: Profile, a: dict[str, Any]) -> int:
    sd = rt.ma.score_definition
    common = {**DEFAULT_COMMON_SCORES, **sd.get("common", {})}
    t = a["type"]
    total = 0
    if t == "web_access":
        hits = [r for r in sd.get("individual", []) if r.get("target") == "web_access" and _url_matches(r, a.get("url"), a.get("utm"))]
        if hits:  # 個別設定に該当したアクセスは個別設定の点数を適用（共通設定は加算しない）
            for r in hits:
                apply_points(p, r["points"], f"個別:{r['rule_id']}", a["timestamp"])
                total += r["points"]
            return total
    elif t == "form_submit":
        for r in sd.get("individual", []):
            if r.get("target") == "form_submit" and r.get("form_id") == a.get("form_id"):
                apply_points(p, r["points"], f"個別:{r['rule_id']}", a["timestamp"])
                total += r["points"]
    pts = common.get(t, 0)
    apply_points(p, pts, f"共通:{t}", a["timestamp"])
    return total + pts


def _score_event(rt: "AgentRuntime", p: Profile, target: str, key: str) -> None:
    for r in rt.ma.score_definition.get("individual", []):
        if r.get("target") == target and r.get("key") == key:
            apply_points(p, r["points"], f"個別:{r['rule_id']}", rt.now().isoformat())


# --- activity -----------------------------------------------------------------------------------
LEAD_FORWARD = {"web_access", "email_open", "email_click"}


def record(rt: "AgentRuntime", p: Profile, a: dict[str, Any], forward: bool = True) -> dict[str, Any]:
    p.activities.append(a)
    if not p.last_seen or parse_ts(a["timestamp"]) > parse_ts(p.last_seen):
        p.last_seen = a["timestamp"]
    if a["type"] == "push_permission":
        p.push_subscribed = bool(a.get("granted"))
    points = score_activity(rt, p, a)
    if forward and p.identified and a["type"] in LEAD_FORWARD:
        forward_to_lead(rt, p, [a])
    entered = evaluate_segments(rt, p)
    return {"points": points, "entered_segments": entered}


def forward_to_lead(rt: "AgentRuntime", p: Profile, activities: list[dict[str, Any]]) -> None:
    """Hand identified-customer behaviour to the lead store (scoring / funnel / playbook)."""
    if not p.identified or not activities:
        return
    url_map = rt.client.get("ma", {}).get("url_event_map", [])
    tps = []
    for a in activities:
        payload: dict[str, Any] = {}
        if a["type"] == "web_access":
            path = urlsplit(a.get("url") or "").path
            et = next((m["event_type"] for m in url_map if m["contains"] in path), "page_view")
            ch = "landing_page" if path.startswith("/lp/") else "website"
            payload = {"url": path}
            if a.get("utm"):
                payload["utm"] = a["utm"]
            if ch == "landing_page":
                payload["landing_page"] = path
            asset = next((m.get("asset_id") for m in url_map if m["contains"] in path and m.get("asset_id")), None)
            if asset:
                payload["asset_id"] = asset
        elif a["type"] in {"email_open", "email_click"}:
            et, ch = a["type"], "email"
            payload = {k: a[k] for k in ("email_id", "asset_id") if a.get(k)}
        else:
            continue
        tps.append({"channel": ch, "timestamp": a["timestamp"], "event_type": et, "payload": payload})
    if tps:
        rt.execute("sync_lead_activity", {"lead_id": p.customer_id, "touchpoints": tps}, origin="ma")


# --- tags ---------------------------------------------------------------------------------------
def add_tag(rt: "AgentRuntime", p: Profile, tag: str, source: str) -> bool:
    if tag in p.tags:
        return False
    p.tags.append(tag)
    _score_event(rt, p, "tag_added", tag)
    fire_trigger(rt, p, "tag_added", tag)
    evaluate_segments(rt, p)
    return True


def remove_tag(rt: "AgentRuntime", p: Profile, tag: str) -> bool:
    if tag not in p.tags:
        return False
    p.tags.remove(tag)
    evaluate_segments(rt, p)
    return True


# --- segments -------------------------------------------------------------------------------------
def _within(rt, a, days):
    return days is None or rt.now() - parse_ts(a["timestamp"]) <= timedelta(days=days)


def matches(rt: "AgentRuntime", p: Profile, c: dict[str, Any]) -> bool:
    if "all" in c:
        return all(matches(rt, p, x) for x in c["all"])
    if "any" in c:
        return any(matches(rt, p, x) for x in c["any"])
    if "not" in c:
        return not matches(rt, p, c["not"])
    t, days = c["type"], c.get("within_days")
    if t == "page_view":
        n = sum(1 for a in p.activities if a["type"] == "web_access" and _within(rt, a, days)
                and (not c.get("url_contains") or c["url_contains"] in (a.get("url") or "")))
        return n >= c.get("min_count", 1)
    if t == "utm":
        return any(a.get("utm") and all(a["utm"].get(k) == v for k, v in c.get("match", {}).items())
                   and _within(rt, a, days) for a in p.activities)
    if t in {"email_open", "email_click", "popup_click", "push_click", "form_submit"}:
        return any(a["type"] == t and _within(rt, a, days) and all(a.get(k) == v for k, v in c.get("match", {}).items())
                   for a in p.activities)
    if t == "tag":
        return (c["has"] in p.tags) if "has" in c else (c.get("not_has") not in p.tags)
    if t == "score":
        return p.score >= c.get("gte", -SCORE_LIMIT) and p.score <= c.get("lte", SCORE_LIMIT)
    if t == "attribute":
        v = p.attributes.get(c["field"])
        return v in c["in"] if "in" in c else v == c.get("equals")
    if t == "identified":
        return p.identified == c.get("value", True)
    if t == "push_subscribed":
        return p.push_subscribed == c.get("value", True)
    if t == "email_opt_in":
        return p.email_opt_in and not p.unsubscribed
    if t == "lead_stage":
        ld = rt.store.leads.get(p.customer_id or "")
        return bool(ld and ld.stage in c["in"])
    raise ValueError(f"unknown segment condition type: {t}")


def evaluate_segments(rt: "AgentRuntime", p: Profile) -> list[str]:
    entered = []
    for sid, seg in rt.ma.segments.items():
        if seg.get("status", "active") != "active":
            continue
        hit = matches(rt, p, seg["conditions"])
        if hit and sid not in p.segments:
            p.segments.append(sid)
            entered.append(sid)
        elif not hit and sid in p.segments:
            p.segments.remove(sid)
    for sid in entered:
        _score_event(rt, p, "segment_entered", sid)
        fire_trigger(rt, p, "segment_entered", sid)
    return entered


# --- scenarios ------------------------------------------------------------------------------------
def fire_trigger(rt: "AgentRuntime", p: Profile, kind: str, key: str) -> None:
    for sc in list(rt.ma.scenarios.values()):
        trg = sc["trigger"]
        if sc.get("status") == "active" and trg["type"] == kind and trg.get("key") == key:
            enroll(rt, sc["scenario_id"], p, source=f"{kind}:{key}")


def enroll(rt: "AgentRuntime", scenario_id: str, p: Profile, source: str) -> dict[str, Any]:
    ma = rt.ma
    sc = ma.scenarios[scenario_id]
    key = f"{scenario_id}|{p.profile_id}"
    cur = ma.enrollments.get(key)
    if cur and (cur["status"] == "active" or not sc.get("allow_reentry", False)):
        return {"status": "skipped", "reason": f"登録済み（{cur['status']}）"}
    now = rt.now()
    ma.enrollments[key] = {"scenario_id": scenario_id, "profile_id": p.profile_id, "status": "active",
                           "entered_at": now.isoformat(), "source": source, "steps_done": [], "exit_reason": None}
    for i, step in enumerate(sc["steps"]):
        at = now + timedelta(days=step.get("day", 0), hours=step.get("hour", 0))
        if at <= now:
            run_step(rt, scenario_id, p.profile_id, i)
        else:
            rt.schedule(at, "_ma_scenario_step", {"scenario_id": scenario_id, "profile_id": p.profile_id, "step_index": i})
    return {"status": "enrolled", "steps": len(sc["steps"])}


def _exit_reason(rt: "AgentRuntime", sc: dict[str, Any], p: Profile) -> str | None:
    ex = sc.get("exit_conditions") or {}
    ld = rt.store.leads.get(p.customer_id or "")
    if ld and ld.stage in ex.get("lead_stages", []):
        return f"リードのステージが {ld.stage}"
    if any(t in p.tags for t in ex.get("tags", [])):
        return "除外タグが付与"
    if any(s in p.segments for s in ex.get("segments", [])):
        return "除外セグメントに該当"
    return None


def run_step(rt: "AgentRuntime", scenario_id: str, profile_id: str, step_index: int) -> dict[str, Any]:
    from .email import deliver  # local import to avoid a cycle

    ma = rt.ma
    p = ma.profiles.get(profile_id) or ma.profiles.get(ma.cookie_index.get(profile_id.removeprefix("anon:"), ""))
    sc = ma.scenarios.get(scenario_id)
    if p is None or sc is None:
        return {"status": "skipped", "reason": "シナリオまたはカスタマーが見つかりません"}
    enr = ma.enrollments.get(f"{scenario_id}|{p.profile_id}")
    if not enr or enr["status"] != "active":
        return {"status": "skipped", "reason": "シナリオ対象外（終了・停止済み）"}
    if sc.get("status") != "active":
        return {"status": "skipped", "reason": "シナリオが停止中"}
    reason = _exit_reason(rt, sc, p)
    if reason:
        enr.update(status="exited", exit_reason=reason)
        return {"status": "exited", "reason": reason}
    step = sc["steps"][step_index]
    act = step["action"]
    ld = rt.store.leads.get(p.customer_id or "")
    if act == "send_email" and step.get("skip_if_consumed") and ld and step["email"].get("asset_id") in ld.consumed_assets:
        res = {"status": "skipped", "reason": f"{step['email']['asset_id']} は閲覧・DL済み"}
    elif act == "send_email":
        res = deliver(rt, p, {**step["email"], "category": "step", "scenario_id": scenario_id, "step": step_index})
    elif act == "add_tag":
        res = {"status": "ok", "added": add_tag(rt, p, step["tag"], f"scenario:{scenario_id}")}
    elif act == "remove_tag":
        res = {"status": "ok", "removed": remove_tag(rt, p, step["tag"])}
    elif act == "notify":
        res = notify(rt, p, step["notify"], f"シナリオ「{sc['name']}」")
    else:
        res = {"status": "error", "reason": f"unknown action {act}"}
    enr["steps_done"].append({"step": step_index, "at": rt.now().isoformat(), "status": res.get("status")})
    if len(enr["steps_done"]) >= len(sc["steps"]):
        enr["status"] = "completed"
    return res


def notify(rt: "AgentRuntime", p: Profile, spec: dict[str, Any], origin: str) -> dict[str, Any]:
    """社内通知: 担当者メール / Webhook（Slack・CRM等）/ CRMタスク。個人情報はマスクして送る。"""
    body = {"origin": origin, "customer_id": p.customer_id, "profile_id": p.profile_id, "score": p.score,
            "tags": p.tags, "attributes": p.attributes, "message": spec.get("message"),
            "recent_activity": [f"{a['timestamp'][:16]} {a['type']} {a.get('url') or ''}".strip() for a in p.activities[-5:]]}
    rec = {"notification_id": rt.ma.next_id("N"), "channel": spec["channel"], "to": spec.get("to"),
           "at": rt.now().isoformat(), "payload": body}
    if rt.guardrails.dry_run:
        rec["status"] = "planned"
    elif spec["channel"] == "crm_task":
        rec["task"] = rt.crm.create_task({"type": "ma_alert", "lead_id": p.customer_id, "due_at": rt.now().isoformat(),
                                          "priority": "high", "context": body})
        rec["status"] = "created"
    else:
        rec["delivery"] = rt.webhook.post(spec.get("to"), body)
        rec["status"] = "sent"
    rt.ma.notifications.append(rec)
    return rec

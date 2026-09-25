"""② score_and_qualify_leads

Transparent rule-based scoring (fit × engagement) so sales and marketing can agree on
the definition of MQL / hot lead. Weights and thresholds live in the client config and
are starting hypotheses — recalibrate them against actual SQL / won outcomes.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..store import Lead, parse_ts

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

LOCKED_STAGES = {"sql", "opportunity", "customer"}  # owned by sales; scoring never changes them


def _fit(icp: dict[str, Any], ld: Lead) -> tuple[int, dict[str, int]]:
    parts = {"industry": icp["industry_points"].get(ld.industry or "", 0),
             "employee_band": icp["employee_band_points"].get(ld.employee_band or "", 0),
             "job_role": icp["role_points"].get(ld.job_role or "", 0)}
    return sum(parts.values()), parts


def _engagement(rt: "AgentRuntime", ld: Lead, window: int) -> tuple[float, dict[str, float], list[str]]:
    sc = rt.client["scoring"]
    now = rt.now()
    by_type: dict[str, float] = {}
    for e in rt.store.events.get(ld.lead_id, []):
        age = max((now - parse_ts(e["timestamp"])).total_seconds() / 86400, 0.0)  # tolerate small clock skew
        if age > window:
            continue
        pts = sc["engagement_points"].get(e["event_type"], 0)
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + pts * 0.5 ** (age / sc["half_life_days"])
    for t, cap in sc["caps"].items():
        if t in by_type:
            by_type[t] = min(by_type[t], cap)
    flags = []
    evs = rt.store.events.get(ld.lead_id, [])
    recent = lambda t, d: any(e["event_type"] == t and now - parse_ts(e["timestamp"]) <= timedelta(days=d) for e in evs)
    if any(recent(t, window) for t in sc["instant_hot_events"]):
        flags.append("問い合わせ・相談依頼あり")
    combo = sc["high_intent_combo"]
    if all(recent(t, combo["within_days"]) for t in combo["events"]):
        flags.append(f"{combo['within_days']}日以内に料金ページ閲覧＋資料DL")
    return round(sum(by_type.values()), 1), {k: round(v, 1) for k, v in by_type.items() if v}, flags


def _grade(fit: int, eng: float) -> str:
    f = "A" if fit >= 40 else "B" if fit >= 30 else "C" if fit >= 20 else "D"
    e = "1" if eng >= 60 else "2" if eng >= 40 else "3" if eng >= 20 else "4"
    return f + e


def score_and_qualify_leads(rt: "AgentRuntime", lead_ids: list[str] | None = None, analysis_window_days: int = 90,
                            include_account_view: bool = True) -> dict[str, Any]:
    sc, icp = rt.client["scoring"], rt.client["icp"]
    now = rt.now()
    if lead_ids is None:
        lead_ids = [l.lead_id for l in rt.store.leads.values()
                    if l.last_seen and now - parse_ts(l.last_seen) <= timedelta(days=analysis_window_days)]
    unknown = [i for i in lead_ids if i not in rt.store.leads]
    raw = {}
    for lid in [i for i in lead_ids if i in rt.store.leads]:
        ld = rt.store.leads[lid]
        eng, breakdown, flags = _engagement(rt, ld, analysis_window_days)
        raw[lid] = (ld, eng, breakdown, flags)

    accounts: dict[str, dict[str, Any]] = {}
    if include_account_view:
        for ld, *_ in raw.values():
            if ld.account_id and ld.account_id not in accounts:
                contacts = rt.store.account_leads(ld.account_id)
                engaged = [c for c in contacts if _engagement(rt, c, analysis_window_days)[0] > 0]
                accounts[ld.account_id] = {"account_id": ld.account_id, "contacts": len(contacts),
                                           "engaged_contacts": len(engaged),
                                           "account_engagement": round(sum(_engagement(rt, c, analysis_window_days)[0] for c in contacts), 1),
                                           "roles": sorted({c.job_role or "unknown" for c in engaged}),
                                           "buying_committee": len(engaged) >= sc["buying_committee_min_contacts"]}

    results = []
    for lid, (ld, eng, breakdown, flags) in raw.items():
        fit, fit_parts = _fit(icp, ld)
        acct = accounts.get(ld.account_id or "")
        bonus = sc["buying_committee_bonus"] if acct and acct["buying_committee"] else 0
        if bonus:
            flags.append(f"同一企業で{acct['engaged_contacts']}名が関与（購買関与者の広がり）")
        total_eng = eng + bonus
        before = ld.stage
        reason = None
        if ld.job_role in icp["disqualify_roles"] and before not in LOCKED_STAGES:
            new, reason = "disqualified", f"対象外の属性（{ld.job_role}）"
        elif before in LOCKED_STAGES or before == "disqualified":
            new = before
        elif (any("問い合わせ" in f for f in flags) or (fit >= sc["hot"]["fit"] and total_eng >= sc["hot"]["engagement"])
              or (fit >= sc["mql"]["fit"] and any("料金ページ" in f for f in flags))):
            new, reason = "hot", "ホットリード条件に到達"
        elif fit >= sc["mql"]["fit"] and total_eng >= sc["mql"]["engagement"]:
            new, reason = ("mql", "MQL条件に到達") if before != "hot" else ("hot", None)
        else:
            new = before
        changed = ld.set_stage(new, now.isoformat(), reason or "") if reason else False
        action = {"hot": "sales_handoff", "mql": "enroll_nurture_track" if not ld.nurture else "recommend_content",
                  "disqualified": "exclude_from_ads_and_nurture", "recycled": "schedule_recontact"}.get(new, "continue_monitoring")
        ld.score = {"fit": fit, "engagement": round(total_eng, 1), "grade": _grade(fit, total_eng), "as_of": now.isoformat()}
        results.append({"lead_id": lid, "account_id": ld.account_id, "industry": ld.industry, "stage_before": before,
                        "stage": new, "stage_changed": changed, **ld.score,
                        "fit_breakdown": fit_parts, "engagement_breakdown": breakdown, "signals": flags,
                        "recommended_action": action})
        if changed and new in {"mql", "hot"}:
            rt.emit(f"lead_{new}", lead_id=lid)

    results.sort(key=lambda r: (-r["fit"] - r["engagement"]))
    return {"as_of": now.isoformat(), "analysis_window_days": analysis_window_days,
            "model": "rule_based_fit_engagement_v1",
            "note": "スコアは設定した重みによる判定です。受注・商談実績と照らして重みを定期的に見直してください。",
            "thresholds": {"mql": sc["mql"], "hot": sc["hot"]},
            "leads": results, "accounts": list(accounts.values()), "unknown_lead_ids": unknown,
            "summary": {s: sum(r["stage"] == s for r in results) for s in ("hot", "mql", "lead", "disqualified")}}

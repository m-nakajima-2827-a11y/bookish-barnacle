"""④ optimize_lead_gen_campaigns — optimise toward sales-qualified pipeline, not just cheap leads."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..connectors import hash_id
from ..store import parse_ts

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

REACHED_SQL = {"sql", "opportunity", "customer"}


def _reached_sql(ld) -> bool:
    return ld.stage in REACHED_SQL or any(h["to"] in REACHED_SQL for h in ld.stage_history)


def campaign_performance(rt: "AgentRuntime", platform: str, days: int) -> dict[str, dict[str, Any]]:
    now = rt.now()
    agg: dict[str, dict[str, Any]] = {}
    for r in rt.store.ad_stats:
        if r["platform"] != platform or now - parse_ts(r["date"] + "T00:00:00+09:00") > timedelta(days=days):
            continue
        a = agg.setdefault(r["campaign_id"], {"utm_campaign": r.get("utm_campaign"), "cost": 0, "impressions": 0,
                                              "clicks": 0, "platform_leads": 0})
        for k in ("cost", "impressions", "clicks", "platform_leads"):
            a[k] += r.get(k, 0)
    for a in agg.values():
        leads = [l for l in rt.store.leads.values() if l.first_touch and l.first_touch.get("campaign") == a["utm_campaign"]]
        a["crm_leads"] = len(leads)
        a["sql"] = sum(_reached_sql(l) for l in leads)
        a["cpl"] = round(a["cost"] / a["crm_leads"]) if a["crm_leads"] else None
        a["cost_per_sql"] = round(a["cost"] / a["sql"]) if a["sql"] else None
        a["sql_rate"] = round(a["sql"] / a["crm_leads"], 3) if a["crm_leads"] else None
    return agg


def optimize_lead_gen_campaigns(rt: "AgentRuntime", platform: str, action: str, target_segment_id: str | None = None,
                                optimization_metrics: dict[str, float] | None = None) -> dict[str, Any]:
    ad = rt.ad_platforms.get(platform)
    if ad is None:
        return {"error": "platform_not_connected", "platform": platform}
    g, cfg = rt.guardrails, rt.policy["ads"]
    m = optimization_metrics or {}
    base = {"platform": platform, "action": action, "mode": "dry_run" if g.dry_run else "live"}

    if action == "sync_audience_exclusion":
        if not target_segment_id:
            return {**base, "error": "target_segment_id is required (customers / open_opportunities / disqualified / hot_leads)"}
        members = rt.store.segment_members(target_segment_id)
        res = {"segment_id": target_segment_id, "members": len(members), "id_format": "sha256",
               "purpose": "既存顧客・商談中・対象外への広告配信を止め、新規リード獲得に予算を集中"}
        if g.dry_run:
            return {**base, **res, "applied": False}
        return {**base, **res, "applied": True, **ad.upsert_exclusion_audience(target_segment_id, [hash_id(x) for x in members])}

    campaigns = [c for c in ad.get_campaigns() if not target_segment_id or c.get("segment_id") == target_segment_id]

    if action == "update_budget":
        t_sql, t_cpl = m.get("target_cost_per_sql"), m.get("target_cpl")
        if not (t_sql or t_cpl):
            return {**base, "error": "optimization_metrics.target_cost_per_sql or target_cpl is required"}
        perf = campaign_performance(rt, platform, 30)
        total = sum(c["daily_budget"] for c in campaigns)
        raw, held = {}, []
        for c in campaigns:
            p = perf.get(c["campaign_id"])
            ratio = 1.0
            if p and t_sql:
                if p["sql"] >= cfg["min_sql_for_budget_judgement"]:
                    ratio = t_sql / p["cost_per_sql"]
                elif p["crm_leads"] and p["sql"] == 0 and p["cost"] >= t_sql * 2:
                    ratio = 0.5  # spent 2× the target cost per SQL without a single SQL
                else:
                    held.append(c["campaign_id"])
            elif p and t_cpl and p["cpl"]:
                ratio = t_cpl / p["cpl"]
            raw[c["campaign_id"]] = c["daily_budget"] * max(0.5, min(1.5, 1 + (ratio - 1) * 0.5))
        changes = []
        for c in campaigns:
            cid = c["campaign_id"]
            new, approval, note = g.clamp_budget_change(c["daily_budget"], raw[cid])
            if new == c["daily_budget"]:
                continue
            ch = {"campaign_id": cid, "from": c["daily_budget"], "to": new, "performance_30d": perf.get(cid), "note": note}
            if approval:
                ch["status"] = "pending_approval"
                rt.request_approval("set_daily_budget", platform=platform, campaign_id=cid, amount=new)
            elif g.dry_run:
                ch["status"] = "planned"
            else:
                ad.set_daily_budget(cid, new)
                ch["status"] = "applied"
            changes.append(ch)
        after = total + sum(ch["to"] - ch["from"] for ch in changes)
        return {**base, "total_daily_budget_before": total, "total_daily_budget_if_applied": after, "changes": changes,
                "held_for_insufficient_sql": held,
                "basis": ("直近30日の商談化単価（CRMでSQL到達したリードをUTMキャンペーンで紐付け）を目標と比較し、"
                          "キャンペーンごとに増減（SQL不足のキャンペーンは判断保留）" if t_sql else "直近30日のCRMリード単価（CPL）を目標と比較して再配分"),
                "caution": "CPLが安くても商談化しないキャンペーンがあるため、判断は商談化単価を優先してください"}

    if action == "adjust_bidding_strategy":
        target = m.get("target_cpl") or m.get("target_cost_per_sql")
        if not target:
            return {**base, "error": "optimization_metrics.target_cpl or target_cost_per_sql is required"}
        strategy = "target_cpa_on_sql_offline_conversion" if m.get("target_cost_per_sql") else "target_cpa_on_lead"
        perf = campaign_performance(rt, platform, 30)
        changes = []
        for c in campaigns:
            cv = perf.get(c["campaign_id"], {}).get("platform_leads", 0)
            if cv < cfg["min_conversions_for_bid_change"]:
                changes.append({"campaign_id": c["campaign_id"], "status": "skipped",
                                "reason": f"直近30日の媒体CV {cv}件 < 自動入札の学習に必要な{cfg['min_conversions_for_bid_change']}件"})
                continue
            prev = c.get("bidding_strategy")
            if not g.dry_run:
                ad.set_bidding(c["campaign_id"], strategy, target)
            changes.append({"campaign_id": c["campaign_id"], "status": "planned" if g.dry_run else "applied",
                            "from": prev, "to": strategy, "target": target})
        note = ("SQLを最適化対象にするには、CRMのSQL到達をオフラインコンバージョンとして媒体へ送る設定が前提です"
                if strategy.startswith("target_cpa_on_sql") else None)
        return {**base, "changes": changes, "note": note}

    if action == "pause_underperforming_creative":
        paused = []
        for c in campaigns:
            active = {k: v for k, v in c.get("creatives", {}).items() if v.get("status", "active") == "active"}
            eligible = {k: v for k, v in active.items() if v["impressions"] >= cfg["min_impressions_for_creative_pause"]}
            if len(eligible) < 2:
                continue
            avg = sum(v["clicks"] for v in eligible.values()) / sum(v["impressions"] for v in eligible.values())
            remaining = len(active)
            for cr, v in sorted(eligible.items(), key=lambda kv: kv[1]["clicks"] / kv[1]["impressions"]):
                ctr = v["clicks"] / v["impressions"]
                if ctr >= avg * cfg["creative_pause_ctr_ratio_to_avg"] or remaining <= 1:
                    continue
                if not g.dry_run:
                    ad.pause_creative(c["campaign_id"], cr)
                remaining -= 1
                paused.append({"campaign_id": c["campaign_id"], "creative_id": cr, "ctr": round(ctr, 4),
                               "campaign_avg_ctr": round(avg, 4), "status": "planned" if g.dry_run else "applied"})
        return {**base, "paused": paused,
                "rule": f"表示{cfg['min_impressions_for_creative_pause']}回以上かつCTRがキャンペーン平均の"
                        f"{cfg['creative_pause_ctr_ratio_to_avg']:.0%}未満（最後の1本は停止しない）"}

    return {**base, "error": f"unsupported action {action}"}

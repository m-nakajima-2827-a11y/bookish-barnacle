"""③ optimize_ad_and_social_campaigns"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..cdp import parse_ts
from ..connectors import hash_id

if TYPE_CHECKING:
    from ..runtime import AgentRuntime


def _perf(rt: "AgentRuntime", platform: str, days: int) -> dict[str, dict[str, float]]:
    now = rt.now()
    agg: dict[str, dict[str, float]] = {}
    for r in rt.store.ad_spend:
        if r["platform"] != platform or now - parse_ts(r["date"] + "T00:00:00+09:00") > timedelta(days=days):
            continue
        a = agg.setdefault(r["campaign_id"], {"cost": 0, "conversions": 0, "revenue": 0, "clicks": 0, "impressions": 0})
        for k in a:
            a[k] += r.get(k, 0)
    for a in agg.values():
        a["roas"] = round(a["revenue"] / a["cost"], 2) if a["cost"] else 0.0
        a["cpa"] = round(a["cost"] / a["conversions"]) if a["conversions"] else None
    return agg


def optimize_ad_and_social_campaigns(rt: "AgentRuntime", platform: str, action: str, target_segment_id: str | None = None,
                                     optimization_metrics: dict[str, float] | None = None) -> dict[str, Any]:
    ad = rt.ad_platforms.get(platform)
    if ad is None:
        return {"error": "platform_not_connected", "platform": platform}
    g = rt.guardrails
    metrics = optimization_metrics or {}
    base = {"platform": platform, "action": action, "mode": "dry_run" if g.dry_run else "live"}

    if action == "sync_audience_exclusion":
        if not target_segment_id:
            return {**base, "error": "target_segment_id is required for sync_audience_exclusion"}
        members = rt.store.segment_members(target_segment_id)
        hashed = [hash_id(m) for m in members]
        result = {"segment_id": target_segment_id, "members": len(members), "id_format": "sha256"}
        if g.dry_run:
            return {**base, **result, "applied": False}
        return {**base, **result, "applied": True, **ad.upsert_exclusion_audience(target_segment_id, hashed)}

    campaigns = [c for c in ad.get_campaigns() if not target_segment_id or c.get("segment_id") == target_segment_id]

    if action == "update_budget":
        target_roas, max_cpa = metrics.get("target_roas"), metrics.get("max_cpa")
        if not (target_roas or max_cpa):
            return {**base, "error": "optimization_metrics.target_roas or max_cpa is required for update_budget"}
        perf = _perf(rt, platform, 7)
        total = sum(c["daily_budget"] for c in campaigns)
        raw = {}
        for c in campaigns:
            p = perf.get(c["campaign_id"])
            if not p or not p["cost"]:
                ratio = 1.0
            elif target_roas:
                ratio = p["roas"] / target_roas
            else:
                ratio = (max_cpa / p["cpa"]) if p["cpa"] else 0.5
            raw[c["campaign_id"]] = c["daily_budget"] * max(0.5, min(1.5, 1 + (ratio - 1) * 0.5))
        scale = total / sum(raw.values()) if raw else 1
        changes = []
        for c in campaigns:
            cid = c["campaign_id"]
            new, needs_approval, note = g.clamp_budget_change(c["daily_budget"], raw[cid] * scale)
            if new == c["daily_budget"]:
                continue
            ch = {"campaign_id": cid, "from": c["daily_budget"], "to": new, "performance_7d": perf.get(cid), "note": note}
            if needs_approval:
                ch["status"] = "pending_approval"
                rt.request_approval("set_daily_budget", platform=platform, campaign_id=cid, amount=new)
            elif g.dry_run:
                ch["status"] = "planned"
            else:
                ad.set_daily_budget(cid, new)
                ch["status"] = "applied"
            changes.append(ch)
        return {**base, "total_daily_budget_before": total, "changes": changes,
                "basis": "直近7日ROAS/CPAを目標値と比較し、総額一定で再配分（変更幅は上限内に補正）"}

    if action == "adjust_bidding_strategy":
        if not (metrics.get("target_roas") or metrics.get("max_cpa")):
            return {**base, "error": "optimization_metrics.target_roas or max_cpa is required for adjust_bidding_strategy"}
        strategy = "target_roas" if metrics.get("target_roas") else "target_cpa"
        perf = _perf(rt, platform, 30)
        min_cv = rt.policy["ads"]["min_conversions_for_bid_change"]
        changes = []
        for c in campaigns:
            cv = perf.get(c["campaign_id"], {}).get("conversions", 0)
            if cv < min_cv:
                changes.append({"campaign_id": c["campaign_id"], "status": "skipped",
                                "reason": f"直近30日CV {cv:.0f}件 < 学習に必要な{min_cv}件"})
                continue
            status = "planned" if g.dry_run else "applied"
            previous = c.get("bidding_strategy")
            if not g.dry_run:
                ad.set_bidding(c["campaign_id"], strategy, metrics.get("target_roas"), metrics.get("max_cpa"))
            changes.append({"campaign_id": c["campaign_id"], "status": status, "strategy": strategy,
                            "from": previous, "target_roas": metrics.get("target_roas"),
                            "target_cpa": metrics.get("max_cpa")})
        return {**base, "changes": changes}

    if action == "pause_underperforming_creative":
        cfg = rt.policy["ads"]
        paused = []
        for c in campaigns:
            active = {k: v for k, v in c.get("creatives", {}).items() if v.get("status", "active") == "active"}
            eligible = {k: v for k, v in active.items() if v["impressions"] >= cfg["min_impressions_for_creative_pause"]}
            if len(eligible) < 2:
                continue
            avg_ctr = sum(v["clicks"] for v in eligible.values()) / sum(v["impressions"] for v in eligible.values())
            remaining = len(active)
            for cr_id, v in sorted(eligible.items(), key=lambda kv: kv[1]["clicks"] / kv[1]["impressions"]):
                ctr = v["clicks"] / v["impressions"]
                if ctr >= avg_ctr * cfg["creative_pause_ctr_ratio_to_avg"] or remaining <= 1:
                    continue
                if not g.dry_run:
                    ad.pause_creative(c["campaign_id"], cr_id)
                remaining -= 1
                paused.append({"campaign_id": c["campaign_id"], "creative_id": cr_id, "ctr": round(ctr, 4),
                               "campaign_avg_ctr": round(avg_ctr, 4), "status": "planned" if g.dry_run else "applied"})
        return {**base, "paused": paused,
                "rule": f"表示{cfg['min_impressions_for_creative_pause']}回以上かつCTRがキャンペーン平均の"
                        f"{cfg['creative_pause_ctr_ratio_to_avg']:.0%}未満（最後の1本は停止しない）"}

    return {**base, "error": f"unsupported action {action}"}

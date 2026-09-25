"""⑤ generate_omnichannel_attribution_report

Rule-based multi-touch attribution computed from CDP-joined touchpoints, with POS
sales included as conversions. `data_driven_mta` and `mmm` need an external
analysis backend (e.g. Shapley/Markov MTA job, Meridian/Robyn MMM); until one is
connected the report falls back to `position_based` and says so explicitly.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ..cdp import parse_ts

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

EXTERNAL_MODELS = {"data_driven_mta", "mmm"}
HALF_LIFE_DAYS = 7
MIN_CONVERSIONS_FOR_BUDGET_ADVICE = 30


def _touch_channel(e: dict[str, Any]) -> str:
    if e["event_type"] == "ad_click" and e["payload"].get("platform"):
        return e["payload"]["platform"]
    return e["channel"]


def _weights(model: str, touches: list[dict[str, Any]], conv_ts: datetime) -> list[float]:
    n = len(touches)
    if model == "last_touch":
        return [0.0] * (n - 1) + [1.0]
    if model == "first_touch":
        return [1.0] + [0.0] * (n - 1)
    if model == "linear":
        return [1 / n] * n
    if model == "time_decay":
        raw = [0.5 ** ((conv_ts - parse_ts(t["timestamp"])).total_seconds() / 86400 / HALF_LIFE_DAYS) for t in touches]
        s = sum(raw)
        return [r / s for r in raw]
    # position_based (40/20/40)
    if n == 1:
        return [1.0]
    if n == 2:
        return [0.5, 0.5]
    mid = 0.2 / (n - 2)
    return [0.4] + [mid] * (n - 2) + [0.4]


def generate_omnichannel_attribution_report(rt: "AgentRuntime", period_start: str, period_end: str, attribution_model: str,
                                            lookback_window_days: int = 30, channels: list[str] | None = None,
                                            include_offline_sales: bool = True, output_format: str = "markdown") -> dict[str, Any]:
    tz = rt.guardrails.tz
    start = datetime.combine(date.fromisoformat(period_start), time.min, tz)
    end = datetime.combine(date.fromisoformat(period_end), time.min, tz) + timedelta(days=1)
    notes = []
    model = attribution_model
    if model in EXTERNAL_MODELS:
        notes.append(f"{model} は外部分析基盤が未接続のため、position_based（40/20/40）で代替算出しています。")
        model = "position_based"

    credit: dict[str, dict[str, float]] = {}
    conversions, revenue_total, offline_only = 0, 0.0, 0
    for cid, events in rt.store.events.items():
        for i, conv in enumerate(events):
            if conv["event_type"] != "store_purchase":
                continue
            ts = parse_ts(conv["timestamp"])
            if not (start <= ts < end):
                continue
            if not include_offline_sales and conv["channel"] == "physical_store_pos":
                continue
            amount = float(conv["payload"].get("amount", 0))
            conversions += 1
            revenue_total += amount
            touches = [e for e in events[:i] if e["event_type"] != "store_purchase"
                       and ts - parse_ts(e["timestamp"]) <= timedelta(days=lookback_window_days)
                       and (not channels or _touch_channel(e) in channels)]
            if not touches:
                offline_only += 1
                touches, weights = [conv], [1.0]
                label = [f"{conv['channel']}（接点なし・直接）"]
            else:
                weights = _weights(model, touches, ts)
                label = [_touch_channel(t) for t in touches]
            for ch, w in zip(label, weights):
                c = credit.setdefault(ch, {"conversions": 0.0, "revenue": 0.0})
                c["conversions"] += w
                c["revenue"] += w * amount

    spend: dict[str, float] = {}
    reported: dict[str, float] = {}
    for r in rt.store.ad_spend:
        d = parse_ts(r["date"] + "T00:00:00+09:00")
        if start <= d < end and (not channels or r["platform"] in channels):
            spend[r["platform"]] = spend.get(r["platform"], 0) + r["cost"]
            reported[r["platform"]] = reported.get(r["platform"], 0) + r.get("revenue", 0)

    rows = []
    for ch, c in sorted(credit.items(), key=lambda kv: -kv[1]["revenue"]):
        cost = spend.get(ch)
        rows.append({"channel": ch, "attributed_conversions": round(c["conversions"], 2),
                     "attributed_revenue": round(c["revenue"]),
                     "revenue_share": round(c["revenue"] / revenue_total, 3) if revenue_total else 0,
                     "ad_cost": round(cost) if cost is not None else None,
                     "attributed_roas": round(c["revenue"] / cost, 2) if cost else None,
                     "platform_reported_roas": round(reported[ch] / cost, 2) if cost else None})
    for platform, cost in spend.items():
        if platform not in credit:
            rows.append({"channel": platform, "attributed_conversions": 0, "attributed_revenue": 0,
                         "revenue_share": 0, "ad_cost": round(cost), "attributed_roas": 0.0,
                         "platform_reported_roas": round(reported[platform] / cost, 2)})

    recs = []
    if spend and conversions < MIN_CONVERSIONS_FOR_BUDGET_ADVICE:
        recs.append({"priority": "高", "channel": "計測基盤",
                     "action": "CDPで紐付いたCVが少なく、貢献ベースROASでの予算判断は保留。会員ID連携率・広告クリックIDの取得状況を先に確認",
                     "evidence": f"紐付CV {conversions}件（判断目安 {MIN_CONVERSIONS_FOR_BUDGET_ADVICE}件以上）、"
                                 "媒体報告ROASとの乖離あり" if any(r.get("platform_reported_roas") for r in rows) else
                                 f"紐付CV {conversions}件"})
    for r in rows if conversions >= MIN_CONVERSIONS_FOR_BUDGET_ADVICE else []:
        if r["attributed_roas"] is not None and r["attributed_roas"] < 1:
            recs.append({"priority": "高", "channel": r["channel"],
                         "action": "予算の縮小またはターゲティング・クリエイティブの見直し",
                         "evidence": f"貢献ベースROAS {r['attributed_roas']}（費用 {r['ad_cost']:,}円）"})
        elif r["attributed_roas"] is not None and r["attributed_roas"] >= 3:
            recs.append({"priority": "中", "channel": r["channel"],
                         "action": "予算増額の検討（日次変更幅の上限内で段階的に）",
                         "evidence": f"貢献ベースROAS {r['attributed_roas']}"})
    if conversions and offline_only / conversions >= 0.3:
        recs.append({"priority": "高", "channel": "physical_store_pos",
                     "action": "店頭での会員ID提示率向上（アプリ会員証・レシート連携）でオンライン接点との紐付けを強化",
                     "evidence": f"デジタル接点が紐付かない購買が {offline_only}/{conversions} 件"})
    if conversions < 30:
        notes.append(f"コンバージョン数が{conversions}件と少ないため、配分結果は参考値として扱ってください。")

    report = {"period": {"start": period_start, "end": period_end}, "attribution_model": model,
              "requested_model": attribution_model, "lookback_window_days": lookback_window_days,
              "include_offline_sales": include_offline_sales,
              "totals": {"conversions": conversions, "revenue": round(revenue_total), "ad_cost": round(sum(spend.values())),
                         "conversions_without_digital_touch": offline_only},
              "channels": rows, "recommendations": recs, "notes": notes}
    if output_format == "markdown":
        report["markdown"] = _to_markdown(report)
    return report


def _to_markdown(r: dict[str, Any]) -> str:
    t = r["totals"]
    lines = [f"# オムニチャネル・アトリビューションレポート（{r['period']['start']}〜{r['period']['end']}）", "",
             f"- モデル: {r['attribution_model']}（要求: {r['requested_model']}）/ ルックバック {r['lookback_window_days']}日",
             f"- CV {t['conversions']}件 / 売上 {t['revenue']:,}円 / 広告費 {t['ad_cost']:,}円 / デジタル接点なしCV {t['conversions_without_digital_touch']}件",
             "", "## チャネル別貢献", "",
             "| チャネル | 貢献CV | 貢献売上(円) | 売上構成比 | 広告費(円) | 貢献ROAS | 媒体報告ROAS |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for c in r["channels"]:
        cost = f"{c['ad_cost']:,}" if c["ad_cost"] is not None else "-"
        roas = c["attributed_roas"] if c["attributed_roas"] is not None else "-"
        rep = c.get("platform_reported_roas") if c.get("platform_reported_roas") is not None else "-"
        lines.append(f"| {c['channel']} | {c['attributed_conversions']} | {c['attributed_revenue']:,} | "
                     f"{c['revenue_share']:.1%} | {cost} | {roas} | {rep} |")
    lines += ["", "## 改善提案", ""]
    lines += [f"- [{x['priority']}] {x['channel']}: {x['action']}（根拠: {x['evidence']}）" for x in r["recommendations"]] or ["- 該当なし"]
    if r["notes"]:
        lines += ["", "## 注記", ""] + [f"- {n}" for n in r["notes"]]
    return "\n".join(lines)

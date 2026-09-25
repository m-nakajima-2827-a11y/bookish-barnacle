"""⑦ analyze_marketing_funnel — GA4 × Search Console × MA/CRM.

Joins sessions (GA4), queries (Search Console) and lead lifecycle (MA/CRM) on UTM values,
so a campaign can be judged on pipeline created, not just traffic or leads.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ..store import Lead, parse_ts, touch_from_event
from ..utm import channel_group, check_value

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

FUNNEL = ["leads", "mql", "hot", "sql", "opportunities", "won"]
REACH = {"mql": {"mql", "hot", "sql", "opportunity", "customer"}, "hot": {"hot", "sql", "opportunity", "customer"},
         "sql": {"sql", "opportunity", "customer"}, "opportunities": {"opportunity", "customer"}, "won": {"customer"}}


def _reached(ld: Lead) -> set[str]:
    seen = {h["to"] for h in ld.stage_history} | {ld.stage}
    out = {k for k, stages in REACH.items() if seen & stages}
    if ld.opportunity:
        out.add("opportunities")
    return out


def _key(group_by: str, source, medium, campaign, landing_page, industry=None) -> str:
    if group_by == "channel_group":
        return channel_group(source, medium)
    if group_by == "source_medium":
        return f"{source or '(direct)'} / {medium or '(none)'}"
    if group_by == "campaign":
        return campaign or "(not set)"
    if group_by == "landing_page":
        return landing_page or "(not set)"
    return industry or "(unknown)"


def _lead_key(group_by: str, ld: Lead) -> str:
    t = ld.first_touch or {}
    return _key(group_by, t.get("source"), t.get("medium"), t.get("campaign"), t.get("landing_page"), ld.industry)


def _weights(model: str, n: int) -> list[float]:
    if model == "first_touch":
        return [1.0] + [0.0] * (n - 1)
    if model == "last_touch":
        return [0.0] * (n - 1) + [1.0]
    if model == "linear" or n <= 2:
        return [1 / n] * n
    return [0.4] + [0.2 / (n - 2)] * (n - 2) + [0.4]


def analyze_marketing_funnel(rt: "AgentRuntime", period_start: str, period_end: str, group_by: str,
                             attribution_model: str = "first_touch", include_search_console: bool = True,
                             output_format: str = "markdown") -> dict[str, Any]:
    tz, cfg = rt.guardrails.tz, rt.policy["analysis"]
    start = datetime.combine(date.fromisoformat(period_start), time.min, tz)
    end = datetime.combine(date.fromisoformat(period_end), time.min, tz) + timedelta(days=1)
    in_period = lambda ts: start <= ts < end
    day_in = lambda d: in_period(datetime.combine(date.fromisoformat(d), time.min, tz))
    rows: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # GA4 sessions (not available by industry)
    for r in rt.store.ga4_sessions:
        if day_in(r["date"]) and group_by != "industry":
            row = rows[_key(group_by, r["source"], r["medium"], r["campaign"], r["landing_page"])]
            for k in ("sessions", "engaged_sessions", "key_events"):
                row[k] += r.get(k, 0)

    # Lead funnel: cohort = leads first seen in period
    cohort = [l for l in rt.store.leads.values() if l.first_seen and in_period(parse_ts(l.first_seen))]
    for ld in cohort:
        row = rows[_lead_key(group_by, ld)]
        row["leads"] += 1
        for k in _reached(ld):
            row[k] += 1
        if ld.opportunity and ld.opportunity.get("status") == "won":
            row["won_amount"] += ld.opportunity["amount"]

    # Pipeline attribution across touches before the opportunity was created
    for ld in cohort:
        if not ld.opportunity:
            continue
        created = parse_ts(ld.opportunity["created_at"])
        touches = [touch_from_event(e) for e in rt.store.events[ld.lead_id]
                   if parse_ts(e["timestamp"]) <= created and (e["payload"].get("utm") or e["payload"].get("landing_page"))]
        keys = ([_key(group_by, t["source"], t["medium"], t["campaign"], t["landing_page"], ld.industry) for t in touches]
                or [_lead_key(group_by, ld)])
        for k, w in zip(keys, _weights(attribution_model, len(keys))):
            rows[k]["pipeline_amount"] += w * ld.opportunity["amount"]

    # Ad cost
    for r in rt.store.ad_stats:
        if day_in(r["date"]) and group_by != "industry":
            k = _key(group_by, r.get("utm_source"), r.get("utm_medium"), r.get("utm_campaign"), r.get("landing_page"))
            rows[k]["cost"] += r["cost"]

    table = []
    for k, r in rows.items():
        s, leads = r.get("sessions", 0), r.get("leads", 0)
        table.append({"group": k, "sessions": int(s),
                      "engagement_rate": round(r["engaged_sessions"] / s, 3) if s else None,
                      "key_events": int(r.get("key_events", 0)),
                      "cvr": round(r["key_events"] / s, 4) if s else None,
                      **{f: int(r.get(f, 0)) for f in FUNNEL},
                      "sql_rate": round(r.get("sql", 0) / leads, 3) if leads else None,
                      "pipeline_amount": round(r.get("pipeline_amount", 0)), "won_amount": round(r.get("won_amount", 0)),
                      "cost": round(r.get("cost", 0)) if r.get("cost") else None,
                      "cpl": round(r["cost"] / leads) if r.get("cost") and leads else None,
                      "cost_per_sql": round(r["cost"] / r["sql"]) if r.get("cost") and r.get("sql") else None})
    table.sort(key=lambda x: (-x["pipeline_amount"], -x["leads"], -x["sessions"]))
    totals = {f: sum(t[f] for t in table) for f in ["sessions", "key_events", *FUNNEL, "pipeline_amount", "won_amount"]}
    totals["cost"] = sum(t["cost"] or 0 for t in table)

    hygiene = _utm_hygiene(rt, day_in)
    sla = _sla(rt, in_period)
    sc = _search_console(rt, day_in, start, end) if include_search_console else None
    recs = _recommendations(rt, table, hygiene, sla, sc, totals)

    recs = [r for r in recs if r["area"] != "LP改善" or group_by in {"landing_page", "campaign"}]
    report = {"period": {"start": period_start, "end": period_end}, "group_by": group_by,
              "attribution_model": attribution_model, "totals": totals, "rows": table,
              "utm_hygiene": hygiene, "first_contact_sla": sla, "search_console": sc, "recommendations": recs,
              "notes": ["リードは期間内に初回接点があったリードを集計（コホート）。商談・受注は集計時点までの到達を含みます。",
                        "GA4のキーイベント数とMA上のリード数は、重複DLや計測方式の違いで一致しない場合があります。"]}
    if totals["leads"] < cfg["min_leads_for_rate_judgement"] * 2:
        report["notes"].append(f"リード数が{totals['leads']}件と少ないため、率の比較は参考値です。")
    if output_format == "markdown":
        report["markdown"] = _markdown(report)
    return report


def _utm_hygiene(rt, day_in) -> list[dict[str, Any]]:
    issues, seen = [], defaultdict(set)
    values = [(r["source"], r["medium"], r["campaign"], r.get("sessions", 0), r["landing_page"])
              for r in rt.store.ga4_sessions if day_in(r["date"])]
    for src, med, camp, sessions, lp in values:
        for name, v in (("source", src), ("medium", med), ("campaign", camp)):
            if v and not v.startswith("("):
                seen[(name, v.lower())].add(v)
                for e in check_value(f"utm_{name}", v):
                    issues.append({"type": "naming", "value": v, "detail": e, "sessions": sessions})
        if lp and lp.startswith("/lp/") and (not camp or camp == "(not set)") and src in {"(direct)", None}:
            issues.append({"type": "missing_utm", "value": lp, "sessions": sessions,
                           "detail": "キャンペーンLPへの流入にUTMがなく、参照元が不明（direct）です。告知リンクにUTMを付与してください"})
    for (name, low), variants in seen.items():
        if len(variants) > 1:
            issues.append({"type": "case_variants", "value": low, "detail": f"{name} の表記ゆれ: {sorted(variants)}（別集計になっています）"})
    allowed = rt.client["utm_dictionary"]["allowed_mediums_by_source"]
    for src, med, camp, sessions, _ in values:
        tagged = camp and not camp.startswith("(")  # only UTM-tagged links are ours to fix
        if tagged and src and src.lower() in allowed and med and med.lower() not in allowed[src.lower()]:
            issues.append({"type": "medium_mismatch", "value": f"{src} / {med}", "sessions": sessions,
                           "detail": f"命名辞書では {src.lower()} の medium は {allowed[src.lower()]} のいずれかです（'{med}' は集計が分散）"})
    merged: dict[tuple, dict[str, Any]] = {}
    for i in issues:
        k = (i["type"], i["value"], i["detail"])
        if k in merged:
            merged[k]["sessions"] = merged[k].get("sessions", 0) + i.get("sessions", 0)
        else:
            merged[k] = dict(i)
    return list(merged.values())


def _sla(rt, in_period) -> dict[str, Any]:
    sla = rt.policy["sales_handoff"]["first_contact_sla_minutes"]
    mins, not_contacted = [], 0
    for ld in rt.store.leads.values():
        h = ld.handoff
        if not h or not in_period(parse_ts(h["at"])):
            continue
        if h.get("first_contact_at"):
            mins.append((parse_ts(h["first_contact_at"]) - parse_ts(h["at"])).total_seconds() / 60)
        else:
            not_contacted += 1
    return {"handoffs": len(mins) + not_contacted, "median_minutes": round(statistics.median(mins)) if mins else None,
            "over_sla": sum(m > sla for m in mins), "not_contacted": not_contacted, "sla_minutes": sla,
            "note": "経過時間は暦時間で計算（営業時間外を含む）"}


def _search_console(rt, day_in, start, end) -> dict[str, Any]:
    brands = [b.lower() for b in rt.client["brand_queries"]]
    rows = [r for r in rt.store.gsc_queries if day_in(r["date"])]
    mid = start + (end - start) / 2
    halves = {"first_half": 0, "second_half": 0}
    agg: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        is_brand = any(b in r["query"].lower() for b in brands)
        if is_brand:
            d = datetime.combine(date.fromisoformat(r["date"]), time.min, rt.guardrails.tz)
            halves["first_half" if d < mid else "second_half"] += r["clicks"]
        a = agg[r["query"]]
        a["clicks"] += r["clicks"]
        a["impressions"] += r["impressions"]
        a["pos_x_impr"] += r["position"] * r["impressions"]
        a["brand"] = is_brand
    queries = [{"query": q, "clicks": int(a["clicks"]), "impressions": int(a["impressions"]),
                "ctr": round(a["clicks"] / a["impressions"], 4) if a["impressions"] else 0,
                "avg_position": round(a["pos_x_impr"] / a["impressions"], 1) if a["impressions"] else None,
                "brand": bool(a["brand"])} for q, a in agg.items()]
    growth = ((halves["second_half"] - halves["first_half"]) / halves["first_half"]) if halves["first_half"] else None
    opportunities = sorted([q for q in queries if not q["brand"] and q["avg_position"] and q["avg_position"] <= 10
                            and q["impressions"] >= 100 and q["ctr"] < 0.02], key=lambda q: -q["impressions"])[:5]
    return {"brand_clicks": halves, "brand_growth": round(growth, 3) if growth is not None else None,
            "top_queries": sorted(queries, key=lambda q: -q["clicks"])[:10], "ctr_improvement_candidates": opportunities}


def _recommendations(rt, table, hygiene, sla, sc, totals) -> list[dict[str, str]]:
    cfg, recs = rt.policy["analysis"], []
    for r in table:
        if r["leads"] >= cfg["min_leads_for_rate_judgement"] and (r["sql_rate"] or 0) < cfg["low_sql_rate"]:
            recs.append({"priority": "高", "area": "商談化", "target": r["group"],
                         "issue": f"リード{r['leads']}件に対しSQL{r['sql']}件（{(r['sql_rate'] or 0):.0%}）",
                         "action": "流入テーマと資料の対象者がずれていないか確認し、ナーチャリング（事例→セミナー→診断）とホットリード条件を見直す"})
        if r["sessions"] >= cfg["lp_min_sessions"] and r["cvr"] is not None and r["cvr"] < cfg["lp_low_cvr"]:
            recs.append({"priority": "中", "area": "LP改善", "target": r["group"],
                         "issue": f"{r['sessions']}セッションでCVR {r['cvr']:.2%}",
                         "action": "ファーストビューの訴求を流入元（投稿・広告）と揃え、フォーム項目を必要最小限にする"})
        if r["cost"] and r["leads"] and not r["sql"] and r["cost"] >= 100000:
            recs.append({"priority": "高", "area": "広告", "target": r["group"],
                         "issue": f"広告費{r['cost']:,}円・リード{r['leads']}件・SQL0件",
                         "action": "CPLではなく商談化単価で評価し、ターゲティング・訴求を見直すか予算を商談化している施策へ移す"})
    if sla["median_minutes"] is not None and sla["median_minutes"] > sla["sla_minutes"] or sla["not_contacted"]:
        recs.append({"priority": "高", "area": "インサイドセールス", "target": "初回接触",
                     "issue": f"引き渡し{sla['handoffs']}件：初回接触までの中央値{sla['median_minutes']}分、期限超過{sla['over_sla']}件、未接触{sla['not_contacted']}件",
                     "action": f"ホットリード発生時の通知と担当割当を自動化し、{sla['sla_minutes']}分以内の初回接触を徹底する"})
    for h in hygiene:
        if h["type"] in {"case_variants", "missing_utm", "naming", "medium_mismatch"}:
            recs.append({"priority": "中", "area": "計測", "target": h["value"], "issue": h["detail"],
                         "action": "build_utm_tracking_url で作成したURLに統一する"})
    if sc and sc["brand_growth"] is not None and sc["brand_growth"] >= cfg["brand_search_growth_alert"]:
        recs.append({"priority": "低", "area": "認知", "target": "指名検索",
                     "issue": f"指名検索クリックが期間後半に{sc['brand_growth']:.0%}増加",
                     "action": "SNS・事例発信の効果の可能性（仮説）。同時期の施策と照らして継続判断する"})
    for q in (sc or {}).get("ctr_improvement_candidates", []):
        recs.append({"priority": "中", "area": "SEO", "target": q["query"],
                     "issue": f"平均{q['avg_position']}位・表示{q['impressions']}回でCTR {q['ctr']:.1%}",
                     "action": "該当ページのタイトル・説明文を検索意図に合わせて改善"})
    order = {"高": 0, "中": 1, "低": 2}
    return sorted(recs, key=lambda r: order[r["priority"]])


def _markdown(r: dict[str, Any]) -> str:
    t = r["totals"]
    L = [f"# マーケティングファネル分析（{r['period']['start']}〜{r['period']['end']}）", "",
         f"- 集計軸: {r['group_by']} / 商談金額の配分: {r['attribution_model']}",
         f"- セッション {t['sessions']:,} / キーイベント {t['key_events']} / リード {t['leads']} / MQL {t['mql']} / "
         f"ホット {t['hot']} / SQL {t['sql']} / 商談 {t['opportunities']} / 受注 {t['won']}",
         f"- 商談金額 {t['pipeline_amount']:,}円 / 受注金額 {t['won_amount']:,}円 / 広告費 {t['cost']:,}円", "",
         "## ファネル", "",
         "| 区分 | セッション | CVR | リード | MQL | SQL | 商談 | 受注 | SQL率 | 商談金額(円) | 広告費(円) | 商談化単価(円) |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    fmt = lambda v, f="{:,}": "-" if v is None else f.format(v)
    for x in r["rows"]:
        L.append(f"| {x['group']} | {x['sessions']:,} | {fmt(x['cvr'], '{:.2%}')} | {x['leads']} | {x['mql']} | {x['sql']} | "
                 f"{x['opportunities']} | {x['won']} | {fmt(x['sql_rate'], '{:.0%}')} | {x['pipeline_amount']:,} | "
                 f"{fmt(x['cost'])} | {fmt(x['cost_per_sql'])} |")
    s = r["first_contact_sla"]
    L += ["", "## 初回接触（インサイドセールス）", "",
          f"- 引き渡し {s['handoffs']}件 / 中央値 {fmt(s['median_minutes'])}分 / {s['sla_minutes']}分超過 {s['over_sla']}件 / 未接触 {s['not_contacted']}件"]
    if r["search_console"]:
        sc = r["search_console"]
        L += ["", "## 検索（サーチコンソール）", "",
              f"- 指名検索クリック: 前半 {sc['brand_clicks']['first_half']} → 後半 {sc['brand_clicks']['second_half']}"
              + (f"（{sc['brand_growth']:+.0%}）" if sc["brand_growth"] is not None else "")]
        L += [f"- CTR改善候補: {q['query']}（{q['avg_position']}位・CTR {q['ctr']:.1%}）" for q in sc["ctr_improvement_candidates"]]
    L += ["", "## UTM・計測の点検", ""]
    L += [f"- [{h['type']}] {h['value']}: {h['detail']}" for h in r["utm_hygiene"]] or ["- 問題なし"]
    L += ["", "## 改善提案", ""]
    L += [f"- [{x['priority']}] {x['area']}｜{x['target']}: {x['issue']} → {x['action']}" for x in r["recommendations"]] or ["- 該当なし"]
    L += ["", "## 注記", ""] + [f"- {n}" for n in r["notes"]]
    return "\n".join(L)

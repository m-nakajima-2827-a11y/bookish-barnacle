"""Command line entry point: `python -m dm_agent <command>`."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

from .connectors import MockAdPlatform
from .registry import ROOT, load_schemas, to_anthropic, to_openai
from .runtime import DEFAULT_CLIENT, AgentRuntime
from .store import LeadStore
from .workflow import install_default_playbook

STATE_DIR = ROOT / "state"
SCENARIO = ROOT / "examples" / "scenario_btob_sales_consulting.json"


def build_runtime(scenario: dict, live_mocks: bool) -> AgentRuntime:
    rt = AgentRuntime(client_id=scenario["client_id"], now=datetime.fromisoformat(scenario["start_at"]))
    if live_mocks:
        # Mocks only record calls, so "live" is safe here and shows the full effect of each step.
        rt.policy = copy.deepcopy(rt.policy)
        rt.policy["execution_mode"] = "live"
        rt.guardrails.policy = rt.policy
    rt.ad_platforms = {p: MockAdPlatform(p, copy.deepcopy(c)) for p, c in scenario["campaigns"].items()}
    rt.store.ad_stats = list(scenario["ad_stats"])
    rt.store.ga4_sessions = list(scenario["ga4_sessions"])
    rt.store.gsc_queries = list(scenario["gsc_queries"])
    for h in scenario["history"]:
        rt.store.ingest(h["lead_id"], h["touchpoints"], account=h.get("account"), consent=h.get("consent"))
    rt.execute("score_and_qualify_leads", {}, origin="setup")  # baseline stages before the playbook is live
    return rt


def _p(title: str, obj) -> None:
    print(f"\n=== {title} ===")
    print(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _brief(r: dict, keys: tuple[str, ...]) -> dict:
    return {k: r[k] for k in keys if k in r}


def cmd_demo(args) -> None:
    sc = json.loads(SCENARIO.read_text(encoding="utf-8"))
    rt = build_runtime(sc, live_mocks=not args.dry_run)
    install_default_playbook(rt)
    live = sc["live"]
    ts = lambda k: max(datetime.fromisoformat(t["timestamp"]) for t in live[k]["touchpoints"])
    print(f"クライアント: {rt.client['name']} / 実行モード: {'dry_run' if rt.guardrails.dry_run else 'live（モック接続）'}")

    _p("STEP0 Instagramプロフィール用のUTM付きURL", _brief(rt.execute("build_utm_tracking_url", {
        "base_url": "https://example.com/lp/mfg-checksheet", "utm_source": "instagram", "utm_medium": "social",
        "utm_campaign": "mfg_paper", "placement": "instagram_profile", "target_industry": "manufacturing"}),
        ("status", "url", "predicted_ga4_channel_group", "warnings", "tip")))
    _p("STEP0' 命名ルール違反の例（大文字・日本語）", _brief(rt.execute("build_utm_tracking_url", {
        "base_url": "https://example.com/lp/mfg-checksheet", "utm_source": "Instagram", "utm_medium": "social",
        "utm_campaign": "製造業資料", "placement": "instagram_story"}), ("status", "errors", "suggested_url", "needs_manual_fix")))

    rt.advance_to(ts("step1_download"))
    _p("STEP1 9/7(月)20:30 Instagram経由で資料DL → 自動スコアリング → MQL → 製造業向け育成シナリオ登録",
       rt.execute("sync_lead_activity", live["step1_download"])["signals"])
    lead = rt.store.leads["L101"]
    print(f"  L101: stage={lead.stage} score={lead.score} nurture={lead.nurture}")
    _p("  育成メールの予約（営業時間外のため初回は翌朝9:00）", rt.pending_jobs()[:5])

    ran = rt.advance_to(datetime.fromisoformat("2026-09-08T09:05:00+09:00"))
    _p("STEP2 9/8(火)9:00 初回メール送信", [_brief(r["result"], ("status", "asset_id", "message")) for r in ran])

    rt.advance_to(ts("step3_high_intent"))
    rt.execute("sync_lead_activity", live["step3_high_intent"])
    task = next((t for t in rt.crm.tasks if t["lead_id"] == "L101"), None)
    _p("STEP3 9/10 ウェビナー参加＋料金ページ閲覧 → ホットリード → インサイドセールスへ引き渡し（30分ルール）",
       {"stage": lead.stage, "score": lead.score, "crm_task": task})

    rt.advance_to(ts("step4_first_contact"))
    rt.execute("sync_lead_activity", live["step4_first_contact"])
    print(f"  初回接触: {lead.handoff}")

    rt.advance_to(ts("step5_meeting"))
    rt.execute("sync_lead_activity", live["step5_meeting"])
    _p("STEP4 9/14 商談設定 → 広告の除外（商談中・既存顧客）", {
        name: {"audiences": {k: len(v) for k, v in ad.audiences.items()}} for name, ad in rt.ad_platforms.items()})

    rt.advance_to(ts("step6_lost"))
    rt.execute("sync_lead_activity", live["step6_lost"])
    _p("STEP5 失注（時期）→ 予算編成時期に再アプローチタスク", [t for t in rt.crm.tasks if t["type"] == "recontact"])

    _p("運用: Meta広告の予算調整（目標商談化単価 100,000円）", rt.execute("optimize_lead_gen_campaigns", {
        "platform": "meta_ads", "action": "update_budget", "optimization_metrics": {"target_cost_per_sql": 100000}}))
    _p("運用: 低成果クリエイティブ停止", rt.execute("optimize_lead_gen_campaigns", {
        "platform": "meta_ads", "action": "pause_underperforming_creative"})["paused"])
    cal = rt.execute("plan_social_content_calendar", {"start_date": "2026-09-21", "weeks": 2,
                                                      "target_industries": ["manufacturing", "it_saas"], "account_status": "new"})
    _p("Instagram投稿カレンダー（2週間）", [_brief(e, ("date", "format", "target_industry", "theme")) for e in cal["entries"]])

    rep = rt.execute("analyze_marketing_funnel", {"period_start": "2026-08-01", "period_end": "2026-09-14",
                                                  "group_by": "source_medium"})
    _p("ファネル分析レポート", rep.get("markdown", rep))

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "demo_funnel_report.md").write_text(rep.get("markdown", ""), encoding="utf-8")
    (out / "demo_instagram_calendar.json").write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    rt.save_audit_log(out / "demo_audit_log.jsonl")
    print(f"\nレポート・投稿カレンダー・監査ログを {out}/ に保存しました。")


def _state_path(client_id: str) -> Path:
    return STATE_DIR / f"{client_id}.json"


def _runtime_from_state(client_id: str) -> AgentRuntime:
    rt = AgentRuntime(client_id=client_id)
    rt.store = LeadStore.load(_state_path(client_id))
    return rt


def cmd_call(args) -> None:
    rt = _runtime_from_state(args.client)
    raw = Path(args.args).read_text(encoding="utf-8") if args.args.endswith(".json") else args.args
    result = rt.execute(args.tool, json.loads(raw))
    rt.store.save(_state_path(args.client))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_agent(args) -> None:
    from .llm_agent import run_agent

    if args.scenario:
        rt = build_runtime(json.loads(SCENARIO.read_text(encoding="utf-8")), live_mocks=False)
        rt._clock = datetime.fromisoformat("2026-09-14T17:00:00+09:00")
    else:
        rt = _runtime_from_state(args.client)
    print(run_agent(rt, args.request, model=args.model))
    if not args.scenario:
        rt.store.save(_state_path(args.client))


def cmd_export(args) -> None:
    schemas = load_schemas()
    data = list(schemas.values()) if args.format == "raw" else {"openai": to_openai, "anthropic": to_anthropic}[args.format](schemas)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dm-agent", description="BtoBデジタルマーケティングAIエージェント")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="リード獲得→育成→ホットリード→商談化のシナリオをシミュレーション実行")
    d.add_argument("--dry-run", action="store_true", help="メール・CRM・広告への反映を行わず計画のみ出力")
    d.set_defaults(fn=cmd_demo)
    c = sub.add_parser("call", help="スキルを1回実行（state/<client>.json に永続化）")
    c.add_argument("tool")
    c.add_argument("args", help="JSON文字列 または .json ファイルパス")
    c.add_argument("--client", default=DEFAULT_CLIENT, help="config/clients/<client>.json")
    c.set_defaults(fn=cmd_call)
    a = sub.add_parser("agent", help="Claude に自然言語で依頼（要 ANTHROPIC_API_KEY）")
    a.add_argument("request")
    a.add_argument("--model", default="claude-opus-5")
    a.add_argument("--client", default=DEFAULT_CLIENT)
    a.add_argument("--scenario", action="store_true", help="デモ用サンプルデータで実行（dry_run）")
    a.set_defaults(fn=cmd_agent)
    e = sub.add_parser("export-tools", help="ツール定義を各フレームワーク形式で出力")
    e.add_argument("--format", choices=["openai", "anthropic", "raw"], default="openai")
    e.set_defaults(fn=cmd_export)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

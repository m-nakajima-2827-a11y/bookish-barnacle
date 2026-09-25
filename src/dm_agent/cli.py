"""Command line entry point: `python -m dm_agent <command>`."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .cdp import CDPStore
from .connectors import MockAdPlatform
from .registry import ROOT, load_schemas, to_anthropic, to_openai
from .runtime import AgentRuntime
from .workflow import install_default_playbook

STATE = ROOT / "state" / "cdp.json"
SCENARIO = ROOT / "examples" / "scenario_store_web.json"


def build_runtime(scenario: dict, live_mocks: bool) -> AgentRuntime:
    rt = AgentRuntime(now=datetime.fromisoformat(scenario["start_at"]))
    if live_mocks:
        # Mocks only record calls, so "live" is safe here and shows the full effect of each step.
        rt.policy = copy.deepcopy(rt.policy)
        rt.policy["execution_mode"] = "live"
        rt.guardrails.policy = rt.policy
    rt.ad_platforms = {p: MockAdPlatform(p, copy.deepcopy(c)) for p, c in scenario["campaigns"].items()}
    rt.store.ad_spend = list(scenario["ad_spend"])
    for cid, tps in scenario["history"].items():
        rt.store.ingest(cid, tps)
    return rt


def _p(title: str, obj) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str) if not isinstance(obj, str) else obj)


def cmd_demo(args) -> None:
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    rt = build_runtime(scenario, live_mocks=not args.dry_run)
    install_default_playbook(rt)
    print(f"実行モード: {'dry_run' if rt.guardrails.dry_run else 'live（モック媒体）'} / 開始時刻: {rt.now().isoformat()}")

    # Step 1: POS scan → CDP sync (fires ad suppression + schedules prediction via playbook)
    trig = scenario["trigger_event"]
    rt.advance_to(datetime.fromisoformat(trig["touchpoints"][0]["timestamp"]))
    _p("STEP1 店舗購買の検知 → sync_omnichannel_customer_data", rt.execute("sync_omnichannel_customer_data", trig))
    _p("STEP2 広告の自動抑制（除外リスト同期の結果）",
       [e for e in rt.audit_log if e.get("tool") == "optimize_ad_and_social_campaigns"])
    for name, ad in rt.ad_platforms.items():
        print(f"  {name}: audiences={ {k: len(v) for k, v in ad.audiences.items()} } "
              f"excluded_on={[c['campaign_id'] for c in ad.get_campaigns() if c.get('excluded_segments')]}")
    _p("予約ジョブ", rt.pending_jobs())

    # Steps 3-4: 3 days later → prediction → cross-sell push
    ran = rt.advance_to(rt.now() + timedelta(days=rt.policy["workflow"]["post_purchase_followup_days"]))
    _p("STEP3 次回アクション予測（3日後）", ran[0]["result"] if ran else "no job")
    _p("STEP4 オムニチャネルフォロー配信", rt.store.outreach_log[-1] if rt.store.outreach_log else "none")

    # Ops: budget / bidding / creative / report
    _p("運用: 予算再配分 google_ads（目標ROAS 2.0）", rt.execute("optimize_ad_and_social_campaigns", {
        "platform": "google_ads", "action": "update_budget", "optimization_metrics": {"target_roas": 2.0}}))
    _p("運用: 入札戦略 google_ads", rt.execute("optimize_ad_and_social_campaigns", {
        "platform": "google_ads", "action": "adjust_bidding_strategy", "optimization_metrics": {"target_roas": 2.0}}))
    _p("運用: 低成果クリエイティブ停止", rt.execute("optimize_ad_and_social_campaigns", {
        "platform": "google_ads", "action": "pause_underperforming_creative"}))
    _p("承認待ち", rt.approvals)
    rep = rt.execute("generate_omnichannel_attribution_report", {
        "period_start": "2026-09-01", "period_end": "2026-09-23", "attribution_model": "position_based"})
    _p("レポート", rep.get("markdown", rep))

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "demo_attribution_report.md").write_text(rep.get("markdown", ""), encoding="utf-8")
    rt.save_audit_log(out / "demo_audit_log.jsonl")
    print(f"\nレポートと監査ログを {out}/ に保存しました。")


def _runtime_from_state() -> AgentRuntime:
    rt = AgentRuntime()
    rt.store = CDPStore.load(STATE, rt.catalog)
    return rt


def cmd_call(args) -> None:
    rt = _runtime_from_state()
    result = rt.execute(args.tool, json.loads(Path(args.args).read_text() if args.args.endswith(".json") else args.args))
    rt.store.save(STATE)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_agent(args) -> None:
    from .llm_agent import run_agent

    if args.scenario:
        rt = build_runtime(json.loads(SCENARIO.read_text(encoding="utf-8")), live_mocks=False)
        rt._clock = datetime.fromisoformat("2026-09-23T11:00:00+09:00")
    else:
        rt = _runtime_from_state()
    print(run_agent(rt, args.request, model=args.model))
    if not args.scenario:
        rt.store.save(STATE)


def cmd_export(args) -> None:
    schemas = load_schemas()
    data = {"openai": to_openai, "anthropic": to_anthropic}[args.format](schemas) if args.format != "raw" else list(schemas.values())
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dm-agent", description="オムニチャネル・デジタルマーケティングAIエージェント")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="店舗×Web連動シナリオをシミュレーション実行")
    d.add_argument("--dry-run", action="store_true", help="媒体・配信への反映を行わず計画のみ出力")
    d.set_defaults(fn=cmd_demo)
    c = sub.add_parser("call", help="スキルを1回実行（state/cdp.json に永続化）")
    c.add_argument("tool")
    c.add_argument("args", help="JSON文字列 または .json ファイルパス")
    c.set_defaults(fn=cmd_call)
    a = sub.add_parser("agent", help="Claude に自然言語で依頼（要 ANTHROPIC_API_KEY）")
    a.add_argument("request")
    a.add_argument("--model", default="claude-opus-5")
    a.add_argument("--scenario", action="store_true", help="デモ用サンプルデータで実行（dry_run）")
    a.set_defaults(fn=cmd_agent)
    e = sub.add_parser("export-tools", help="ツール定義を各フレームワーク形式で出力")
    e.add_argument("--format", choices=["openai", "anthropic", "raw"], default="openai")
    e.set_defaults(fn=cmd_export)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

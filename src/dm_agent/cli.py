"""Command line entry point: `python -m dm_agent <command>`."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

from .connectors import MockAdPlatform
from .ma import engine as ma_engine
from .ma.store import MAStore
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
        if h.get("contact"):  # 既存リードをMAのカスタマーとして登録（過去に取得済みの連絡先・同意）
            p = ma_engine.ensure_customer(rt, h["lead_id"])
            ma_engine.set_contact(rt, p, h["contact"])
            p.attributes.update({k: v for k, v in (h.get("account") or {}).items() if k != "account_id"})
            p.email_opt_in = bool((h.get("consent") or {}).get("email_opt_in"))
    for p in rt.ma.profiles.values():
        ma_engine.evaluate_segments(rt, p)
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

    def at(iso: str) -> None:
        rt.advance_to(datetime.fromisoformat(iso))

    def last_ts(step: dict) -> str:
        items = step.get("events") or step.get("touchpoints") or [step.get("submission", {})]
        return max(x["timestamp"] for x in items)

    print(f"クライアント: {rt.client['name']} / 実行モード: {'dry_run' if rt.guardrails.dry_run else 'live（モック接続）'}")

    _p("STEP0 Instagramプロフィール用のUTM付きURL", _brief(rt.execute("build_utm_tracking_url", {
        "base_url": "https://example.com/lp/mfg-checksheet", "utm_source": "instagram", "utm_medium": "social",
        "utm_campaign": "mfg_paper", "placement": "instagram_profile", "target_industry": "manufacturing"}),
        ("status", "url", "predicted_ga4_channel_group", "warnings")))
    lp = rt.execute("ma_create_landing_page", {
        "slug": "mfg-checksheet", "title": "製造業向け 営業仕組み化チェックシート", "form_id": "F-WP-MFG",
        "headline": "ベテラン営業の「勘と経験」を、チーム全員の型に。",
        "subheadline": "製造業の営業組織向け・無料チェックシート",
        "benefits": ["属人化しているポイントを30項目で点検", "ルート営業から提案型営業へ移る手順", "週報・報告の型づくりのコツ"],
        "target_industry": "manufacturing"})
    _p("STEP0' MA: キャンペーンLPを作成（フォーム・計測タグ組み込み済み）", {k: lp[k] for k in ("status", "url", "next_steps")})

    at(last_ts(live["anon_first_visit"]))
    r = rt.execute("ma_track_activity", live["anon_first_visit"])
    _p("STEP1 9/2 匿名客がInstagram経由でLP・事例を閲覧（MAで匿名のまま記録・スコア加算）", r["profiles"][0])

    at(last_ts(live["anon_revisit"]))
    r = rt.execute("ma_track_activity", live["anon_revisit"])
    _p("STEP2 9/7 20:25 LP再訪 → セグメント「匿名でLPを2回以上閲覧」に該当 → 資料DLポップアップを表示",
       {"entered_segments": r["events"][0]["entered_segments"], "popup": r.get("popup")})
    at(last_ts(live["popup_interaction"]))
    rt.execute("ma_track_activity", live["popup_interaction"])

    at(last_ts(live["form_submit"]))
    r = rt.execute("ma_manage_form", live["form_submit"])
    _p("STEP3 9/7 20:30 ポップアップのフォームから資料DL → 実名化（匿名時代の行動を引き継ぎ）→ 自動返信 → Slack通知 → リード登録・MQL・育成シナリオ", r)
    cid = r["customer_id"]
    lead = rt.store.leads[cid]
    print(f"  リード: stage={lead.stage} score={lead.score} first_touch={lead.first_touch and lead.first_touch.get('campaign')} "
          f"nurture={lead.nurture and lead.nurture['scenario_id']} account={lead.account_id}")

    at("2026-09-08T12:01:00+09:00")
    rt.execute("ma_track_activity", live["push_permission"])
    _p("STEP4 9/8 別の匿名客がWebプッシュを許諾 → セミナー告知をプッシュ配信（営業時間内）", rt.execute("ma_send_web_push", {
        "segment_id": "SEG-PUSH", "title": "オンラインセミナー開催：BtoB営業組織の立ち上げ方",
        "url": "https://example.com/seminar/sales-org?utm_source=ma_push&utm_medium=push&utm_campaign=webinar_wb-gen-01"}))

    at(last_ts(live["webinar_attendance"]))
    rt.execute("sync_lead_activity", {"lead_id": cid, **live["webinar_attendance"]})
    at(last_ts(live["pricing_visit"]))
    rt.execute("ma_track_activity", live["pricing_visit"])
    task = next((t for t in rt.crm.tasks if t.get("lead_id") == cid and t["type"] == "first_contact"), None)
    _p("STEP5 9/10 セミナー参加＋料金ページ閲覧 → ホットリード → インサイドセールスへ引き渡し（30分ルール）",
       {"stage": lead.stage, "score": lead.score, "ma_score": rt.ma.by_customer(cid).score,
        "crm_task_due": task and task["due_at"], "talk_points": task and task["context"]["talk_points_hypothesis"]})
    at(last_ts(live["first_contact"]))
    rt.execute("sync_lead_activity", {"lead_id": cid, **live["first_contact"]})

    at("2026-09-11T10:00:00+09:00")
    _p("STEP6 9/11 MA: 製造業・配信可セグメントへセミナー案内（テスト→配信）", {
        "test": rt.execute("ma_send_email", {"segment_id": "SEG-MFG-OPTIN", "subject": "【10/1開催】BtoB営業組織の立ち上げ方",
                                             "asset_id": "WB-GEN-01", "campaign": "webinar_oct", "test_only": True}),
        "send": rt.execute("ma_send_email", {"segment_id": "SEG-MFG-OPTIN", "subject": "【10/1開催】BtoB営業組織の立ち上げ方",
                                             "body": "{{company_name}} ご担当者様\n営業組織の立ち上げ方を解説するセミナーのご案内です。",
                                             "asset_id": "WB-GEN-01", "campaign": "webinar_oct"})})

    at(last_ts(live["meeting"]))
    rt.execute("sync_lead_activity", {"lead_id": cid, **live["meeting"]})
    at(last_ts(live["lost"]))
    rt.execute("sync_lead_activity", live["lost"])
    _p("STEP7 9/14 商談設定 → 広告除外 ／ 別リードの失注（時期）→ 予算編成時期の再アプローチ", {
        "ad_exclusions": {n: sorted(ad.audiences) for n, ad in rt.ad_platforms.items()},
        "recontact": [t["due_at"] for t in rt.crm.tasks if t["type"] == "recontact"]})

    at("2026-09-30T18:00:00+09:00")
    _p("MAレポート: 概要", rt.execute("ma_get_report", {"report_type": "overview"}))
    _p("MAレポート: メール", rt.execute("ma_get_report", {"report_type": "email"})["rows"])
    _p("MAレポート: シナリオ", rt.execute("ma_get_report", {"report_type": "scenario"})["scenarios"])
    _p("MAレポート: ポップアップ", rt.execute("ma_get_report", {"report_type": "popup"})["popups"])

    rep = rt.execute("analyze_marketing_funnel", {"period_start": "2026-08-01", "period_end": "2026-09-14",
                                                  "group_by": "source_medium"})
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "demo_funnel_report.md").write_text(rep.get("markdown", ""), encoding="utf-8")
    (out / "lp_mfg-checksheet.html").write_text(lp["html"], encoding="utf-8")
    rt.save_audit_log(out / "demo_audit_log.jsonl")
    print(f"\nファネル分析レポート・LP（HTML）・監査ログを {out}/ に保存しました。")


def _state_path(client_id: str) -> Path:
    return STATE_DIR / f"{client_id}.json"


def _ma_state_path(client_id: str) -> Path:
    return STATE_DIR / f"{client_id}_ma.json"


def _runtime_from_state(client_id: str) -> AgentRuntime:
    rt = AgentRuntime(client_id=client_id)
    rt.store = LeadStore.load(_state_path(client_id))
    if _ma_state_path(client_id).exists():
        rt.ma = MAStore.load(_ma_state_path(client_id))
    return rt


def _save_state(rt: AgentRuntime, client_id: str) -> None:
    rt.store.save(_state_path(client_id))
    rt.ma.save(_ma_state_path(client_id))


def cmd_call(args) -> None:
    rt = _runtime_from_state(args.client)
    raw = Path(args.args).read_text(encoding="utf-8") if args.args.endswith(".json") else args.args
    result = rt.execute(args.tool, json.loads(raw))
    _save_state(rt, args.client)
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
        _save_state(rt, args.client)


def cmd_export(args) -> None:
    schemas = load_schemas()
    data = list(schemas.values()) if args.format == "raw" else {"openai": to_openai, "anthropic": to_anthropic}[args.format](schemas)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dm-agent", description="BtoBデジタルマーケティングAIエージェント")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="匿名訪問→MA（ポップアップ・フォーム・シナリオ）→ホットリード→商談化をシミュレーション実行")
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

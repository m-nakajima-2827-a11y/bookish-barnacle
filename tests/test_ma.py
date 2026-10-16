"""In-house MA (SATORI の公開機能構成をもとにした独自実装)."""

import json

from conftest import at, run_live


def _visit(rt, cookie, url, ts):
    return rt.execute("ma_track_activity", {"visitor_id": cookie, "events": [{"type": "web_access", "timestamp": ts, "url": url}]})


def _submit(rt, email="sato@example-mfg.example", cookie=None, form="F-WP-MFG", optin="1", **over):
    values = {"company": "サンプル工業", "name": "佐藤 花子", "email": email, "industry": "manufacturing",
              "employees": "50-299", "role": "executive", "optin": optin, **over}
    return rt.execute("ma_manage_form", {"action": "submit", "form_id": form, "submission": {
        "visitor_id": cookie, "values": values, "page_url": "https://example.com/lp/mfg-checksheet", "timestamp": rt.now().isoformat()}})


# --- スコア定義 ---------------------------------------------------------------------------------
def test_default_scores_and_individual_override(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    d = live_rt.execute("ma_configure_scoring", {"action": "get"})
    assert {k: d["common"][k] for k in ("web_access", "email_click", "email_open", "unsubscribe")} == \
        {"web_access": 5, "email_click": 10, "email_open": 1, "unsubscribe": -30}
    r = _visit(live_rt, "ck-x", "https://example.com/blog/a", "2026-09-08T10:00:00+09:00")
    assert r["events"][0]["points"] == 5
    r = _visit(live_rt, "ck-x", "https://example.com/price", "2026-09-08T10:01:00+09:00")
    assert r["events"][0]["points"] == 20  # 個別設定（料金ページ+20）を適用し、共通+5は加算しない


def test_param_filter_rule_and_limits(live_rt):
    bad = live_rt.execute("ma_configure_scoring", {"action": "add_rule", "rule": {"target": "web_access", "points": 5}})
    assert "error" in bad
    too_big = live_rt.execute("ma_configure_scoring", {"action": "add_rule", "rule": {"target": "web_access", "url_filter": "/x", "points": 100001}})
    assert "error" in too_big
    ok = live_rt.execute("ma_configure_scoring", {"action": "add_rule", "rule": {"target": "web_access", "param_filter": "utm_campaign=it_seminar", "points": 7}})
    assert ok["status"] == "ok"
    r = _visit(live_rt, "ck-y", "https://example.com/seminar/sales-org?utm_source=google&utm_medium=cpc&utm_campaign=it_seminar", "2026-09-08T10:00:00+09:00")
    assert r["events"][0]["points"] == 7


# --- 匿名 → 実名化・名寄せ --------------------------------------------------------------------------
def test_form_merges_anonymous_history_and_dedupes_by_email(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    _visit(live_rt, "ck-a", "https://example.com/lp/mfg-checksheet?utm_source=instagram&utm_medium=social&utm_campaign=mfg_paper", "2026-09-08T09:50:00+09:00")
    first = _submit(live_rt, cookie="ck-a")
    assert first["new_customer"] and first["merged_anonymous_activities"] == 1
    assert "anon:ck-a" not in live_rt.ma.profiles
    _visit(live_rt, "ck-b", "https://example.com/blog/b", "2026-09-08T10:00:00+09:00")
    again = _submit(live_rt, email="SATO@example-mfg.example", cookie="ck-b", form="F-SEMINAR")
    assert not again["new_customer"] and again["customer_id"] == first["customer_id"]  # 名寄せ（メールアドレス）
    assert set(live_rt.ma.by_customer(first["customer_id"]).cookies) == {"ck-a", "ck-b"}


def test_form_validation_and_no_consent(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    bad = _submit(live_rt, email="not-an-email")
    assert bad["status"] == "invalid"
    r = _submit(live_rt, email="no-optin@corp.example", optin="")
    assert r["status"] == "accepted" and r["email_opt_in"] is False
    assert r["auto_reply"]["status"] == "sent"  # 請求資料の送付（取引メール）は同意の対象外として送信
    cid = r["customer_id"]
    mk = live_rt.execute("ma_send_email", {"customer_id": cid, "subject": "お知らせ", "asset_id": "CS-MFG-01"})
    assert mk["blocked_reasons"] == {"no_opt_in": 1}


def test_free_mail_uses_company_name_for_account(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    r = _submit(live_rt, email="someone@gmail.com")
    assert live_rt.store.leads[r["customer_id"]].account_id == "co:サンプル工業"


# --- セグメント・シナリオ ------------------------------------------------------------------------
def test_segment_create_does_not_fire_scenarios_retroactively(live_rt):
    seg = live_rt.execute("ma_manage_segment", {"action": "create", "segment_id": "SEG-IT", "name": "IT",
                                                "conditions": {"type": "attribute", "field": "industry", "equals": "it_saas"}})
    assert seg["members"] == 2
    sc = live_rt.execute("ma_manage_scenario", {"action": "create", "scenario_id": "SC-IT", "definition": {
        "name": "IT", "trigger": {"type": "segment_entered", "key": "SEG-IT"},
        "steps": [{"day": 0, "action": "add_tag", "tag": "it_track"}]}})
    assert sc["scenario_status"] == "draft"
    live_rt.execute("ma_manage_scenario", {"action": "activate", "scenario_id": "SC-IT"})
    assert not any("it_track" in p.tags for p in live_rt.ma.profiles.values())
    # a customer who newly matches does trigger it
    live_rt.execute("ma_manage_customer", {"action": "update_attributes", "customer_id": "L110", "attributes": {"industry": "it_saas"}})
    assert "it_track" in live_rt.ma.by_customer("L110").tags


def test_scenario_validation(live_rt):
    r = live_rt.execute("ma_manage_scenario", {"action": "create", "definition": {
        "name": "x", "trigger": {"type": "segment_entered", "key": "NOPE"}, "steps": [{"action": "send_sms"}]}})
    assert r["status"] == "invalid" and len(r["errors"]) == 2


def _boost(rt, cid, cookie):
    p = rt.ma.by_customer(cid)
    rt.ma.cookie_index[cookie] = p.profile_id
    p.cookies.append(cookie)
    _visit(rt, cookie, "https://example.com/demo", "2026-09-08T10:00:00+09:00")
    return p


def test_score_alert_scenario_notifies_sales(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    live_rt.execute("ma_configure_scoring", {"action": "add_rule", "rule": {"target": "web_access", "url_filter": "/demo", "points": 100}})
    p = _boost(live_rt, "L102", "ck-102")  # 実名客・ステージ lead → 通知
    assert "SEG-SCORE-100" in p.segments and "score_100" in p.tags
    post = live_rt.webhook.posts[-1]
    assert post["url"].endswith("/slack/sales") and post["body"]["customer_id"] == "L102"
    q = _boost(live_rt, "L103", "ck-103")  # 受注済み（customer）→ シナリオから離脱し通知しない
    assert "score_100" not in q.tags
    assert live_rt.ma.enrollments["SC-SCORE-ALERT|L103"]["status"] == "exited"


# --- メール計測・配信停止 --------------------------------------------------------------------------
def test_email_open_click_unsubscribe_tracking(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    live_rt.execute("ma_send_email", {"customer_id": "L105", "subject": "事例のご紹介", "asset_id": "CS-IT-01"})
    rec = live_rt.ma.emails[-1]
    assert rec["status"] == "sent" and rec["to"] == "l***@a-it-03.example"
    body = live_rt.email.sent[-1]["message"]["body"]
    assert f"/c/{rec['token']}" in body and f"/u/{rec['token']}" in body and "{{" not in body
    before = live_rt.ma.by_customer("L105").score
    live_rt.execute("ma_track_activity", {"events": [
        {"type": "email_open", "timestamp": "2026-09-08T10:05:00+09:00", "email_token": rec["token"]},
        {"type": "email_click", "timestamp": "2026-09-08T10:06:00+09:00", "email_token": rec["token"]},
        {"type": "unsubscribe", "timestamp": "2026-09-08T10:07:00+09:00", "email_token": rec["token"]}]})
    p = live_rt.ma.by_customer("L105")
    assert p.score == before + 1 + 10 - 30 and p.unsubscribed and not live_rt.store.leads["L105"].email_opt_in
    rep = live_rt.execute("ma_get_report", {"report_type": "email"})["rows"][0]
    assert rep["open_rate"] == 1.0 and rep["click_rate"] == 1.0 and rep["unsubscribe_rate"] == 1.0
    again = live_rt.execute("ma_send_email", {"customer_id": "L105", "subject": "再送", "asset_id": "WP-GEN-01"})
    assert again["blocked_reasons"] == {"unsubscribed": 1}
    assert live_rt.store.events["L105"][-1]["event_type"] == "email_click"  # MAの行動はリードにも連携


def test_bulk_email_outside_hours_is_scheduled(live_rt):
    at(live_rt, "2026-09-12T11:00:00+09:00")  # Saturday
    r = live_rt.execute("ma_send_email", {"segment_id": "SEG-IT-OPTIN", "subject": "お知らせ", "asset_id": "WB-GEN-01"})
    assert r["result"] == {"scheduled": 2}
    at(live_rt, "2026-09-14T09:01:00+09:00")
    assert sum(1 for e in live_rt.ma.emails if e["status"] == "sent") == 2


# --- ポップアップ・Webプッシュ ----------------------------------------------------------------------
def test_popup_conditions_and_frequency(live_rt, scenario):
    out = run_live(live_rt, scenario, "anon_first_visit")
    assert out["anon_first_visit"]["popup"] is None  # first LP visit: not yet in the revisit segment
    out = run_live(live_rt, scenario, "anon_revisit", "popup_interaction")
    assert out["anon_revisit"]["popup"]["popup_id"] == "P-MFG-DL"
    again = live_rt.execute("ma_manage_popup", {"action": "decide", "visitor_id": "ck-101", "url": "https://example.com/lp/mfg-checksheet"})
    assert again["popup"] is None  # clicked → hidden / once per day
    price = live_rt.execute("ma_manage_popup", {"action": "decide", "visitor_id": "ck-101", "url": "https://example.com/price"})
    assert price["popup"]["popup_id"] == "P-SEMINAR"


def test_web_push_permission_frequency_and_hours(live_rt, scenario):
    run_live(live_rt, scenario, "push_permission")
    for i in range(3):
        assert live_rt.execute("ma_send_web_push", {"segment_id": "SEG-PUSH", "title": f"t{i}", "url": "https://example.com/x"})["recipients"] == 1
    capped = live_rt.execute("ma_send_web_push", {"segment_id": "SEG-PUSH", "title": "t4", "url": "https://example.com/x"})
    assert capped["recipients"] == 0 and capped["skipped_frequency_cap"] == 1
    at(live_rt, "2026-09-08T19:00:00+09:00")
    later = live_rt.execute("ma_send_web_push", {"title": "t5", "url": "https://example.com/x"})
    assert later["status"] == "scheduled" and later["scheduled_at"].startswith("2026-09-09T09:00")


# --- 個人情報の扱い・LP・レポート ------------------------------------------------------------------
def test_pii_is_masked_in_outputs_and_audit_log(live_rt, scenario):
    run_live(live_rt, scenario, "anon_first_visit", "form_submit")
    got = live_rt.execute("ma_manage_customer", {"action": "get", "customer_id": "C00001"})
    assert got["contact"] == {"email": "y***@sample-seiki.example", "name": "***"}
    log = json.dumps(live_rt.audit_log, ensure_ascii=False, default=str)
    assert "yamada@sample-seiki.example" not in log and "山田" not in log
    assert "yamada@" not in json.dumps([vars(l) for l in live_rt.store.leads.values()], ensure_ascii=False, default=str)


def test_landing_page_generation(live_rt):
    bad = live_rt.execute("ma_create_landing_page", {"slug": "Bad Slug", "title": "t", "headline": "h", "form_id": "F-WP-MFG"})
    assert bad["status"] == "invalid"
    r = live_rt.execute("ma_create_landing_page", {"slug": "it-toss", "title": "<script>x</script>", "headline": "h",
                                                   "form_id": "F-WP-IT", "benefits": ["a & b"]})
    assert r["url"] == "https://example.com/lp/it-toss"
    assert "<script>x</script>" not in r["html"] and "&lt;script&gt;" in r["html"] and "a &amp; b" in r["html"]
    assert 'data-ma-form="F-WP-IT"' in r["html"] and 'type="email"' in r["html"] and "tag.js" in r["html"]


def test_overview_report(live_rt, scenario):
    run_live(live_rt, scenario, "anon_first_visit", "anon_revisit", "form_submit", "push_permission")
    r = live_rt.execute("ma_get_report", {"report_type": "overview"})
    assert r["form_submissions"] == 1 and r["anonymous_history_merged"] == 3 and r["push_subscribed"] == 1
    assert r["anonymous"] == 1

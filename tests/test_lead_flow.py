"""End-to-end: 匿名訪問 → ポップアップ → フォーム（実名化）→ MQL・育成 → ホットリード → 引き渡し → 商談 → 広告除外 / 失注 → 再アプローチ."""

from conftest import at, run_live

PRE_FORM = ("anon_first_visit", "anon_revisit", "popup_interaction")


def test_form_identifies_visitor_and_creates_mql(live_rt, scenario):
    out = run_live(live_rt, scenario, *PRE_FORM, "form_submit")
    r = out["form_submit"]
    cid = r["customer_id"]
    assert r["new_customer"] and r["merged_anonymous_activities"] == 5 and r["email"] == "y***@sample-seiki.example"
    ld = live_rt.store.leads[cid]
    assert ld.stage == "mql" and ld.nurture["scenario_id"] == "nurture_manufacturing"
    assert ld.first_touch["campaign"] == "mfg_paper"          # inherited from the anonymous LP visit
    assert ld.account_id == "dom:sample-seiki.example"         # same company as L102 → buying committee
    # auto-reply goes out immediately (transactional) even at 20:30; marketing steps wait for business hours
    assert live_rt.email.sent[0]["message"]["subject"].startswith("【資料送付】")
    assert live_rt.webhook.posts and "email" not in str(live_rt.webhook.posts[0]["body"])


def test_high_intent_hands_off_and_nurture_exits(live_rt, scenario):
    run_live(live_rt, scenario, *PRE_FORM, "form_submit", "webinar_attendance", "pricing_visit")
    ld = live_rt.store.leads["C00001"]
    assert ld.stage == "sql"
    task = next(t for t in live_rt.crm.tasks if t["type"] == "first_contact")
    assert task["due_at"].startswith("2026-09-10T15:35")
    assert task["context"]["account_contacts"] == 2
    at(live_rt, "2026-10-15T10:00:00+09:00")
    enr = live_rt.ma.enrollments["nurture_manufacturing|C00001"]
    assert enr["status"] == "exited" and "sql" in enr["exit_reason"]
    assert [m["message"]["subject"] for m in live_rt.email.sent] == ["【資料送付】営業仕組み化チェックシート"]


def test_meeting_syncs_ad_exclusion(live_rt, scenario):
    run_live(live_rt, scenario, *PRE_FORM, "form_submit", "meeting")
    for p in ("google_ads", "meta_ads"):
        assert {"open_opportunities", "customers"} <= set(live_rt.ad_platforms[p].audiences)


def test_lost_on_timing_schedules_recontact(live_rt, scenario):
    run_live(live_rt, scenario, "lost")
    task = live_rt.crm.tasks[-1]
    assert task["type"] == "recontact" and task["due_at"].startswith("2027-01-04T09:00")
    assert live_rt.store.leads["L105"].stage == "recycled"


def test_student_is_disqualified_and_not_emailed(live_rt):
    assert live_rt.store.leads["L104"].stage == "disqualified"
    r = live_rt.execute("trigger_nurture_action", {"lead_id": "L104", "action": "send_email", "content_asset_id": "WP-GEN-01"})
    assert r["status"] == "blocked"


def test_dry_run_touches_nothing_external(dry_rt, scenario):
    run_live(dry_rt, scenario, *PRE_FORM, "form_submit", "webinar_attendance", "pricing_visit")
    assert dry_rt.email.sent == [] and dry_rt.crm.tasks == [] and dry_rt.webhook.posts == []
    assert all(not ad.calls for ad in dry_rt.ad_platforms.values())

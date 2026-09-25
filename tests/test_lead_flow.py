"""End-to-end: Instagram → 資料DL → MQL/育成 → ホットリード → 営業引き渡し → 商談 → 広告除外 / 失注 → 再アプローチ."""

from conftest import at


def test_download_makes_mql_and_enrolls_industry_track(live_rt, scenario):
    at(live_rt, "2026-09-07T20:30:00+09:00")
    live_rt.execute("sync_lead_activity", scenario["live"]["step1_download"])
    ld = live_rt.store.leads["L101"]
    assert ld.stage == "mql"
    assert ld.nurture["track"] == "manufacturing"
    # 20:30 is outside business hours → first email waits for 09:00 next business day
    jobs = live_rt.pending_jobs()
    assert jobs[0]["run_at"].startswith("2026-09-08T09:00")
    assert live_rt.email.sent == []
    at(live_rt, "2026-09-08T09:01:00+09:00")
    assert live_rt.email.sent[0]["message"]["subject"].startswith("【資料送付】")
    body = live_rt.email.sent[0]["message"]["body"]
    assert "配信停止" in body and "utm_medium=email" in body


def test_high_intent_hands_off_with_sla_and_stops_nurture(live_rt, scenario):
    at(live_rt, "2026-09-07T20:30:00+09:00")
    live_rt.execute("sync_lead_activity", scenario["live"]["step1_download"])
    at(live_rt, "2026-09-10T15:05:00+09:00")
    live_rt.execute("sync_lead_activity", scenario["live"]["step3_high_intent"])
    ld = live_rt.store.leads["L101"]
    assert ld.stage == "sql"
    task = live_rt.crm.tasks[-1]
    assert task["type"] == "first_contact" and task["due_at"].startswith("2026-09-10T15:35")
    assert task["context"]["account_contacts"] == 2
    # remaining nurture steps are skipped once sales owns the lead
    at(live_rt, "2026-09-30T10:00:00+09:00")
    later = [r for r in live_rt.store.email_log if r.get("track_step") and r["track_step"] != "manufacturing#0"]
    assert later == []
    assert len(live_rt.email.sent) == 1


def test_meeting_syncs_ad_exclusion(live_rt, scenario):
    at(live_rt, "2026-09-14T11:00:00+09:00")
    live_rt.execute("sync_lead_activity", scenario["live"]["step5_meeting"])
    for p in ("google_ads", "meta_ads"):
        assert "open_opportunities" in live_rt.ad_platforms[p].audiences
        assert "customers" in live_rt.ad_platforms[p].audiences  # L103 won earlier


def test_lost_on_timing_schedules_recontact_at_budget_planning(live_rt, scenario):
    at(live_rt, "2026-09-14T16:00:00+09:00")
    live_rt.execute("sync_lead_activity", scenario["live"]["step6_lost"])
    task = live_rt.crm.tasks[-1]
    assert task["type"] == "recontact"
    assert task["due_at"].startswith("2027-01-04T09:00")  # Jan (3 months before April FY start), after year-end closure
    assert live_rt.store.leads["L105"].stage == "recycled"


def test_student_is_disqualified_and_not_emailed(live_rt):
    assert live_rt.store.leads["L104"].stage == "disqualified"
    r = live_rt.execute("trigger_nurture_action", {"lead_id": "L104", "action": "send_email", "content_asset_id": "WP-GEN-01"})
    assert r["status"] == "blocked"


def test_dry_run_touches_nothing_external(dry_rt, scenario):
    at(dry_rt, "2026-09-10T15:05:00+09:00")
    dry_rt.execute("sync_lead_activity", scenario["live"]["step1_download"])
    dry_rt.execute("sync_lead_activity", scenario["live"]["step3_high_intent"])
    assert dry_rt.email.sent == [] and dry_rt.crm.tasks == []
    assert all(not ad.calls for ad in dry_rt.ad_platforms.values())

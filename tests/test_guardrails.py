from datetime import datetime

from conftest import at


def _mail(rt, lead="L103", asset="CS-IT-01"):
    return rt.execute("trigger_nurture_action", {"lead_id": lead, "action": "send_email", "content_asset_id": asset})


def test_no_opt_in_blocks_email(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    r = _mail(live_rt, lead="L102")
    assert r["status"] == "blocked" and any("no_opt_in" in x for x in r["reasons"])


def test_frequency_cap_and_duplicate_asset(live_rt):
    at(live_rt, "2026-09-08T10:00:00+09:00")
    assert _mail(live_rt, asset="CS-IT-01")["status"] == "sent"
    dup = _mail(live_rt, asset="CS-IT-01")
    assert any("duplicate_asset" in x for x in dup["reasons"])
    assert _mail(live_rt, asset="WP-GEN-01")["status"] == "sent"
    capped = _mail(live_rt, asset="DC-GEN-01")
    assert any("frequency_cap" in x for x in capped["reasons"])


def test_weekend_email_waits_for_monday(live_rt):
    at(live_rt, "2026-09-12T11:00:00+09:00")  # Saturday
    r = _mail(live_rt)
    assert r["status"] == "scheduled" and r["scheduled_at"].startswith("2026-09-14T09:00")


def test_handoff_requires_hot_stage(live_rt):
    r = live_rt.execute("trigger_nurture_action", {"lead_id": "L102", "action": "sales_handoff"})
    assert r["status"] == "blocked"


def test_sla_counts_business_minutes(live_rt):
    g = live_rt.guardrails
    fri_evening = datetime.fromisoformat("2026-09-11T17:50:00+09:00")
    assert g.add_business_minutes(fri_evening, 30).isoformat().startswith("2026-09-14T09:20")


def test_budget_cut_for_zero_sql_campaign_needs_approval(live_rt):
    at(live_rt, "2026-09-14T17:00:00+09:00")
    r = live_rt.execute("optimize_lead_gen_campaigns", {"platform": "meta_ads", "action": "update_budget",
                                                        "optimization_metrics": {"target_cost_per_sql": 100000}})
    ch = r["changes"][0]
    assert ch["campaign_id"] == "M-MFG-LEADAD" and ch["to"] == 6400 and ch["status"] == "pending_approval"
    assert ch["performance_30d"]["crm_leads"] == 5 and ch["performance_30d"]["sql"] == 0
    assert not any(c[0] == "set_daily_budget" for c in live_rt.ad_platforms["meta_ads"].calls)
    live_rt.approve(live_rt.approvals[0]["id"])
    assert live_rt.ad_platforms["meta_ads"].campaigns["M-MFG-LEADAD"]["daily_budget"] == 6400


def test_budget_held_when_sql_sample_is_small(live_rt):
    at(live_rt, "2026-09-14T17:00:00+09:00")
    r = live_rt.execute("optimize_lead_gen_campaigns", {"platform": "google_ads", "action": "update_budget",
                                                        "optimization_metrics": {"target_cost_per_sql": 100000}})
    assert set(r["held_for_insufficient_sql"]) == {"G-IT-SEMINAR", "G-IT-PAPER"} and r["changes"] == []


def test_bidding_requires_learning_volume(live_rt):
    at(live_rt, "2026-09-14T17:00:00+09:00")
    r = live_rt.execute("optimize_lead_gen_campaigns", {"platform": "google_ads", "action": "adjust_bidding_strategy",
                                                        "optimization_metrics": {"target_cpl": 20000}})
    st = {c["campaign_id"]: c["status"] for c in r["changes"]}
    assert st == {"G-IT-SEMINAR": "applied", "G-IT-PAPER": "skipped"}

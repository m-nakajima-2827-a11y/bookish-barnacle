from datetime import datetime


def _push(rt, cid="C001", channel="app_push", scenario="churn_prevention", **kw):
    return rt.execute("trigger_personalized_outreach", {
        "customer_id": cid, "selected_channel": channel, "campaign_scenario": scenario, **kw})


def test_no_consent_is_blocked(live_rt):
    r = _push(live_rt, channel="sms")
    assert r["status"] == "blocked" and any("no_consent" in x for x in r["reasons"])


def test_discount_cap(live_rt):
    r = _push(live_rt, offer_type="store_coupon", payload_details={"discount_rate": 0.5})
    assert r["status"] == "blocked" and any("discount_cap" in x for x in r["reasons"])


def test_quiet_hours_reschedules_to_morning(live_rt):
    live_rt.advance_to(datetime.fromisoformat("2026-09-20T22:30:00+09:00"))
    r = _push(live_rt)
    assert r["status"] == "scheduled"
    assert r["scheduled_at"].startswith("2026-09-21T08:00")
    live_rt.advance_to(datetime.fromisoformat("2026-09-21T08:05:00+09:00"))
    assert live_rt.store.outreach_log[-1]["status"] == "sent"


def test_frequency_cap_and_cooldown(live_rt):
    assert _push(live_rt, scenario="churn_prevention")["status"] == "sent"
    again = _push(live_rt, scenario="churn_prevention")
    assert again["status"] == "blocked" and any("cooldown" in x for x in again["reasons"])
    assert _push(live_rt, scenario="abandoned_cart")["status"] == "sent"
    assert _push(live_rt, scenario="cross_sell_recommendation")["status"] == "sent"
    capped = _push(live_rt, scenario="post_store_visit_followup")
    assert any("frequency_cap" in x for x in capped["reasons"])


def test_budget_change_is_clamped_and_needs_approval(live_rt):
    live_rt.advance_to(datetime.fromisoformat("2026-09-20T10:00:00+09:00"))
    r = live_rt.execute("optimize_ad_and_social_campaigns", {
        "platform": "google_ads", "action": "update_budget", "optimization_metrics": {"target_roas": 2.0}})
    for ch in r["changes"]:
        assert abs(ch["to"] - ch["from"]) <= ch["from"] * 0.2 + 1
        assert ch["status"] == "pending_approval"
    # nothing applied until approved
    assert not any(c[0] == "set_daily_budget" for c in live_rt.ad_platforms["google_ads"].calls)
    live_rt.approve(live_rt.approvals[0]["id"])
    assert any(c[0] == "set_daily_budget" for c in live_rt.ad_platforms["google_ads"].calls)


def test_bidding_requires_enough_conversions(live_rt):
    r = live_rt.execute("optimize_ad_and_social_campaigns", {
        "platform": "google_ads", "action": "adjust_bidding_strategy", "optimization_metrics": {"max_cpa": 8000}})
    by_id = {c["campaign_id"]: c for c in r["changes"]}
    assert by_id["G-RMK-JKT"]["status"] == "skipped"
    assert by_id["G-SRCH-BRAND"]["status"] == "applied" and by_id["G-SRCH-BRAND"]["from"] == "maximize_conversions"


def test_never_pauses_last_active_creative(live_rt):
    r = live_rt.execute("optimize_ad_and_social_campaigns",
                        {"platform": "google_ads", "action": "pause_underperforming_creative"})
    creatives = live_rt.ad_platforms["google_ads"].campaigns["G-RMK-JKT"]["creatives"]
    assert [p["creative_id"] for p in r["paused"]] == ["G-RMK-JKT-b"]
    assert creatives["G-RMK-JKT-a"]["status"] == "active"
    assert creatives["G-RMK-JKT-c"]["status"] == "active"  # below impression threshold

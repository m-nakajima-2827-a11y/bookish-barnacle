from datetime import datetime, timedelta


def _trigger(rt, scenario):
    trig = scenario["trigger_event"]
    rt.advance_to(datetime.fromisoformat(trig["touchpoints"][0]["timestamp"]))
    return rt.execute("sync_omnichannel_customer_data", trig)


def test_store_purchase_to_crosssell_push(live_rt, scenario):
    res = _trigger(live_rt, scenario)
    assert res["derived_signals"][0]["category"] == "outdoor_jacket"
    # Step 2: purchasers excluded from jacket retargeting on both platforms
    for p in ("google_ads", "meta_ads"):
        rmk = next(c for c in live_rt.ad_platforms[p].get_campaigns() if c["segment_id"] == "rmk_outdoor_jacket")
        assert "purchased_outdoor_jacket" in rmk["excluded_segments"]
    assert live_rt.store.outreach_log == []
    # Steps 3-4: three days later
    live_rt.advance_to(live_rt.now() + timedelta(days=3))
    sent = live_rt.store.outreach_log[-1]
    assert sent["status"] == "sent" and sent["channel"] == "app_push"
    assert set(sent["message"]["product_ids"]) == {"SPR-010", "SHO-100"}
    assert sent["message"]["discount_rate"] == 0.1
    assert len(live_rt.messaging.sent) == 1
    assert live_rt.messaging.sent[0]["to"] != "C001"  # hashed


def test_duplicate_events_are_ignored(live_rt, scenario):
    _trigger(live_rt, scenario)
    again = live_rt.execute("sync_omnichannel_customer_data", scenario["trigger_event"])
    assert again["accepted_events"] == 0 and again["duplicate_events_skipped"] == 1
    assert live_rt.store.profiles["C001"].purchase_count == 1


def test_dry_run_touches_nothing_external(dry_rt, scenario):
    _trigger(dry_rt, scenario)
    dry_rt.advance_to(dry_rt.now() + timedelta(days=3))
    assert all(not ad.calls for ad in dry_rt.ad_platforms.values())
    assert dry_rt.messaging.sent == []
    assert dry_rt.store.outreach_log[-1]["status"] == "planned"


def test_adhoc_prediction_does_not_auto_send(live_rt):
    live_rt.execute("predict_customer_intent_and_churn",
                    {"customer_id": "C001", "prediction_targets": ["category_affinity", "optimal_channel"]})
    assert live_rt.store.outreach_log == []

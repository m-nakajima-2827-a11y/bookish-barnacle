from dm_agent.utm import channel_group


def test_utm_builder_ok_and_registered(live_rt):
    r = live_rt.execute("build_utm_tracking_url", {"base_url": "https://example.com/lp/x?ref=1#top", "utm_source": "instagram",
                                                   "utm_medium": "social", "utm_campaign": "it_seminar",
                                                   "placement": "instagram_story", "target_industry": "it_saas"})
    assert r["status"] == "ok" and r["predicted_ga4_channel_group"] == "Organic Social"
    assert r["url"] == ("https://example.com/lp/x?ref=1&utm_source=instagram&utm_medium=social"
                        "&utm_campaign=it_seminar&utm_content=story_it_saas#top")
    assert "it_seminar" in live_rt.store.utm_registry


def test_utm_builder_rejects_uppercase_and_japanese(live_rt):
    r = live_rt.execute("build_utm_tracking_url", {"base_url": "https://example.com/", "utm_source": "Instagram",
                                                   "utm_medium": "social", "utm_campaign": "ITセミナー"})
    assert r["status"] == "invalid" and len(r["errors"]) == 3 and "url" not in r
    assert "utm_campaign" in r["needs_manual_fix"]
    fixable = live_rt.execute("build_utm_tracking_url", {"base_url": "https://example.com/", "utm_source": "Instagram",
                                                         "utm_medium": "social", "utm_campaign": "IT Seminar"})
    assert fixable["suggested_params"]["utm_campaign"] == "it_seminar"


def test_utm_builder_warns_on_off_dictionary_medium(live_rt):
    r = live_rt.execute("build_utm_tracking_url", {"base_url": "https://example.com/", "utm_source": "instagram",
                                                   "utm_medium": "referral", "utm_campaign": "mfg_paper"})
    assert r["status"] == "ok" and any("medium" in w for w in r["warnings"])


def test_channel_grouping():
    assert channel_group("instagram", "social") == "Organic Social"
    assert channel_group("instagram", "paid_social") == "Paid Social"
    assert channel_group("google", "cpc") == "Paid Search"
    assert channel_group("newsletter", "email") == "Email"
    assert channel_group("google", "organic") == "Organic Search"
    assert channel_group("(direct)", "(none)") == "Direct"


def test_content_calendar(live_rt):
    r = live_rt.execute("plan_social_content_calendar", {"start_date": "2026-09-23", "weeks": 2,
                                                         "target_industries": ["manufacturing", "it_saas"],
                                                         "account_status": "new"})
    feed = [e for e in r["entries"] if e["format"] != "story"]
    assert [e["date"] for e in feed] == ["2026-09-21", "2026-09-25", "2026-09-28", "2026-10-02"]  # aligned to Monday
    assert {e["target_industry"] for e in feed} == {"manufacturing", "it_saas"}
    assert feed[0]["pillar"] == "howto_carousel" and feed[1]["pillar"] == "case_study"
    assert all("utm_source=instagram" in e["link_destination"] for e in r["entries"])
    assert "profile_setup_checklist" in r
    stories = [e for e in r["entries"] if e["format"] == "story"]
    assert len(stories) == 4 and "utm_content=story_" in stories[0]["link_destination"]

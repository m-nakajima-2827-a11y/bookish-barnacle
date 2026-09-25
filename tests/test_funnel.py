def test_funnel_by_source_medium(live_rt):
    r = live_rt.execute("analyze_marketing_funnel", {"period_start": "2026-08-01", "period_end": "2026-09-14",
                                                     "group_by": "source_medium", "output_format": "json"})
    rows = {x["group"]: x for x in r["rows"]}
    paid = rows["instagram / paid_social"]
    assert paid["leads"] == 5 and paid["sql"] == 0 and paid["cost"] == 360000
    g = rows["google / cpc"]
    assert g["opportunities"] == 2 and g["won"] == 1 and g["pipeline_amount"] == 2100000
    types = {h["type"] for h in r["utm_hygiene"]}
    assert {"case_variants", "missing_utm", "medium_mismatch"} <= types
    assert not any(h["value"] == "instagram / paid_social" for h in r["utm_hygiene"])
    assert r["search_console"]["brand_growth"] > 0.2
    assert r["search_console"]["ctr_improvement_candidates"][0]["query"] == "営業 仕組み化"
    assert r["recommendations"][0]["priority"] == "高"
    assert "markdown" not in r


def test_funnel_by_industry_and_attribution(live_rt):
    r = live_rt.execute("analyze_marketing_funnel", {"period_start": "2026-08-01", "period_end": "2026-09-14",
                                                     "group_by": "industry", "attribution_model": "linear"})
    rows = {x["group"]: x for x in r["rows"]}
    assert rows["it_saas"]["opportunities"] == 2 and rows["it_saas"]["sessions"] == 0
    assert sum(x["pipeline_amount"] for x in r["rows"]) == r["totals"]["pipeline_amount"]
    assert "## ファネル" in r["markdown"]

from datetime import datetime

import pytest

from dm_agent.skills.report import _weights


@pytest.mark.parametrize("model", ["last_touch", "first_touch", "linear", "time_decay", "position_based"])
def test_weights_sum_to_one(model):
    touches = [{"timestamp": f"2026-09-0{i}T00:00:00+09:00"} for i in range(1, 6)]
    w = _weights(model, touches, datetime.fromisoformat("2026-09-10T00:00:00+09:00"))
    assert sum(w) == pytest.approx(1.0)


def test_report_includes_offline_and_flags_small_sample(live_rt):
    r = live_rt.execute("generate_omnichannel_attribution_report", {
        "period_start": "2026-09-01", "period_end": "2026-09-19", "attribution_model": "linear"})
    assert r["totals"]["conversions"] == 3
    assert sum(c["attributed_revenue"] for c in r["channels"]) == pytest.approx(r["totals"]["revenue"], abs=2)
    assert r["recommendations"][0]["channel"] == "計測基盤"
    assert "| チャネル |" in r["markdown"]
    offline = live_rt.execute("generate_omnichannel_attribution_report", {
        "period_start": "2026-09-01", "period_end": "2026-09-19", "attribution_model": "linear",
        "include_offline_sales": False})
    assert offline["totals"]["conversions"] == 1


def test_external_models_fall_back_with_note(live_rt):
    r = live_rt.execute("generate_omnichannel_attribution_report", {
        "period_start": "2026-09-01", "period_end": "2026-09-19", "attribution_model": "mmm", "output_format": "json"})
    assert r["attribution_model"] == "position_based" and r["requested_model"] == "mmm"
    assert any("mmm" in n for n in r["notes"])
    assert "markdown" not in r

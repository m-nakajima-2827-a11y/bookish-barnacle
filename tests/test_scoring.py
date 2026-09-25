from conftest import at


def test_scores_and_account_view(live_rt):
    at(live_rt, "2026-09-07T12:00:00+09:00")
    r = live_rt.execute("score_and_qualify_leads", {"lead_ids": ["L101", "L102", "L999"]})
    by = {x["lead_id"]: x for x in r["leads"]}
    assert by["L101"]["fit"] == 47 and by["L101"]["fit_breakdown"] == {"industry": 20, "employee_band": 15, "job_role": 12}
    acct = r["accounts"][0]
    assert acct["account_id"] == "A-MFG-01" and acct["engaged_contacts"] == 2 and acct["buying_committee"]
    assert any("同一企業" in s for s in by["L101"]["signals"])
    assert r["unknown_lead_ids"] == ["L999"]


def test_sales_owned_stages_are_never_changed(live_rt):
    at(live_rt, "2026-09-07T12:00:00+09:00")
    r = live_rt.execute("score_and_qualify_leads", {"lead_ids": ["L103", "L105"]})
    assert {x["stage"] for x in r["leads"]} == {"customer", "opportunity"}
    assert not any(x["stage_changed"] for x in r["leads"])


def test_low_fit_paid_social_leads_stay_unqualified(live_rt):
    stages = {live_rt.store.leads[f"L11{i}"].stage for i in range(5)}
    assert stages == {"lead"}

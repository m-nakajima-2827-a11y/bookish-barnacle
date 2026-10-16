from conftest import at, run_live


def test_scores_and_account_view(live_rt, scenario):
    run_live(live_rt, scenario, "anon_first_visit", "anon_revisit", "form_submit")
    r = live_rt.execute("score_and_qualify_leads", {"lead_ids": ["C00001", "L102", "L999"]})
    by = {x["lead_id"]: x for x in r["leads"]}
    assert by["C00001"]["fit"] == 47 and by["C00001"]["fit_breakdown"] == {"industry": 20, "employee_band": 15, "job_role": 12}
    acct = r["accounts"][0]
    assert acct["account_id"] == "dom:sample-seiki.example" and acct["engaged_contacts"] == 2 and acct["buying_committee"]
    assert any("同一企業" in s for s in by["C00001"]["signals"])
    assert r["unknown_lead_ids"] == ["L999"]


def test_sales_owned_stages_are_never_changed(live_rt):
    at(live_rt, "2026-09-07T12:00:00+09:00")
    r = live_rt.execute("score_and_qualify_leads", {"lead_ids": ["L103", "L105"]})
    assert {x["stage"] for x in r["leads"]} == {"customer", "opportunity"}
    assert not any(x["stage_changed"] for x in r["leads"])


def test_low_fit_paid_social_leads_stay_unqualified(live_rt):
    stages = {live_rt.store.leads[f"L11{i}"].stage for i in range(5)}
    assert stages == {"lead"}

import json
from datetime import datetime
from pathlib import Path

import pytest

from dm_agent.cli import SCENARIO, build_runtime
from dm_agent.workflow import install_default_playbook


@pytest.fixture
def scenario():
    return json.loads(Path(SCENARIO).read_text(encoding="utf-8"))


def _rt(scenario, live):
    rt = build_runtime(scenario, live_mocks=live)
    install_default_playbook(rt)
    return rt


@pytest.fixture
def live_rt(scenario):
    return _rt(scenario, True)


@pytest.fixture
def dry_rt(scenario):
    return _rt(scenario, False)


def at(rt, iso):
    rt.advance_to(datetime.fromisoformat(iso))


def run_live(rt, scenario, *steps):
    """Replay named steps of scenario["live"] in order, advancing the clock to each step's last event."""
    live = scenario["live"]
    out = {}
    for name in steps:
        step = live[name]
        items = step.get("events") or step.get("touchpoints") or [step.get("submission", {})]
        at(rt, max(x["timestamp"] for x in items))
        if "events" in step:
            out[name] = rt.execute("ma_track_activity", step)
        elif "submission" in step:
            out[name] = rt.execute("ma_manage_form", step)
        else:
            lead_id = step.get("lead_id") or out.get("form_submit", {}).get("customer_id") or "C00001"
            out[name] = rt.execute("sync_lead_activity", {"lead_id": lead_id, **step})
    return out

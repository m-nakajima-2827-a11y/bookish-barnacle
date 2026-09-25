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

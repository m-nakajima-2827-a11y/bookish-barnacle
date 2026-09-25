import json
from pathlib import Path

import pytest

from dm_agent.cli import SCENARIO, build_runtime
from dm_agent.workflow import install_default_playbook


@pytest.fixture
def scenario():
    return json.loads(Path(SCENARIO).read_text(encoding="utf-8"))


@pytest.fixture
def live_rt(scenario):
    rt = build_runtime(scenario, live_mocks=True)
    install_default_playbook(rt)
    return rt


@pytest.fixture
def dry_rt(scenario):
    rt = build_runtime(scenario, live_mocks=False)
    install_default_playbook(rt)
    return rt

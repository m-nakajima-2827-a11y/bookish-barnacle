"""Exercises the tool-use loop with a scripted fake client (no API key needed)."""

from types import SimpleNamespace as NS

from dm_agent.llm_agent import run_agent


class FakeMessages:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


def test_loop_executes_tools_and_returns_text(live_rt):
    tool_turn = NS(stop_reason="tool_use", content=[
        NS(type="tool_use", id="tu_1", name="score_and_qualify_leads", input={"lead_ids": ["L101"]}),
        NS(type="tool_use", id="tu_2", name="trigger_nurture_action", input={"lead_id": "L101", "action": "send_fax"}),
    ])
    final = NS(stop_reason="end_turn", content=[NS(type="text", text="完了しました")])
    fake = FakeMessages([tool_turn, final])

    out = run_agent(live_rt, "L101を評価して", client=NS(beta=NS(messages=fake)), verbose=False)

    assert out == "完了しました"
    first = fake.calls[0]
    assert first["fallbacks"] == "default" and first["thinking"] == {"type": "adaptive"}
    assert len(first["tools"]) == 7
    results = fake.calls[1]["messages"][2]["content"]  # user, assistant(tool_use), user(tool_results)
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]
    assert results[0]["is_error"] is False and '"fit"' in results[0]["content"]
    assert results[1]["is_error"] is True  # invalid enum rejected by schema validation

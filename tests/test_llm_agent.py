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
        NS(type="text", text="確認します"),
        NS(type="tool_use", id="tu_1", name="predict_customer_intent_and_churn",
           input={"customer_id": "C006", "prediction_targets": ["churn_risk", "optimal_channel"]}),
        NS(type="tool_use", id="tu_2", name="trigger_personalized_outreach",
           input={"customer_id": "C006", "selected_channel": "fax", "campaign_scenario": "churn_prevention"}),
    ])
    final = NS(stop_reason="end_turn", content=[NS(type="text", text="完了しました")])
    fake = FakeMessages([tool_turn, final])
    client = NS(beta=NS(messages=fake))

    out = run_agent(live_rt, "C006の離脱リスクを確認して", client=client, verbose=False)

    assert out == "完了しました"
    first = fake.calls[0]
    assert first["fallbacks"] == "default" and first["thinking"] == {"type": "adaptive"}
    assert len(first["tools"]) == 5
    results = fake.calls[1]["messages"][2]["content"]  # user, assistant(tool_use), user(tool_results)
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]  # all results in one user message
    assert results[0]["is_error"] is False and '"churn_risk"' in results[0]["content"]
    assert results[1]["is_error"] is True  # invalid channel enum rejected by schema validation

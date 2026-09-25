import pytest

from dm_agent.registry import TOOL_ORDER, ToolValidationError, load_schemas, to_anthropic, to_openai, validate_input


def test_all_schemas_load_and_export():
    schemas = load_schemas()
    assert list(schemas) == TOOL_ORDER
    assert [t["function"]["name"] for t in to_openai(schemas)] == TOOL_ORDER
    assert all("input_schema" in t for t in to_anthropic(schemas))


def test_validation_rejects_bad_enum_and_missing_required():
    spec = load_schemas()["trigger_personalized_outreach"]
    with pytest.raises(ToolValidationError):
        validate_input(spec, {"customer_id": "C1", "selected_channel": "fax", "campaign_scenario": "abandoned_cart"})
    with pytest.raises(ToolValidationError):
        validate_input(spec, {"customer_id": "C1"})


def test_runtime_returns_error_instead_of_raising(live_rt):
    r = live_rt.execute("optimize_ad_and_social_campaigns", {"platform": "tiktok", "action": "update_budget"})
    assert r["error"] == "invalid_arguments"


def test_exported_files_are_up_to_date():
    import json

    from dm_agent.registry import SCHEMA_DIR

    schemas = load_schemas()
    for fmt, fn in (("openai", to_openai), ("anthropic", to_anthropic)):
        on_disk = json.loads((SCHEMA_DIR / "export" / f"tools.{fmt}.json").read_text(encoding="utf-8"))
        assert on_disk == fn(schemas), f"run: python -m dm_agent export-tools --format {fmt} > schemas/export/tools.{fmt}.json"

"""Tool (skill) schema registry: load, validate, and export to framework formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"

TOOL_ORDER = [
    "sync_lead_activity",
    "score_and_qualify_leads",
    "trigger_nurture_action",
    "optimize_lead_gen_campaigns",
    "build_utm_tracking_url",
    "plan_social_content_calendar",
    "analyze_marketing_funnel",
]


class ToolValidationError(ValueError):
    pass


def load_schemas(schema_dir: Path = SCHEMA_DIR) -> dict[str, dict[str, Any]]:
    schemas = {}
    for name in TOOL_ORDER:
        spec = json.loads((schema_dir / f"{name}.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec["parameters"])
        schemas[name] = spec
    return schemas


def validate_input(spec: dict[str, Any], args: dict[str, Any]) -> None:
    validator = Draft202012Validator(spec["parameters"], format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(args), key=lambda e: list(e.path))
    if errors:
        msgs = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors]
        raise ToolValidationError("; ".join(msgs))


def to_openai(schemas: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenAI function-calling / LangChain `convert_to_openai_tool` compatible format."""
    return [{"type": "function", "function": spec} for spec in schemas.values()]


def to_anthropic(schemas: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Claude Messages API `tools` format."""
    return [
        {"name": s["name"], "description": s["description"], "input_schema": s["parameters"]}
        for s in schemas.values()
    ]

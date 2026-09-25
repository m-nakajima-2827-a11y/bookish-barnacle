"""Claude-driven agent: a manual tool-use loop over the BtoB marketing skills.

The model decides which skills to call; every call still goes through
AgentRuntime.execute (schema validation + guardrails + audit log).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import to_anthropic
from .runtime import AgentRuntime

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")
DEFAULT_MODEL = "claude-opus-5"


def run_agent(rt: AgentRuntime, user_request: str, model: str = DEFAULT_MODEL, max_turns: int = 20,
              verbose: bool = True, client: Any = None) -> str:
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    tools = to_anthropic(rt.schemas)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_request}]

    for _ in range(max_turns):
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=tools,
            thinking={"type": "adaptive"},
            messages=messages,
            # Server-side refusal fallback: routes a declined turn to a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return "リクエストはモデルにより処理されませんでした（refusal）。依頼内容を見直してください。"
        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            return "".join(b.text for b in response.content if b.type == "text")

        results = []
        for tu in tool_uses:
            result = rt.execute(tu.name, dict(tu.input), origin="llm")
            if verbose:
                print(f"  → {tu.name}({json.dumps(tu.input, ensure_ascii=False)[:200]})")
            results.append({"type": "tool_result", "tool_use_id": tu.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                            "is_error": "error" in result})
        messages.append({"role": "user", "content": results})
    return f"最大ターン数（{max_turns}）に達したため停止しました。"

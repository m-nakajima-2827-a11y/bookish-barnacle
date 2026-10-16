"""Initial MA objects from the client config (forms, segments, scoring rules, popups, scenarios)."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..runtime import AgentRuntime


def nurture_scenario_id(track: str) -> str:
    return f"nurture_{track}"


def seed_ma(rt: "AgentRuntime") -> None:
    cfg = copy.deepcopy(rt.client.get("ma", {}))
    ma = rt.ma
    ma.score_definition = {"common": cfg.get("score_common", {}), "individual": cfg.get("score_rules", [])}
    for f in cfg.get("forms", []):
        ma.forms[f["form_id"]] = {**f, "created_at": rt.now().isoformat()}
    for s in cfg.get("segments", []):
        ma.segments[s["segment_id"]] = {**s, "status": "active"}
    for p in cfg.get("popups", []):
        ma.popups[p["popup_id"]] = {**p, "status": "active", "stats": {"views": 0, "clicks": 0}}
    for sc in cfg.get("scenarios", []):
        ma.scenarios[sc["scenario_id"]] = {**sc, "status": "active"}
    # 業界別の育成シナリオ（リード育成）は nurture_tracks から生成。トリガーは trigger_nurture_action からの登録。
    exit_stages = ["sql", "opportunity", "customer", "disqualified"]
    for track, steps in rt.client["nurture_tracks"].items():
        ma.scenarios[nurture_scenario_id(track)] = {
            "scenario_id": nurture_scenario_id(track), "name": f"育成シナリオ（{track}）", "status": "active",
            "trigger": {"type": "manual", "key": None},
            "steps": [{"day": s["day"], "action": "send_email", "skip_if_consumed": True,
                       "email": {"subject": s["subject"], "asset_id": s["asset_id"], "campaign": f"nurture_{track}"}}
                      for s in steps],
            "exit_conditions": {"lead_stages": exit_stages}, "allow_reentry": False}

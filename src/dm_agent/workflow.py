"""BtoB automation playbook: lead capture → scoring → nurture / sales handoff → recontact.

Deterministic rules handle the routine, time-sensitive reactions (e.g. the 30-minute
first-contact rule) so they don't wait on an LLM. The LLM agent works on top of the
same tools for analysis, planning and exceptions.
"""

from __future__ import annotations

from .runtime import AgentRuntime

AD_PLATFORMS_FOR_EXCLUSION = ("google_ads", "meta_ads")


def install_default_playbook(rt: AgentRuntime) -> None:
    def rescore(rt: AgentRuntime, origin: str, lead_id: str, **_) -> None:
        # 1) Conversions (資料DL・セミナー申込・問い合わせ) and high-intent activity
        #    (セミナー参加・料金ページ・事例閲覧) re-score the lead immediately.
        rt.execute("score_and_qualify_leads", {"lead_ids": [lead_id]}, origin="playbook")

    def on_mql(rt: AgentRuntime, origin: str, lead_id: str) -> None:
        # 2) MQL → industry-specific nurture track (IT / 製造業 / 汎用).
        rt.execute("trigger_nurture_action", {"lead_id": lead_id, "action": "enroll_nurture_track"}, origin="playbook")

    def on_hot(rt: AgentRuntime, origin: str, lead_id: str) -> None:
        # 3) Hot lead → inside-sales task with a first-contact deadline (SLA).
        rt.execute("trigger_nurture_action", {"lead_id": lead_id, "action": "sales_handoff"}, origin="playbook")

    def on_pipeline_change(rt: AgentRuntime, origin: str, lead_id: str, **_) -> None:
        # 4) Stop spending ad budget on companies already in sales conversations or won.
        for platform in AD_PLATFORMS_FOR_EXCLUSION:
            for seg in ("open_opportunities", "customers"):
                rt.execute("optimize_lead_gen_campaigns", {"platform": platform, "action": "sync_audience_exclusion",
                                                           "target_segment_id": seg}, origin="playbook")

    def on_lost(rt: AgentRuntime, origin: str, lead_id: str, lost_reason: str | None = None, **_) -> None:
        # 5) Lost on timing/budget → recontact task at the (assumed) budget-planning month.
        if lost_reason in {"timing", "budget"}:
            rt.execute("trigger_nurture_action", {"lead_id": lead_id, "action": "schedule_recontact"}, origin="playbook")

    rt.on("lead_converted", rescore)
    rt.on("high_intent_activity", rescore)
    rt.on("lead_mql", on_mql)
    rt.on("lead_hot", on_hot)
    rt.on("lead_handed_off", on_pipeline_change)
    rt.on("opportunity_created", on_pipeline_change)
    rt.on("deal_won", on_pipeline_change)
    rt.on("deal_lost", on_lost)

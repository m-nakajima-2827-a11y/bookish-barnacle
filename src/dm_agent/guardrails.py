"""Policy guardrails applied before any outward-facing action (ad changes, message sends)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .cdp import CDPStore, parse_ts


class Guardrails:
    def __init__(self, policy: dict[str, Any]):
        self.policy = policy
        self.tz = ZoneInfo(policy.get("timezone", "Asia/Tokyo"))

    @property
    def dry_run(self) -> bool:
        return self.policy.get("execution_mode", "dry_run") != "live"

    # --- ads -------------------------------------------------------------
    def clamp_budget_change(self, current: float, proposed: float) -> tuple[float, bool, str | None]:
        """Returns (new_budget, needs_approval, note)."""
        cfg = self.policy["ads"]
        max_ratio = cfg["max_daily_budget_change_ratio"]
        lo, hi = current * (1 - max_ratio), current * (1 + max_ratio)
        note = None
        new = min(max(proposed, lo), hi)
        if new != proposed:
            note = f"変更幅上限±{max_ratio:.0%}で補正（提案 {proposed:,.0f} → {new:,.0f}）"
        ratio = abs(new - current) / current if current else 1.0
        return round(new), ratio > cfg["require_human_approval_over_ratio"], note

    # --- outreach ---------------------------------------------------------
    def check_outreach(self, store: CDPStore, customer_id: str, channel: str, scenario: str,
                       now: datetime, discount_rate: float | None) -> list[str]:
        cfg = self.policy["outreach"]
        violations = []
        p = store.profiles.get(customer_id)
        if p is None:
            return ["unknown_customer: CDPに顧客プロファイルが存在しません"]
        if cfg.get("require_consent") and not p.consent.get(channel, False):
            violations.append(f"no_consent: {channel} の配信同意がありません（個人情報保護法・特定電子メール法対応）")
        sent = [r for r in store.outreach_log if r["customer_id"] == customer_id and r["status"] == "sent"]
        recent = [r for r in sent if now - parse_ts(r["sent_at"]) < timedelta(days=7)]
        if len(recent) >= cfg["frequency_cap_per_customer_per_7days"]:
            violations.append("frequency_cap: 直近7日の配信上限に到達しています")
        cooldown = timedelta(days=cfg["same_scenario_cooldown_days"])
        if any(r["campaign_scenario"] == scenario and now - parse_ts(r["sent_at"]) < cooldown for r in sent):
            violations.append(f"cooldown: 同一シナリオを{cfg['same_scenario_cooldown_days']}日以内に配信済みです")
        if discount_rate is not None and discount_rate > cfg["max_discount_rate"]:
            violations.append(f"discount_cap: 割引率{discount_rate:.0%}が上限{cfg['max_discount_rate']:.0%}を超えています")
        return violations

    def in_quiet_hours(self, channel: str, now: datetime) -> bool:
        q = self.policy["outreach"]["quiet_hours"]
        if channel not in q["channels"]:
            return False
        local = now.astimezone(self.tz).time()
        start, end = time.fromisoformat(q["start"]), time.fromisoformat(q["end"])
        return local >= start or local < end if start > end else start <= local < end

    def next_send_time(self, now: datetime) -> datetime:
        end = time.fromisoformat(self.policy["outreach"]["quiet_hours"]["end"])
        local = now.astimezone(self.tz)
        candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        return candidate

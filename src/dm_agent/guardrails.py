"""Policy guardrails applied before any outward-facing action (emails, sales tasks, ad changes)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .store import Lead, LeadStore, parse_ts

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Guardrails:
    def __init__(self, policy: dict[str, Any]):
        self.policy = policy
        self.tz = ZoneInfo(policy.get("timezone", "Asia/Tokyo"))

    @property
    def dry_run(self) -> bool:
        return self.policy.get("execution_mode", "dry_run") != "live"

    # --- business hours (year-end closure via closed_dates_mmdd; national holidays need a calendar) ---
    def _bh(self):
        bh = self.policy["business_hours"]
        return set(bh["days"]), time.fromisoformat(bh["start"]), time.fromisoformat(bh["end"])

    def is_business_day(self, local: datetime) -> bool:
        days, _, _ = self._bh()
        closed = set(self.policy["business_hours"].get("closed_dates_mmdd", []))
        return DAYS[local.weekday()] in days and local.strftime("%m-%d") not in closed

    def in_business_hours(self, now: datetime) -> bool:
        _, start, end = self._bh()
        local = now.astimezone(self.tz)
        return self.is_business_day(local) and start <= local.time() < end

    def next_business_open(self, now: datetime) -> datetime:
        if self.in_business_hours(now):
            return now
        _, start, _ = self._bh()
        local = now.astimezone(self.tz)
        candidate = local.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        while not self.is_business_day(candidate):
            candidate += timedelta(days=1)
        return candidate

    def add_business_minutes(self, now: datetime, minutes: int) -> datetime:
        _, _, end = self._bh()
        t = self.next_business_open(now)
        while minutes > 0:
            day_end = t.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
            available = int((day_end - t).total_seconds() // 60)
            if minutes <= available:
                return t + timedelta(minutes=minutes)
            minutes -= available
            t = self.next_business_open(day_end)
        return t

    # --- email ---------------------------------------------------------------
    def check_email(self, store: LeadStore, lead: Lead, asset_id: str | None, now: datetime) -> list[str]:
        cfg = self.policy["email"]
        v = []
        if lead.unsubscribed:
            v.append("unsubscribed: 配信停止済みのリードです")
        elif cfg["require_opt_in"] and not lead.email_opt_in:
            v.append("no_opt_in: メール配信の同意がありません（特定電子メール法）")
        if lead.stage in {"disqualified"}:
            v.append("disqualified: 対象外リードです")
        sent = [r for r in store.email_log if r["lead_id"] == lead.lead_id and r["status"] == "sent"]
        if sum(now - parse_ts(r["sent_at"]) < timedelta(days=7) for r in sent) >= cfg["frequency_cap_per_lead_per_7days"]:
            v.append("frequency_cap: 直近7日の配信上限に到達しています")
        if asset_id and any(r.get("asset_id") == asset_id and now - parse_ts(r["sent_at"]) < timedelta(days=cfg["same_asset_resend_block_days"]) for r in sent):
            v.append(f"duplicate_asset: {asset_id} は{cfg['same_asset_resend_block_days']}日以内に送信済みです")
        return v

    # --- ads -------------------------------------------------------------------
    def clamp_budget_change(self, current: float, proposed: float) -> tuple[float, bool, str | None]:
        cfg = self.policy["ads"]
        r = cfg["max_daily_budget_change_ratio"]
        new = min(max(proposed, current * (1 - r)), current * (1 + r))
        note = f"変更幅上限±{r:.0%}で補正（提案 {proposed:,.0f} → {new:,.0f}）" if new != proposed else None
        ratio = abs(new - current) / current if current else 1.0
        return round(new), ratio > cfg["require_human_approval_over_ratio"], note

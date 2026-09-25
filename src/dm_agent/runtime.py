"""Agent runtime: tool dispatch with validation, clock, scheduler, event bus, approvals, audit log."""

from __future__ import annotations

import heapq
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .connectors import MockAdPlatform, MockCRM, MockEmail
from .guardrails import Guardrails
from .registry import ROOT, ToolValidationError, load_schemas, validate_input
from .skills import HANDLERS
from .store import LeadStore

CONFIG_DIR = ROOT / "config"
DEFAULT_CLIENT = "sample_sales_consulting"


def load_client(client_id: str) -> dict[str, Any]:
    """Per-client settings (ICP, scoring, content, UTM dictionary) — one file per client."""
    return json.loads((CONFIG_DIR / "clients" / f"{client_id}.json").read_text(encoding="utf-8"))


class AgentRuntime:
    def __init__(self, client_id: str = DEFAULT_CLIENT, policy: dict[str, Any] | None = None,
                 client: dict[str, Any] | None = None, store: LeadStore | None = None,
                 ad_platforms: dict[str, Any] | None = None, email: Any = None, crm: Any = None,
                 now: datetime | None = None):
        self.policy = policy or json.loads((CONFIG_DIR / "policy.json").read_text(encoding="utf-8"))
        self.client = client or load_client(client_id)
        self.store = store or LeadStore()
        self.guardrails = Guardrails(self.policy)
        self.ad_platforms = ad_platforms if ad_platforms is not None else {
            n: MockAdPlatform(n) for n in ("google_ads", "yahoo_ads", "meta_ads", "linkedin_ads")}
        self.email = email or MockEmail()
        self.crm = crm or MockCRM()
        self.schemas = load_schemas()
        self._clock = now
        self._jobs: list[tuple[datetime, int, str, dict[str, Any]]] = []
        self._seq = itertools.count()
        self._subscribers: dict[str, list[Callable[..., None]]] = {}
        self.approvals: list[dict[str, Any]] = []
        self.audit_log: list[dict[str, Any]] = []
        self._origins: list[str] = []

    # --- clock / scheduler ---------------------------------------------------
    def now(self) -> datetime:
        return self._clock or datetime.now(timezone.utc)

    def schedule(self, at: datetime, tool: str, args: dict[str, Any]) -> None:
        heapq.heappush(self._jobs, (at, next(self._seq), tool, args))
        self.audit_log.append({"at": self.now().isoformat(), "type": "scheduled", "tool": tool,
                               "run_at": at.isoformat(), "args": args})

    def pending_jobs(self) -> list[dict[str, Any]]:
        return [{"run_at": at.isoformat(), "tool": t, "args": a} for at, _, t, a in sorted(self._jobs)]

    def advance_to(self, until: datetime) -> list[dict[str, Any]]:
        """Run every job due up to `until` (simulated or wall-clock), in time order."""
        results = []
        while self._jobs and self._jobs[0][0] <= until:
            at, _, tool, args = heapq.heappop(self._jobs)
            self._clock = max(self.now(), at)
            results.append({"tool": tool, "result": self.execute(tool, args, origin="scheduler")})
        self._clock = max(self.now(), until)
        return results

    # --- events -------------------------------------------------------------
    def on(self, event: str, fn: Callable[..., None]) -> None:
        self._subscribers.setdefault(event, []).append(fn)

    def emit(self, event: str, **data: Any) -> None:
        self.audit_log.append({"at": self.now().isoformat(), "type": "event", "event": event,
                               **{k: v for k, v in data.items() if k != "result"}})
        origin = self._origins[-1] if self._origins else "direct"
        for fn in self._subscribers.get(event, []):
            fn(self, origin=origin, **data)

    # --- approvals ----------------------------------------------------------
    def request_approval(self, operation: str, **params: Any) -> None:
        self.approvals.append({"id": f"apr-{len(self.approvals) + 1:04d}", "operation": operation,
                               "params": params, "status": "pending", "requested_at": self.now().isoformat()})

    def approve(self, approval_id: str) -> dict[str, Any]:
        a = next(x for x in self.approvals if x["id"] == approval_id)
        if a["status"] != "pending":
            return a
        if a["operation"] == "set_daily_budget" and not self.guardrails.dry_run:
            p = a["params"]
            self.ad_platforms[p["platform"]].set_daily_budget(p["campaign_id"], p["amount"])
            a["status"] = "applied"
        else:
            a["status"] = "approved_not_applied_dry_run"
        self.audit_log.append({"at": self.now().isoformat(), "type": "approval", **a})
        return a

    # --- tool dispatch ------------------------------------------------------
    def execute(self, tool: str, args: dict[str, Any], origin: str = "direct") -> dict[str, Any]:
        entry = {"at": self.now().isoformat(), "type": "tool_call", "tool": tool, "origin": origin, "args": args}
        if tool not in HANDLERS:
            result = {"error": f"unknown tool {tool}"}
        else:
            self._origins.append(origin)
            try:
                validate_input(self.schemas[tool], args)
                result = HANDLERS[tool](self, **args)
            except ToolValidationError as e:
                result = {"error": "invalid_arguments", "detail": str(e)}
            finally:
                self._origins.pop()
        entry["result_summary"] = {k: result[k] for k in ("status", "error", "mode", "applied") if k in result}
        self.audit_log.append(entry)
        return result

    def save_audit_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in self.audit_log) + "\n",
                        encoding="utf-8")

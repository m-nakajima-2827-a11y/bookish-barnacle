"""MA data model. Contact details (email, name, phone) live only here, in `contact`,
and are masked in every tool output and audit log."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PII_KEYS = {"email", "name", "last_name", "first_name", "phone", "tel"}


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_pii(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: (mask_email(v) if k == "email" and isinstance(v, str) else "***" if k in PII_KEYS and v else mask_pii(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_pii(v) for v in obj]
    return obj


@dataclass
class Profile:
    """SATORI でいう「カスタマー」。customer_id が無い間は匿名客。"""
    profile_id: str
    customer_id: str | None = None
    cookies: list[str] = field(default_factory=list)
    created_at: str | None = None
    last_seen: str | None = None
    activities: list[dict[str, Any]] = field(default_factory=list)
    score: int = 0
    score_log: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    push_subscribed: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)
    contact: dict[str, Any] = field(default_factory=dict)
    email_opt_in: bool = False
    unsubscribed: bool = False

    @property
    def identified(self) -> bool:
        return self.customer_id is not None

    def public(self, with_activity: int = 0) -> dict[str, Any]:
        d = {"profile_id": self.profile_id, "customer_id": self.customer_id, "identified": self.identified,
             "score": self.score, "tags": self.tags, "segments": self.segments, "push_subscribed": self.push_subscribed,
             "attributes": self.attributes, "contact": mask_pii(self.contact), "email_opt_in": self.email_opt_in,
             "unsubscribed": self.unsubscribed, "created_at": self.created_at, "last_seen": self.last_seen,
             "activity_count": len(self.activities)}
        if with_activity:
            d["recent_activity"] = self.activities[-with_activity:]
        return d


class MAStore:
    def __init__(self):
        self.profiles: dict[str, Profile] = {}
        self.cookie_index: dict[str, str] = {}
        self.email_index: dict[str, str] = {}  # lower(email) -> profile_id（名寄せ）
        self.forms: dict[str, dict[str, Any]] = {}
        self.form_submissions: list[dict[str, Any]] = []
        self.pages: dict[str, dict[str, Any]] = {}
        self.segments: dict[str, dict[str, Any]] = {}
        self.score_definition: dict[str, Any] = {"common": {}, "individual": []}
        self.scenarios: dict[str, dict[str, Any]] = {}
        self.enrollments: dict[str, dict[str, Any]] = {}  # f"{scenario_id}|{profile_id}"
        self.emails: list[dict[str, Any]] = []
        self.email_tokens: dict[str, int] = {}  # token -> index in emails
        self.popups: dict[str, dict[str, Any]] = {}
        self.pushes: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.seq: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        self.seq[prefix] = self.seq.get(prefix, 0) + 1
        return f"{prefix}{self.seq[prefix]:05d}"

    def by_customer(self, customer_id: str) -> Profile | None:
        p = self.profiles.get(customer_id)
        return p if p and p.customer_id == customer_id else None

    def save(self, path: Path) -> None:
        data = {k: v for k, v in self.__dict__.items() if k != "profiles"}
        data["profiles"] = {k: asdict(v) for k, v in self.profiles.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MAStore":
        s = cls()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.items():
                setattr(s, k, {pid: Profile(**p) for pid, p in v.items()} if k == "profiles" else v)
        return s

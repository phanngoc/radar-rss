"""Data models for filter proposals, evaluations, and audit entries."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal


ChangeAction = Literal["add_keyword", "remove_keyword", "add_regex", "remove_regex"]


@dataclass
class FilterChange:
    action: ChangeAction
    topic: str
    value: str
    reasoning: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Proposal:
    id: str
    created_at: str
    status: Literal["pending", "applied", "rejected"]
    base_version: int
    changes: list[FilterChange]
    impact: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "status": self.status,
            "base_version": self.base_version,
            "changes": [c.to_dict() for c in self.changes],
            "impact": self.impact,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Proposal":
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            status=data["status"],
            base_version=data["base_version"],
            changes=[FilterChange(**c) for c in data["changes"]],
            impact=data.get("impact", {}),
        )

    @staticmethod
    def new_id() -> str:
        return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


@dataclass
class Evaluation:
    date: str
    filter_version: int
    total_articles: int
    classified: int
    unclassified: int
    multi_match: int
    per_topic: dict = field(default_factory=dict)

    @property
    def unclassified_rate(self) -> float:
        return self.unclassified / self.total_articles if self.total_articles else 0.0

    @property
    def multi_match_rate(self) -> float:
        return self.multi_match / self.total_articles if self.total_articles else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["unclassified_rate"] = self.unclassified_rate
        d["multi_match_rate"] = self.multi_match_rate
        return d


@dataclass
class AuditEntry:
    timestamp: str
    event: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def now(cls, event: str, **details) -> "AuditEntry":
        return cls(timestamp=datetime.now().isoformat(), event=event, details=details)

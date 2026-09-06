"""Append-only audit log for filter changes and agent events."""

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
AUDIT_DIR = BASE_DIR / "data" / "audit"


def append_audit(event: str, **details) -> None:
    """Append a JSONL entry to today's audit log."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"{today}.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "details": details,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_audit(date: str | None = None) -> list[dict]:
    """Read audit log entries for a given date (default: today)."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"{date}.jsonl"
    if not log_file.exists():
        return []
    entries = []
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries

"""Apply proposals to filters.json with versioning and rollback."""

import json
import shutil
from datetime import datetime
from pathlib import Path

import radar
from agent import validate
from agent.audit import append_audit
from agent.models import Proposal


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
FILTERS_FILE = DATA_DIR / "filters.json"
PENDING_DIR = DATA_DIR / "proposals" / "pending"
APPLIED_DIR = DATA_DIR / "proposals" / "applied"
VERSIONS_DIR = DATA_DIR / "versions"


def list_pending() -> list[Path]:
    if not PENDING_DIR.exists():
        return []
    return sorted(PENDING_DIR.glob("*.json"))


def load_proposal(path: Path) -> Proposal:
    with open(path, encoding="utf-8") as f:
        return Proposal.from_dict(json.load(f))


def load_current_filters() -> dict:
    with open(FILTERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_today_articles() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    cache = DATA_DIR / "cache" / f"{today}.json"
    if not cache.exists():
        # Use the most recent cache available
        caches = sorted((DATA_DIR / "cache").glob("*.json"))
        if not caches:
            raise FileNotFoundError("No cached articles found. Run radar.py first.")
        cache = caches[-1]
    with open(cache, encoding="utf-8") as f:
        return json.load(f)


def show_proposal(proposal: Proposal) -> None:
    print(f"\nProposal: {proposal.id}")
    print(f"  Status: {proposal.status}")
    print(f"  Base version: {proposal.base_version}")
    print(f"  Changes: {len(proposal.changes)}")
    summary = (proposal.impact or {}).get("summary", "")
    if summary:
        print(f"  Summary: {summary}")
    for i, c in enumerate(proposal.changes):
        print(f"\n  [{i+1}] {c.action} '{c.value}' to/from topic '{c.topic}'")
        print(f"      Reasoning: {c.reasoning}")
        if c.evidence:
            print(f"      Evidence ({len(c.evidence)} articles):")
            for ev in c.evidence[:3]:
                print(f"        - {ev[:100]}")


def show_impact(impact: dict) -> None:
    print(f"\n  Newly classified: {impact['newly_classified']}")
    print(f"  No longer classified: {impact['no_longer_classified']}")
    print(f"  Net change: {impact['net_classified_change']:+d}")
    print(f"\n  Per-topic deltas:")
    for topic, delta in impact["per_topic"].items():
        if delta["delta"] != 0:
            sign = "+" if delta["delta"] > 0 else ""
            print(f"    {topic}: {delta['before']} → {delta['after']} ({sign}{delta['delta']})")


def write_filters(new_filters: dict) -> int:
    """Write new filters with bumped version, save old as version snapshot."""
    new_version = new_filters.get("version", 1) + 1
    new_filters["version"] = new_version
    new_filters["updated_at"] = datetime.now().isoformat()

    # Snapshot the OLD filters to versions/
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if FILTERS_FILE.exists():
        with open(FILTERS_FILE, encoding="utf-8") as f:
            old = json.load(f)
        old_version = old.get("version", 1)
        snapshot = VERSIONS_DIR / f"filters.v{old_version}.json"
        if not snapshot.exists():
            shutil.copy(FILTERS_FILE, snapshot)

    with open(FILTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_filters, f, ensure_ascii=False, indent=2)

    return new_version


def archive_proposal(path: Path, status: str) -> None:
    """Move proposal from pending/ to applied/ with updated status."""
    APPLIED_DIR.mkdir(parents=True, exist_ok=True)
    proposal = load_proposal(path)
    proposal.status = status
    target = APPLIED_DIR / path.name
    with open(target, "w", encoding="utf-8") as f:
        json.dump(proposal.to_dict(), f, ensure_ascii=False, indent=2)
    path.unlink()


def apply_proposal(
    proposal_path: Path,
    auto: bool = False,
    dry_run: bool = False,
) -> bool:
    """Apply one proposal. Returns True if applied, False if skipped/rejected."""
    proposal = load_proposal(proposal_path)
    current_filters = load_current_filters()
    articles = load_today_articles()

    show_proposal(proposal)

    result = validate.full_validate(proposal, current_filters, articles)

    if not result["ok"]:
        print("\n[REJECTED] Validation errors:")
        for err in result["errors"]:
            print(f"  - {err}")
        if not dry_run:
            archive_proposal(proposal_path, "rejected")
            append_audit(
                "proposal_rejected",
                proposal_id=proposal.id,
                errors=result["errors"],
            )
        return False

    show_impact(result["impact"])

    if dry_run:
        print("\n[DRY-RUN] Would apply if not in dry-run mode.")
        return False

    if not auto:
        ans = input("\nApply this proposal? [y/N] ").strip().lower()
        if ans != "y":
            print("Skipped.")
            return False

    new_version = write_filters(result["new_filters"])
    archive_proposal(proposal_path, "applied")
    append_audit(
        "proposal_applied",
        proposal_id=proposal.id,
        new_version=new_version,
        impact=result["impact"],
    )
    print(f"\n[APPLIED] Filters now at version {new_version}")
    return True


def apply_all(auto: bool = False, dry_run: bool = False) -> dict:
    """Process all pending proposals."""
    pending = list_pending()
    if not pending:
        print("No pending proposals.")
        return {"applied": 0, "rejected": 0, "skipped": 0}

    print(f"Found {len(pending)} pending proposal(s).")
    counts = {"applied": 0, "rejected": 0, "skipped": 0}
    for path in pending:
        applied = apply_proposal(path, auto=auto, dry_run=dry_run)
        if applied:
            counts["applied"] += 1
        else:
            # Distinguish rejected vs skipped via file existence after call
            if path.exists():
                counts["skipped"] += 1
            else:
                counts["rejected"] += 1
    return counts


def rollback(target_version: int) -> bool:
    """Rollback filters.json to a specific version."""
    snapshot = VERSIONS_DIR / f"filters.v{target_version}.json"
    if not snapshot.exists():
        print(f"No snapshot for version {target_version}")
        return False

    current = load_current_filters()
    current_version = current.get("version", 1)

    # Snapshot current before rollback
    cur_snap = VERSIONS_DIR / f"filters.v{current_version}.json"
    if not cur_snap.exists():
        shutil.copy(FILTERS_FILE, cur_snap)

    shutil.copy(snapshot, FILTERS_FILE)
    append_audit(
        "rollback",
        from_version=current_version,
        to_version=target_version,
    )
    print(f"Rolled back from v{current_version} to v{target_version}")
    return True

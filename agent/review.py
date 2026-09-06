"""Main agent review loop: identify problems, call LLM, save proposals."""

import json
import random
import sys
from datetime import datetime
from pathlib import Path

import radar
from agent import llm
from agent.audit import append_audit
from agent.models import FilterChange, Proposal


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
PROPOSALS_DIR = DATA_DIR / "proposals" / "pending"
EVALUATIONS_DIR = DATA_DIR / "evaluations"


def load_today_articles() -> list[dict]:
    """Load articles from today's cache, or fetch fresh if missing."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"{today}.json"
    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)
    # Fallback: fetch fresh
    cfg = radar.load_config()
    articles = radar.fetch_all(cfg["sources"])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False)
    return articles


def find_unclassified(articles: list[dict], topics: list[str]) -> list[dict]:
    """Articles that match zero topics."""
    unclassified = []
    for art in articles:
        if not art.get("title") or not art.get("link"):
            continue
        if not any(radar.topic_matches(t, art) for t in topics):
            unclassified.append(art)
    return unclassified


def find_multi_match(articles: list[dict], topics: list[str], min_topics: int = 4) -> list[dict]:
    """Articles matching too many topics (likely false positives)."""
    result = []
    for art in articles:
        if not art.get("title") or not art.get("link"):
            continue
        matched = [t for t in topics if radar.topic_matches(t, art)]
        if len(matched) >= min_topics:
            result.append({"article": art, "topics": matched})
    return result


def compute_stats(articles: list[dict], topics: list[str]) -> dict:
    """Compute classification statistics."""
    topics_data = radar.filter_by_topics(articles, topics)
    classified_links = set()
    for arts in topics_data.values():
        for a in arts:
            classified_links.add(a["link"])
    valid_articles = [a for a in articles if a.get("title") and a.get("link")]
    classified = len(classified_links)
    total = len(valid_articles)
    return {
        "total_articles": total,
        "classified": classified,
        "unclassified": total - classified,
        "unclassified_rate": round((total - classified) / total, 4) if total else 0,
        "per_topic": {t: len(arts) for t, arts in topics_data.items()},
    }


def load_recent_evaluations(days: int = 7) -> list[dict]:
    """Load recent evaluation snapshots for trend context."""
    if not EVALUATIONS_DIR.exists():
        return []
    files = sorted(EVALUATIONS_DIR.glob("*.json"))[-days:]
    out = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                out.append(json.load(fp))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def build_current_filters_dict() -> dict:
    """Snapshot current filter state for inclusion in LLM prompt."""
    return {
        "version": radar.FILTER_VERSION,
        "topics": {
            t: {
                "keywords": radar.TOPIC_KEYWORDS.get(t, []),
                "regex_patterns": radar.TOPIC_REGEX_KEYWORDS.get(t, []),
                "regex_only": t in radar.REGEX_ONLY_TOPICS,
            }
            for t in radar.ALL_TOPICS
        },
    }


def review(
    sample_unclassified: int = 30,
    sample_multi_match: int = 10,
    dry_run: bool = False,
    seed: int | None = None,
) -> dict:
    """Run the agent review loop. Returns the proposal dict or {} if none."""
    if seed is not None:
        random.seed(seed)

    articles = load_today_articles()
    topics = radar.ALL_TOPICS

    print(f"Loaded {len(articles)} articles from cache")

    stats = compute_stats(articles, topics)
    print(f"Stats: {stats['classified']}/{stats['total_articles']} classified "
          f"({stats['unclassified_rate']*100:.1f}% unclassified)")

    unclassified = find_unclassified(articles, topics)
    multi_match = find_multi_match(articles, topics)
    print(f"Found {len(unclassified)} unclassified, {len(multi_match)} multi-match")

    # Sample for prompt
    uncl_sample = random.sample(unclassified, min(sample_unclassified, len(unclassified)))
    mm_sample = random.sample(multi_match, min(sample_multi_match, len(multi_match)))

    # Trend context
    recent = load_recent_evaluations()
    trend = {
        "recent_unclassified_rates": [
            {"date": e.get("date"), "rate": e.get("unclassified_rate")}
            for e in recent
        ]
    } if recent else None

    current_filters = build_current_filters_dict()

    if dry_run:
        print("\n[DRY-RUN] Would call LLM with:")
        print(f"  - {len(current_filters['topics'])} topics in current filters")
        print(f"  - {len(uncl_sample)} unclassified samples")
        print(f"  - {len(mm_sample)} multi-match samples")
        print(f"  - {len(recent)} recent evaluations for trend")
        print("\n[DRY-RUN] Sample unclassified articles:")
        for art in uncl_sample[:5]:
            print(f"  - [{art.get('source', '?')}] {art.get('title', '')[:80]}")
        return {}

    print("\nCalling LLM...")
    response = llm.call_review(
        current_filters=current_filters,
        unclassified=uncl_sample,
        multi_match=mm_sample,
        stats=stats,
        trend=trend,
    )

    summary = response.get("summary", "")
    changes_data = response.get("changes", [])
    print(f"LLM proposed {len(changes_data)} changes: {summary}")

    if not changes_data:
        append_audit("review_no_changes", stats=stats)
        return {}

    changes = [FilterChange(**c) for c in changes_data]
    proposal = Proposal(
        id=Proposal.new_id(),
        created_at=datetime.now().isoformat(),
        status="pending",
        base_version=radar.FILTER_VERSION,
        changes=changes,
        impact={"summary": summary, "stats_at_review": stats},
    )

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    proposal_file = PROPOSALS_DIR / f"{proposal.id}.json"
    with open(proposal_file, "w", encoding="utf-8") as f:
        json.dump(proposal.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"Saved proposal: {proposal_file}")
    append_audit(
        "proposal_created",
        proposal_id=proposal.id,
        change_count=len(changes),
        summary=summary,
        stats=stats,
    )

    return proposal.to_dict()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    review(dry_run=dry)

"""Proposal validation: syntax, conflict, impact simulation, threshold gates."""

import copy
import re
from typing import Any

import radar
from agent.models import FilterChange, Proposal


MIN_KEYWORD_LENGTH = 3
MIN_KEYWORDS_PER_TOPIC = 3
MAX_CHANGES_PER_PROPOSAL = 5
MAX_REMOVALS_PER_TOPIC = 2
MAX_TOPIC_GROWTH_RATIO = 1.5  # A topic shouldn't grow >50% from one change
MAX_TOPIC_LOSS_RATIO = 0.10   # A topic shouldn't lose >10% articles


class ValidationError(Exception):
    """Raised when a proposal fails validation."""


def validate_syntax(change: FilterChange) -> list[str]:
    """Returns list of error messages (empty if valid)."""
    errors = []

    if change.action not in ("add_keyword", "remove_keyword", "add_regex", "remove_regex"):
        errors.append(f"unknown action: {change.action}")
        return errors

    if change.topic not in radar.ALL_TOPICS:
        errors.append(f"unknown topic: {change.topic}")

    value = (change.value or "").strip()
    if not value:
        errors.append("empty value")
        return errors

    if change.action == "add_keyword":
        if len(value) < MIN_KEYWORD_LENGTH:
            errors.append(
                f"keyword '{value}' is too short ({len(value)} chars, "
                f"min {MIN_KEYWORD_LENGTH}). Use add_regex with word boundaries instead."
            )

    if change.action in ("add_regex", "remove_regex"):
        try:
            re.compile(value)
        except re.error as e:
            errors.append(f"invalid regex '{value}': {e}")

    if not change.reasoning or len(change.reasoning) < 10:
        errors.append("reasoning too short or missing")

    if not change.evidence:
        errors.append("no evidence articles provided")

    return errors


def validate_proposal(proposal: Proposal) -> list[str]:
    """Returns list of error messages for the whole proposal."""
    errors = []

    if len(proposal.changes) == 0:
        errors.append("proposal has no changes")
    if len(proposal.changes) > MAX_CHANGES_PER_PROPOSAL:
        errors.append(
            f"too many changes: {len(proposal.changes)} > {MAX_CHANGES_PER_PROPOSAL}"
        )

    # Per-change syntax
    removals_per_topic: dict[str, int] = {}
    for i, change in enumerate(proposal.changes):
        for err in validate_syntax(change):
            errors.append(f"change[{i}]: {err}")
        if change.action in ("remove_keyword", "remove_regex"):
            removals_per_topic[change.topic] = removals_per_topic.get(change.topic, 0) + 1

    # Per-topic removal cap
    for topic, count in removals_per_topic.items():
        if count > MAX_REMOVALS_PER_TOPIC:
            errors.append(
                f"too many removals for topic '{topic}': {count} > {MAX_REMOVALS_PER_TOPIC}"
            )

    return errors


def apply_changes_to_filters(filters: dict, changes: list[FilterChange]) -> dict:
    """Return a NEW filters dict with changes applied. Does not mutate input."""
    new_filters = copy.deepcopy(filters)
    topics = new_filters["topics"]

    for change in changes:
        if change.topic not in topics:
            continue
        topic_data = topics[change.topic]
        if change.action == "add_keyword":
            kws = topic_data.setdefault("keywords", [])
            if change.value not in kws:
                kws.append(change.value)
        elif change.action == "remove_keyword":
            kws = topic_data.get("keywords", [])
            topic_data["keywords"] = [k for k in kws if k != change.value]
        elif change.action == "add_regex":
            rxs = topic_data.setdefault("regex_patterns", [])
            if change.value not in rxs:
                rxs.append(change.value)
        elif change.action == "remove_regex":
            rxs = topic_data.get("regex_patterns", [])
            topic_data["regex_patterns"] = [r for r in rxs if r != change.value]

    return new_filters


def check_min_keywords(new_filters: dict) -> list[str]:
    """Each topic must retain enough keywords (or regex)."""
    errors = []
    for topic, data in new_filters["topics"].items():
        n = len(data.get("keywords", [])) + len(data.get("regex_patterns", []))
        if n < MIN_KEYWORDS_PER_TOPIC:
            errors.append(
                f"topic '{topic}' would have only {n} matchers (min {MIN_KEYWORDS_PER_TOPIC})"
            )
    return errors


def simulate_impact(articles: list[dict], current_filters: dict, new_filters: dict) -> dict:
    """Run filter_by_topics under both filter sets, return impact metrics."""
    before = _filter_with(articles, current_filters)
    after = _filter_with(articles, new_filters)

    before_classified = _set_of_links(before)
    after_classified = _set_of_links(after)

    newly_classified = after_classified - before_classified
    no_longer_classified = before_classified - after_classified

    per_topic_delta = {}
    for topic in current_filters["topics"]:
        b = len(before.get(topic, []))
        a = len(after.get(topic, []))
        per_topic_delta[topic] = {"before": b, "after": a, "delta": a - b}

    return {
        "newly_classified": len(newly_classified),
        "no_longer_classified": len(no_longer_classified),
        "net_classified_change": len(newly_classified) - len(no_longer_classified),
        "per_topic": per_topic_delta,
    }


def check_impact_thresholds(impact: dict) -> list[str]:
    """Reject if any topic exceeds growth/loss bounds."""
    errors = []
    for topic, delta in impact["per_topic"].items():
        before = delta["before"]
        after = delta["after"]
        if before == 0:
            continue
        if after > before * MAX_TOPIC_GROWTH_RATIO:
            errors.append(
                f"topic '{topic}' grows {before} → {after} (>{int((MAX_TOPIC_GROWTH_RATIO-1)*100)}%)"
            )
        loss = (before - after) / before
        if loss > MAX_TOPIC_LOSS_RATIO:
            errors.append(
                f"topic '{topic}' loses {loss*100:.1f}% articles ({before} → {after})"
            )
    return errors


def _filter_with(articles: list[dict], filters: dict) -> dict[str, list[dict]]:
    """Run filter_by_topics with a custom filters dict (without mutating globals)."""
    topics = list(filters["topics"].keys())
    keywords_map = {t: v["keywords"] for t, v in filters["topics"].items()}
    regex_map = {t: v.get("regex_patterns", []) for t, v in filters["topics"].items()}
    regex_only = {t for t, v in filters["topics"].items() if v.get("regex_only", False)}

    seen = set()
    result: dict[str, list[dict]] = {t: [] for t in topics}
    for art in articles:
        if not art.get("title") or not art.get("link"):
            continue
        text = (art["title"] + " " + art.get("desc", "")).lower()
        for topic in topics:
            kws = keywords_map.get(topic, [])
            if topic not in regex_only:
                kws = list(set(kws + [topic.lower()]))
            matched = any(kw in text for kw in kws)
            if not matched:
                for pattern in regex_map.get(topic, []):
                    if re.search(pattern, text):
                        matched = True
                        break
            key = art["link"] + "|" + topic
            if matched and key not in seen:
                result[topic].append(art)
                seen.add(key)
    return result


def _set_of_links(topics_data: dict) -> set:
    out = set()
    for arts in topics_data.values():
        for a in arts:
            out.add(a["link"])
    return out


def full_validate(
    proposal: Proposal,
    current_filters: dict,
    articles: list[dict],
) -> dict:
    """Run all validation steps. Returns dict with `ok`, `errors`, `impact`, `new_filters`."""
    errors = validate_proposal(proposal)
    if errors:
        return {"ok": False, "errors": errors, "impact": None, "new_filters": None}

    new_filters = apply_changes_to_filters(current_filters, proposal.changes)
    errors.extend(check_min_keywords(new_filters))

    impact = simulate_impact(articles, current_filters, new_filters)
    errors.extend(check_impact_thresholds(impact))

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "impact": impact,
        "new_filters": new_filters,
    }

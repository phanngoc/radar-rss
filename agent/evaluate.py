"""Daily evaluation: metrics + LLM-as-judge precision sampling."""

import json
import random
from datetime import datetime
from pathlib import Path

import radar
from agent import llm
from agent.audit import append_audit
from agent.models import Evaluation


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
EVALUATIONS_DIR = DATA_DIR / "evaluations"


def load_today_articles() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    cache = CACHE_DIR / f"{today}.json"
    if not cache.exists():
        caches = sorted(CACHE_DIR.glob("*.json"))
        if not caches:
            raise FileNotFoundError("No cached articles available")
        cache = caches[-1]
    with open(cache, encoding="utf-8") as f:
        return json.load(f)


def compute_metrics(articles: list[dict], topics: list[str]) -> dict:
    """Compute coverage metrics: classified, unclassified, multi-match counts per topic."""
    topics_data = radar.filter_by_topics(articles, topics)

    valid = [a for a in articles if a.get("title") and a.get("link")]
    total = len(valid)

    # Track topic count per article
    article_topic_count: dict[str, int] = {}
    for topic, arts in topics_data.items():
        for a in arts:
            article_topic_count[a["link"]] = article_topic_count.get(a["link"], 0) + 1

    classified_count = len(article_topic_count)
    unclassified = total - classified_count
    multi_match = sum(1 for c in article_topic_count.values() if c >= 4)

    per_topic = {}
    for topic, arts in topics_data.items():
        per_topic[topic] = {"matched": len(arts)}

    return {
        "total_articles": total,
        "classified": classified_count,
        "unclassified": unclassified,
        "multi_match": multi_match,
        "per_topic": per_topic,
        "topics_data": topics_data,
    }


def llm_judge_sample(
    topics_data: dict[str, list[dict]],
    sample_per_topic: int = 5,
    seed: int | None = None,
) -> dict:
    """Sample articles per topic, ask LLM if correctly classified, return per-topic precision."""
    if seed is not None:
        random.seed(seed)

    judgements = {}
    for topic, arts in topics_data.items():
        if not arts:
            judgements[topic] = {"sample_size": 0, "correct": 0, "partial": 0, "incorrect": 0}
            continue
        sample = random.sample(arts, min(sample_per_topic, len(arts)))
        correct = partial = incorrect = 0
        details = []
        for art in sample:
            try:
                verdict = llm.call_judge(art, topic)
                v = verdict.get("verdict", "partial")
            except Exception as e:
                details.append({"title": art.get("title", "")[:80], "error": str(e)})
                continue
            details.append({
                "title": art.get("title", "")[:80],
                "verdict": v,
                "reasoning": verdict.get("reasoning", "")[:200],
            })
            if v == "correct":
                correct += 1
            elif v == "partial":
                partial += 1
            elif v == "incorrect":
                incorrect += 1
        n = correct + partial + incorrect
        judgements[topic] = {
            "sample_size": n,
            "correct": correct,
            "partial": partial,
            "incorrect": incorrect,
            "precision": round(correct / n, 3) if n else 0.0,
            "samples": details,
        }
    return judgements


def evaluate(use_llm_judge: bool = False, sample_per_topic: int = 5) -> Evaluation:
    """Run full evaluation, save snapshot to disk, return Evaluation."""
    articles = load_today_articles()
    metrics = compute_metrics(articles, radar.ALL_TOPICS)

    per_topic = metrics["per_topic"]

    if use_llm_judge:
        print("Running LLM judge sampling...")
        judge_results = llm_judge_sample(metrics["topics_data"], sample_per_topic)
        for topic, judgement in judge_results.items():
            per_topic.setdefault(topic, {}).update(judgement)

    today = datetime.now().strftime("%Y-%m-%d")
    eval_obj = Evaluation(
        date=today,
        filter_version=radar.FILTER_VERSION,
        total_articles=metrics["total_articles"],
        classified=metrics["classified"],
        unclassified=metrics["unclassified"],
        multi_match=metrics["multi_match"],
        per_topic=per_topic,
    )

    EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = EVALUATIONS_DIR / f"{today}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(eval_obj.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"Evaluation saved: {out_file}")
    print(f"  Total: {eval_obj.total_articles}")
    print(f"  Classified: {eval_obj.classified} ({(1-eval_obj.unclassified_rate)*100:.1f}%)")
    print(f"  Unclassified: {eval_obj.unclassified} ({eval_obj.unclassified_rate*100:.1f}%)")
    print(f"  Multi-match (≥4 topics): {eval_obj.multi_match}")

    append_audit(
        "evaluation",
        filter_version=eval_obj.filter_version,
        total=eval_obj.total_articles,
        unclassified_rate=eval_obj.unclassified_rate,
        multi_match_rate=eval_obj.multi_match_rate,
    )

    return eval_obj


def status() -> dict:
    """Print and return current state: filter version, pending proposals, recent metrics."""
    from agent.apply import list_pending

    info = {
        "filter_version": radar.FILTER_VERSION,
        "topics": radar.ALL_TOPICS,
        "pending_proposals": [p.name for p in list_pending()],
    }

    # Recent evaluations
    if EVALUATIONS_DIR.exists():
        recent = sorted(EVALUATIONS_DIR.glob("*.json"))[-7:]
        rates = []
        for f in recent:
            try:
                with open(f, encoding="utf-8") as fp:
                    e = json.load(fp)
                rates.append({
                    "date": e.get("date"),
                    "version": e.get("filter_version"),
                    "unclassified_rate": e.get("unclassified_rate"),
                })
            except (json.JSONDecodeError, OSError):
                continue
        info["recent_evaluations"] = rates

    print(f"Filter version: v{info['filter_version']}")
    print(f"Topics: {len(info['topics'])}")
    print(f"Pending proposals: {len(info['pending_proposals'])}")
    if info.get("recent_evaluations"):
        print("\nRecent evaluations:")
        for e in info["recent_evaluations"]:
            print(f"  {e['date']} v{e['version']}: "
                  f"{e['unclassified_rate']*100:.1f}% unclassified")
    return info

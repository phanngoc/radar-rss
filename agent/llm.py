"""Claude API client for filter review and evaluation."""

import json
import os
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None


SYSTEM_PROMPT = """You are a news classification expert for a bilingual (Vietnamese/English) RSS aggregator.

Your job is to review article classification results and propose targeted improvements to keyword/regex filters.

Domain knowledge:
- Articles come from Vietnamese news sites (VnExpress, Tuổi Trẻ, Thanh Niên, Dân Trí, Genk, Tinhte) and English sources (BBC, TechCrunch, The Verge, Ars Technica, Wired, MIT Tech Review, Hacker News, The Register, ZDNet, Engadget).
- Filtering uses two mechanisms: simple substring keywords AND regex patterns (with word boundaries).
- Vietnamese keywords MUST include diacritics (e.g., "kinh tế" not "kinh te").
- Short words (≤3 chars) like "us", "ai", "fed" MUST use regex with word boundaries.

Rules for proposals:
1. Maximum 5 changes per review.
2. Each change must include reasoning AND evidence (specific article titles).
3. Prefer specific multi-word keywords over single short words.
4. For removals, document the false-positive pattern observed.
5. Vietnamese keywords always with diacritics.
6. Never propose removing more than 2 keywords from one topic (preserve coverage).
7. Each topic must retain at least 3 keywords after changes.
"""


PROPOSE_CHANGES_TOOL = {
    "name": "propose_filter_changes",
    "description": "Propose targeted improvements to topic filters based on review of articles.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-sentence summary of the proposed changes and their goal.",
            },
            "changes": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add_keyword", "remove_keyword", "add_regex", "remove_regex"],
                        },
                        "topic": {"type": "string"},
                        "value": {
                            "type": "string",
                            "description": "The keyword or regex pattern to add/remove.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this change improves classification.",
                        },
                        "evidence": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Article titles that justify this change.",
                        },
                    },
                    "required": ["action", "topic", "value", "reasoning", "evidence"],
                },
            },
        },
        "required": ["summary", "changes"],
    },
}


JUDGE_TOOL = {
    "name": "judge_classification",
    "description": "Judge whether an article is correctly classified under a topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["correct", "incorrect", "partial"],
            },
            "reasoning": {"type": "string"},
        },
        "required": ["verdict", "reasoning"],
    },
}


def _client():
    if anthropic is None:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def call_review(
    current_filters: dict,
    unclassified: list[dict],
    multi_match: list[dict],
    stats: dict,
    trend: dict | None = None,
    model: str = "claude-sonnet-4-5",
    max_tokens: int = 4096,
) -> dict:
    """Call Claude to review classification and propose filter changes.

    Returns a dict matching PROPOSE_CHANGES_TOOL.input_schema.
    """
    user_content = _build_review_prompt(current_filters, unclassified, multi_match, stats, trend)

    client = _client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        tools=[PROPOSE_CHANGES_TOOL],
        tool_choice={"type": "tool", "name": "propose_filter_changes"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "propose_filter_changes":
            return block.input

    return {"summary": "no proposals", "changes": []}


def call_judge(
    article: dict,
    topic: str,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 256,
) -> dict:
    """Call Claude to judge if an article belongs to a topic. Returns {verdict, reasoning}."""
    user_content = (
        f"Topic: {topic}\n\n"
        f"Article title: {article.get('title', '')}\n"
        f"Article description: {article.get('desc', '')}\n"
        f"Source: {article.get('source', '')}\n\n"
        f"Is this article correctly classified under topic '{topic}'? "
        f"Answer 'correct' if it clearly belongs, 'partial' if tangentially related, "
        f"'incorrect' if it does not belong."
    )

    client = _client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": user_content}],
        tools=[JUDGE_TOOL],
        tool_choice={"type": "tool", "name": "judge_classification"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "judge_classification":
            return block.input

    return {"verdict": "partial", "reasoning": "no response"}


def _build_review_prompt(
    current_filters: dict,
    unclassified: list[dict],
    multi_match: list[dict],
    stats: dict,
    trend: dict | None,
) -> str:
    parts = []

    parts.append("## Current Filters\n")
    parts.append("```json\n")
    parts.append(json.dumps(current_filters, ensure_ascii=False, indent=2))
    parts.append("\n```\n")

    parts.append("\n## Today's Statistics\n")
    parts.append(json.dumps(stats, ensure_ascii=False, indent=2))
    parts.append("\n")

    if trend:
        parts.append("\n## Trend (recent days)\n")
        parts.append(json.dumps(trend, ensure_ascii=False, indent=2))
        parts.append("\n")

    if unclassified:
        parts.append(f"\n## Unclassified Articles ({len(unclassified)} samples)\n")
        parts.append("These matched ZERO topics:\n\n")
        for art in unclassified:
            parts.append(f"- [{art.get('source', '?')}] {art.get('title', '')}\n")
            desc = (art.get("desc") or "").strip()[:200]
            if desc:
                parts.append(f"    {desc}\n")

    if multi_match:
        parts.append(f"\n## Suspicious Multi-Match Articles ({len(multi_match)} samples)\n")
        parts.append("These matched 4+ topics (potential false positives):\n\n")
        for entry in multi_match:
            art = entry["article"]
            topics = entry["topics"]
            parts.append(f"- [{art.get('source', '?')}] {art.get('title', '')}\n")
            parts.append(f"    matched topics: {', '.join(topics)}\n")

    parts.append(
        "\n## Task\n\n"
        "Analyze the unclassified and multi-match articles. Propose up to 5 targeted "
        "filter changes that would improve classification. Use the propose_filter_changes "
        "tool to return your structured response. Each change must include reasoning and "
        "evidence (specific article titles from above).\n"
    )

    return "".join(parts)

"""LLM-based content scoring using Anthropic Claude."""

import json
import logging
import os

import anthropic

from megaphone import db

log = logging.getLogger(__name__)

SCORING_PROMPT = """Rate this content item on a 0-10 scale across these dimensions:
- relevance: How relevant is it to the following topics? {topics}
- novelty: Is this genuinely new information or a rehash?
- engagement: How likely is this to spark discussion on social media?
- timeliness: Is this trending or time-sensitive?
- brand_alignment: Does this fit a tech leader's voice (AI, engineering, fintech)?

Content title: {title}
Content body (first 2000 chars): {body}

Return ONLY valid JSON in this exact format, no other text:
{{"relevance": 7.0, "novelty": 8.0, "engagement": 6.5, "timeliness": 7.0, "brand_alignment": 8.0, "overall": 7.3, "summary": "One sentence explaining why this score"}}
"""


def _get_client():
    """Get Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def score_item(item, config):
    """Score a single content item using LLM.

    Args:
        item: dict with 'title' and 'body'
        config: app config dict

    Returns:
        (overall_score: float, reasons: dict)
    """
    topics = ", ".join(config.get("scoring", {}).get("topics", []))
    body_text = (item.get("body") or "")[:2000]

    prompt = SCORING_PROMPT.format(
        topics=topics,
        title=item.get("title", ""),
        body=body_text,
    )

    client = _get_client()
    model = config.get("llm", {}).get("scoring_model", "claude-haiku-4")

    response = client.messages.create(
        model=model,
        max_tokens=300,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Try to parse JSON from the response
    try:
        # Handle markdown code blocks
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        scores = json.loads(raw)
    except (json.JSONDecodeError, IndexError) as e:
        log.error("Failed to parse LLM scoring response: %s\nRaw: %s", e, raw)
        raise ValueError(f"LLM returned unparseable response: {raw[:200]}")

    overall = scores.get("overall", 0.0)
    return float(overall), scores


def score_pending(conn, config):
    """Score all items with status='raw'. Returns count scored."""
    items = db.get_content_items(conn, status="raw")
    threshold = config.get("scoring", {}).get("threshold", 6.0)
    scored = 0

    for item in items:
        try:
            overall, reasons = score_item(item, config)
            new_status = "candidate" if overall >= threshold else "archived"
            db.update_content_item_score(conn, item["id"], overall, reasons, new_status)
            log.info(
                "Scored [%d] %s: %.1f -> %s",
                item["id"], (item["title"] or "")[:60], overall, new_status
            )
            scored += 1
        except Exception as e:
            log.error("Failed to score item %d: %s", item["id"], e)
            # Leave as 'raw' for retry

    return scored

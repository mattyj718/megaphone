"""LLM-powered post drafting using Anthropic Claude."""

import json
import logging
import os

import anthropic

from megaphone import db

log = logging.getLogger(__name__)

LINKEDIN_PROMPT = """You are a social media ghostwriter for a tech leader. Write a LinkedIn post based on the source content below.

VOICE PROFILE:
{voice_profile}

SOURCE CONTENT:
Title: {title}
Body: {body}

INSTRUCTIONS:
- Write a compelling LinkedIn post (150-300 words)
- Start with a strong hook that grabs attention
- Include the main insight or takeaway
- End with a question or call-to-action to drive engagement
- Use the voice profile above to match tone and style
- No hashtags unless they feel natural
- No emojis unless the voice profile uses them
- Be opinionated and specific, not generic

Return ONLY the post text, nothing else."""

BLUESKY_PROMPT = """You are a social media ghostwriter for a tech leader. Write a Bluesky post based on the source content below.

VOICE PROFILE:
{voice_profile}

SOURCE CONTENT:
Title: {title}
Body: {body}

INSTRUCTIONS:
- Write a punchy Bluesky post (max 300 characters including spaces)
- Be concise, sharp, and opinionated
- Conversational tone — Bluesky is more casual than LinkedIn
- One core insight or hot take
- No hashtags
- Match the voice profile above

Return ONLY the post text, nothing else. It MUST be 300 characters or fewer."""


def _get_client():
    """Get Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def _format_voice_profile(config):
    """Format voice profile from config into a string for prompts."""
    voice = config.get("voice_profile", {})
    if not voice:
        return "Professional tech leader. Thoughtful, opinionated, concise."

    parts = []
    if voice.get("tone"):
        parts.append(f"Tone: {voice['tone']}")
    if voice.get("style"):
        parts.append(f"Style: {voice['style']}")
    if voice.get("topics"):
        parts.append(f"Core topics: {', '.join(voice['topics'])}")
    if voice.get("avoid"):
        parts.append(f"Avoid: {', '.join(voice['avoid'])}")
    if voice.get("examples"):
        parts.append("Example posts:")
        for ex in voice["examples"]:
            parts.append(f'  "{ex}"')

    return "\n".join(parts) if parts else "Professional tech leader. Thoughtful, opinionated, concise."


def draft_post(content_item_id, platform, conn, config):
    """Generate a draft post from a content item.

    Args:
        content_item_id: ID of the source content item
        platform: 'linkedin' or 'bluesky'
        conn: database connection
        config: app config dict

    Returns:
        post ID (int)
    """
    item = db.get_content_item(conn, content_item_id)
    if not item:
        raise ValueError(f"Content item {content_item_id} not found")

    voice_profile = _format_voice_profile(config)
    body_text = (item.get("body") or "")[:3000]

    if platform == "linkedin":
        prompt = LINKEDIN_PROMPT.format(
            voice_profile=voice_profile,
            title=item.get("title", ""),
            body=body_text,
        )
    elif platform == "bluesky":
        prompt = BLUESKY_PROMPT.format(
            voice_profile=voice_profile,
            title=item.get("title", ""),
            body=body_text,
        )
    else:
        raise ValueError(f"Unknown platform: {platform}")

    client = _get_client()
    model = config.get("llm", {}).get("drafting_model", "claude-opus-4-6")

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )

    draft_body = response.content[0].text.strip()

    # Enforce Bluesky character limit — truncate if LLM went over
    if platform == "bluesky" and len(draft_body) > 300:
        draft_body = draft_body[:297] + "..."

    post_id = db.insert_post(conn, content_item_id, platform, draft_body)

    # Update content item status to 'drafted' if it was a candidate
    if item["status"] == "candidate":
        db.update_content_item_status(conn, content_item_id, "drafted")

    log.info("Drafted %s post [%d] from content item [%d]", platform, post_id, content_item_id)
    return post_id


def draft_both(content_item_id, conn, config):
    """Draft posts for both LinkedIn and Bluesky. Returns dict of platform -> post_id."""
    results = {}
    for platform in ("linkedin", "bluesky"):
        post_id = draft_post(content_item_id, platform, conn, config)
        results[platform] = post_id
    return results

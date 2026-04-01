# backend/llm/panel_show.py

import json
import logging
from typing import Any, Optional

from config.settings import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_MODEL_OPENAI,
    LLM_MODEL_ANTHROPIC,
)

logger = logging.getLogger(__name__)

SEGMENT_TYPES = {
    "scenes",
    "if_this_is_the_answer",
    "truth_or_lie",
    "picture_of_week",
    "unlikely_things",
    "wildcard",
}
SPEED_VALUES = {"fast", "medium", "slow"}

PANEL_PROMPT = """You are a comedy writer's assistant for a fast-paced live SF panel show.

Show format: 6 game segments. Answers are quick — usually one line, sometimes 1-2 sentences max.
Minimal setup. Optimize for pacing and fast laughs. This is NOT a discussion show.

Segment types and pace guidance:
- scenes: "Scenes We'd Like to See" — short hypothetical prompt based on a local news item. Fast (2–3 possible per segment). Example: story about wolf on Alcatraz → prompt "Things the wolf says arriving at Alcatraz"
- if_this_is_the_answer: Based on a number / price / stat / concrete outcome in a story. Requires: answer, prompt, reveal. Medium (1 per segment). Example: answer "$18", prompt "What are you paying for in San Francisco?", reveal "A Mission cafe charged $18 for toast"
- truth_or_lie: Strange but plausible local story. Output a short statement that could be real. Slow (usually 1 story only).
- picture_of_week: Visual or highly imageable story. Short reaction prompt. Medium (1–2 per segment). If image_url exists in source, preserve it.
- unlikely_things: "Unlikely things to hear on a [X]" style. Fast (2–3 per segment). Best for transit, tech companies, city institutions, public figures.
- wildcard: Flexible slot — bad startup pitch, absurd city policy response, quick absurd prompt. Usually 1 per segment.

Story selection rules:
- Prefer: weird, local, specific, visual, price/stat-based, public-behavior absurdity
- Avoid: national with weak SF tie, too explanatory, duplicates in angle
- SAFETY HARD RULE: Exclude any story involving deaths, severe violence, ongoing tragedies, or sensitive personal harm — mark these as unused

Produce multiple candidates per segment type where the material supports it.
Do NOT force exactly one candidate per type. Producers will choose the final show lineup.

Input stories:
{stories_json}

Return ONLY valid JSON with no markdown and no explanation:
{{
  "segments": [
    {{
      "type": "<one of: scenes|if_this_is_the_answer|truth_or_lie|picture_of_week|unlikely_things|wildcard>",
      "story_id": "<id from input>",
      "headline": "<original headline>",
      "prompt": "<short show-ready prompt — keep it tight>",
      "why_it_fits": "<one sentence>",
      "speed": "<fast|medium|slow>",
      "fit_score": <integer 1–10>,
      "comedy_reason": "<one short phrase>",
      "host_setup": "<one sentence the host says to introduce the prompt>"
    }}
  ],
  "unused_stories": [
    {{
      "story_id": "<id>",
      "headline": "<headline>",
      "reason": "<why skipped: e.g. too explanatory / weak local tie / safety exclusion>"
    }}
  ]
}}

For if_this_is_the_answer segments also include:
  "answer": "<the stat/price/number>",
  "reveal": "<one sentence reveal>"

For picture_of_week segments, include "image_url" if the source story has one."""


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _call_openai(prompt: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL_OPENAI,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return json.loads(response.choices[0].message.content.strip())


def _call_anthropic(prompt: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=LLM_MODEL_ANTHROPIC,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = _strip_fences(message.content[0].text.strip())
    return json.loads(raw)


def _validate_segment(seg: Any) -> Optional[dict]:
    """Return a cleaned segment dict, or None if it fails validation."""
    if not isinstance(seg, dict):
        return None
    if seg.get("type") not in SEGMENT_TYPES:
        return None
    required = {"type", "story_id", "headline", "prompt", "why_it_fits", "speed"}
    if not required.issubset(seg.keys()):
        return None
    if seg["type"] == "if_this_is_the_answer" and not (seg.get("answer") and seg.get("reveal")):
        return None
    if seg.get("speed") not in SPEED_VALUES:
        seg["speed"] = "medium"
    if "fit_score" in seg:
        try:
            seg["fit_score"] = max(1, min(10, int(seg["fit_score"])))
        except (TypeError, ValueError):
            seg.pop("fit_score")
    return seg


def generate_panel_show(stories: list[dict]) -> dict:
    """
    Given a list of normalized story dicts, calls the LLM and returns:
      {
        "segments": { "<type>": [<candidate>, ...], ... },
        "unused_stories": [...]
      }

    Segments are grouped by type so producers can choose the final lineup.
    Raises ValueError or json.JSONDecodeError on parse/validation failure.
    """
    stories_json = json.dumps(stories, ensure_ascii=False)
    prompt = PANEL_PROMPT.format(stories_json=stories_json)

    if LLM_PROVIDER == "anthropic":
        raw_result = _call_anthropic(prompt)
    else:
        raw_result = _call_openai(prompt)

    raw_segments = raw_result.get("segments", [])
    raw_unused = raw_result.get("unused_stories", [])

    valid_segments = []
    invalid_count = 0
    for seg in raw_segments:
        cleaned = _validate_segment(seg)
        if cleaned is not None:
            valid_segments.append(cleaned)
        else:
            invalid_count += 1

    if invalid_count:
        logger.warning("panel_show: %d segment(s) failed validation and were dropped", invalid_count)

    # Lenient check: keep unused entries that at least have a story_id
    valid_unused = [u for u in raw_unused if isinstance(u, dict) and u.get("story_id")]

    # Group by type for producer control over final selection
    grouped: dict[str, list] = {}
    for seg in valid_segments:
        grouped.setdefault(seg["type"], []).append(seg)

    return {"segments": grouped, "unused_stories": valid_unused}

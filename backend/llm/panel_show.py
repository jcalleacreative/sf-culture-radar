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
WILDCARD_MODES = {
    "bad_startup_pitch",
    "absurd_policy_response",
    "hot_take_poll",
    "absurd_impersonation",
}
DISPLAY_LABELS = {
    "scenes": "Scenes We'd Like to See",
    "if_this_is_the_answer": "If This Is The Answer",
    "truth_or_lie": "Truth or Lie",
    "picture_of_week": "Picture of the Week",
    "unlikely_things": "Unlikely Things",
    "wildcard": "Wildcard",
}
REQUIRED_STORY_FIELDS = {"id", "headline", "source", "url"}

PANEL_PROMPT = """You are a comedy writer's assistant preparing segment candidates for a fast-paced live SF panel show.

SHOW RULES: host presents a prompt, panelists respond in one quick line. No setup speeches. No discussion. Every prompt must be answerable with a single funny sentence.

SEGMENT MECHANICS — assign each story to its best-fit type:

1. SCENES WE'D LIKE TO SEE  (type: "scenes")
   Mechanic: host reads "[prompt]", panelists each deliver one-line scene responses
   Good prompt: 4–10 words, a hypothetical situation with a clear subject
   Framing: start with "Things..." / "Lines from..." / "Reactions when..." / "Signs at..."
   Avoid: discussion questions, anything needing context to be funny, abstract concepts
   Speed: fast — 2–3 prompts fit in a 5-minute segment
   Example: story about wolf swimming to Alcatraz → "Things the wolf says arriving at Alcatraz"

2. IF THIS IS THE ANSWER  (type: "if_this_is_the_answer")
   Mechanic: host reads "[answer]" (a number/price/stat), panelists buzz in with a funny "What is [X]?" question
   Only use when the story contains a concrete measurable fact: price, count, distance, duration
   Required fields: answer (the literal number/price), prompt (vague question host reads aloud), reveal (actual story context, ≤15 words)
   Avoid: vague stats, opinions, ratios without scale
   Speed: medium — 1 per segment
   Example: answer="$18", prompt="What does it cost to feel judged in SF?", reveal="A Mission cafe charged $18 for avocado toast"

3. TRUTH OR LIE  (type: "truth_or_lie")
   Mechanic: host reads "[statement]", panelists vote true or false
   Required field: statement — one declarative sentence, ≤20 words, no compound clauses
   Good statement: locally plausible, genuinely surprising, guessable without insider knowledge
   Avoid: obviously fake claims, obviously true claims, run-on sentences with "and"
   Speed: slow — 1 story per segment
   Example: "A Tenderloin landlord is now required to provide free kombucha under a new city ordinance"

4. PICTURE OF THE WEEK  (type: "picture_of_week")
   Mechanic: host shows image on screen, panelists react or caption it
   ONLY assign this type when the source story has image_url set — never invent this field
   Required field: image_url copied from source story
   Good prompt: 4–8 words directing the reaction ("Caption this photo of X")
   Avoid: abstract stories, data stories, anything not photographable
   Speed: medium — 1–2 per segment

5. UNLIKELY THINGS  (type: "unlikely_things")
   Mechanic: host reads "Unlikely things to hear [on/in/from/at] [target]", panelists give one-line responses
   Required field: target — specific SF/Bay Area institution, vehicle, company, or public figure
   Good targets: "a Waymo", "Caltrain", "a Google all-hands", "Gavin Newsom", "a Tenderloin Whole Foods"
   Avoid: generic categories ("a restaurant"), non-SF-specific targets, abstract concepts
   Speed: fast — 2–3 prompts fit in a 5-minute segment

6. WILDCARD  (type: "wildcard")
   Fast-play slot. Must use exactly one of these modes:
   - "bad_startup_pitch": "Pitch me [weird real thing] as a startup" — for absurd local products/services/behaviors
   - "absurd_policy_response": "The city's official response to [X]" — for bizarre SF government or policy stories
   - "hot_take_poll": "SF residents poll: [yes/no question]?" — for local behavior or trend stories
   - "absurd_impersonation": "Things [named public figure] would say about [local story]"
   Required field: wildcard_mode (must be exactly one of the four above)
   Prompt max: 12 words
   Speed: fast — 1 per segment

STORY SELECTION:
- Prefer: weird, locally specific, visual, price/stat-grounded, SF public-behavior absurdity
- Avoid: national with weak SF tie, stories needing explanation to land, duplicate angles
- SAFETY (hard rule): Exclude stories involving deaths, severe violence, ongoing tragedies, or sensitive personal harm → mark as unused with reason "safety exclusion"

Produce multiple candidates per segment type where the material supports it.
Do NOT force one candidate per type. Producers pick the final lineup.

Input stories:
{stories_json}

Return ONLY valid JSON — no markdown, no explanation:
{{
  "segments": [
    {{
      "type": "<scenes|if_this_is_the_answer|truth_or_lie|picture_of_week|unlikely_things|wildcard>",
      "story_id": "<id from input>",
      "prompt": "<show-ready prompt — keep it tight>",
      "host_intro": "<one sentence host says before presenting the prompt>",
      "panelist_task": "<one sentence describing what panelists do>",
      "speed": "<fast|medium|slow>",
      "fit_score": <integer 1-10>,
      "reason_short": "<8 words or fewer: why this story fits this slot>"
    }}
  ],
  "unused_stories": [
    {{
      "story_id": "<id>",
      "reason": "<8 words or fewer: why skipped>"
    }}
  ]
}}

Per-type extra fields (include directly in the segment object, not nested):
- if_this_is_the_answer: "answer" and "reveal"
- truth_or_lie: "statement"
- picture_of_week: "image_url" (copy from source story only if present)
- unlikely_things: "target"
- wildcard: "wildcard_mode"
"""


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_input_stories(stories: list) -> list[dict]:
    """
    Validate the raw input list. Returns a list of error dicts (empty = all valid).
    Each error has: index, optional id, detail.
    """
    errors = []
    for i, item in enumerate(stories):
        if not isinstance(item, dict):
            errors.append({"index": i, "detail": "not a JSON object"})
            continue
        missing = sorted(REQUIRED_STORY_FIELDS - item.keys())
        if missing:
            errors.append({"index": i, "id": item.get("id"), "detail": f"missing required fields: {missing}"})
    return errors


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that some models add around JSON."""
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _call_llm(prompt: str) -> dict:
    """Call the configured LLM provider and return parsed JSON dict."""
    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=LLM_MODEL_ANTHROPIC,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
    else:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=LLM_MODEL_OPENAI,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()

    raw = _strip_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("panel_show: unparseable LLM output: %s", raw[:500])
        raise


# ---------------------------------------------------------------------------
# Per-candidate validation and hydration
# ---------------------------------------------------------------------------

def _validate_candidate(
    seg: Any, story_index: dict[str, dict]
) -> tuple[Optional[dict], Optional[str]]:
    """
    Validate and clean one raw segment dict from the LLM.
    Returns (cleaned_dict, None) on success, (None, drop_reason) on failure.
    Hydrates headline (and image_url for picture_of_week) from the source story.
    """
    if not isinstance(seg, dict):
        return None, "not a dict"

    seg_type = seg.get("type")
    if seg_type not in SEGMENT_TYPES:
        return None, f"unknown type: {seg_type!r}"

    story_id = str(seg.get("story_id", ""))
    source_story = story_index.get(story_id)
    if source_story is None:
        return None, f"story_id {story_id!r} not in input"

    for field in ("prompt", "host_intro", "panelist_task", "speed"):
        if not seg.get(field):
            return None, f"missing required field: {field!r}"

    prompt_text = seg["prompt"].strip()
    if len(prompt_text) > 150:
        return None, f"prompt too long ({len(prompt_text)} chars, max 150)"

    if seg.get("speed") not in SPEED_VALUES:
        seg["speed"] = "medium"

    if "fit_score" in seg:
        try:
            seg["fit_score"] = max(1, min(10, int(seg["fit_score"])))
        except (TypeError, ValueError):
            seg["fit_score"] = 5

    # Per-type checks
    if seg_type == "if_this_is_the_answer":
        if not seg.get("answer") or not seg.get("reveal"):
            return None, "if_this_is_the_answer: missing answer or reveal"

    elif seg_type == "truth_or_lie":
        if not seg.get("statement"):
            return None, "truth_or_lie: missing statement"

    elif seg_type == "picture_of_week":
        image_url = source_story.get("image_url")
        if not image_url:
            return None, "picture_of_week: source story has no image_url"
        seg["image_url"] = image_url  # hydrate from source, don't trust model

    elif seg_type == "unlikely_things":
        if not seg.get("target"):
            return None, "unlikely_things: missing target"

    elif seg_type == "wildcard":
        if seg.get("wildcard_mode") not in WILDCARD_MODES:
            return None, f"wildcard: wildcard_mode {seg.get('wildcard_mode')!r} not in allowed set"

    # Hydrate fields the model shouldn't control
    seg["headline"] = source_story["headline"]
    seg["display_label"] = DISPLAY_LABELS[seg_type]
    seg["story_id"] = story_id
    seg["prompt"] = prompt_text

    return seg, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_panel_show(stories: list[dict]) -> dict:
    """
    Given a list of validated story dicts, calls the LLM and returns:
      {
        "segments": { "<type>": [<candidate>, ...], ... },
        "unused_stories": [...]
      }

    Segments are grouped by type so producers can choose the final lineup.
    Raises json.JSONDecodeError or KeyError on unrecoverable parse failure.
    """
    story_index: dict[str, dict] = {str(s["id"]): s for s in stories}

    # Only send the fields the model needs; keep the payload lean
    story_fields = ("id", "headline", "summary", "source", "url", "published_at", "image_url")
    stories_for_prompt = [
        {k: s[k] for k in story_fields if k in s}
        for s in stories
    ]
    prompt = PANEL_PROMPT.format(stories_json=json.dumps(stories_for_prompt, ensure_ascii=False))

    raw_result = _call_llm(prompt)

    raw_segments = raw_result.get("segments", [])
    raw_unused = raw_result.get("unused_stories", [])

    valid_segments = []
    for i, seg in enumerate(raw_segments):
        cleaned, reason = _validate_candidate(seg, story_index)
        if cleaned is not None:
            cleaned["candidate_id"] = f"{cleaned['type']}_{cleaned['story_id']}_{i}"
            valid_segments.append(cleaned)
        else:
            logger.warning("panel_show: dropped segment[%d]: %s", i, reason)

    valid_unused = [u for u in raw_unused if isinstance(u, dict) and u.get("story_id")]

    grouped: dict[str, list] = {}
    for seg in valid_segments:
        grouped.setdefault(seg["type"], []).append(seg)

    return {"segments": grouped, "unused_stories": valid_unused}

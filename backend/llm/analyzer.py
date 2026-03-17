# backend/llm/analyzer.py

import json

from config.settings import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_MODEL_OPENAI,
    LLM_MODEL_ANTHROPIC,
)

VALID_SIGNALS = {
    "rare_event", "internet_discourse", "tech_ai", "algorithm_logic", "local_absurdity",
}

PROMPT_TEMPLATE = """You are a premise filter for a sketch comedy show targeting 25-40 year olds in San Francisco.

Headline: {title}

Your job is NOT to rank all news. Your job is to find things that could turn into a bit.

Ask yourself: "Would a 25-40 year old send this to a friend because it is weird, surprising, or funny?"

A PLAYABLE story is:
- unusual, surprising, or confusing
- easy to visualize or imagine on stage
- something people would react to or share online
- feels like it could turn into a bit

NOT PLAYABLE (score 0-3, playable=false):
- government committee decisions
- regulatory updates or policy restructuring
- bureaucratic process or administrative efficiency
- abstract governance topics
If the story is primarily about any of the above AND there is no rare or unusual event → playable=false and score must be 0-3.

Apply these signals if present:
- rare_event: an unusual real-world event that is surprising or uncommon (e.g. a wolf swims to Alcatraz)
- internet_discourse: likely to go viral or spark online debate or sharing
- tech_ai: involves AI, tech companies, or technology culture
- algorithm_logic: algorithmic or data-driven thinking applied to human life
- local_absurdity: strange cultural behaviors specific to a city or neighborhood

Examples:
- "Wolf swims to Alcatraz and officials refuse to intervene" → playable=true, score=9, signals=["rare_event","internet_discourse","local_absurdity"]
- "Months and millions later, SF may make few changes to city commissions" → playable=false, score=2, signals=[]

Return ONLY a JSON object with exactly these fields, no markdown, no explanation:
{{
  "playable": <true or false>,
  "llm_score": <integer 0-10>,
  "signals": [<zero or more signal strings from the list above>],
  "category": "<short label>",
  "explanation": "<one sentence explaining why this story is or is not a playable premise>"
}}"""


def _call_openai(title: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = PROMPT_TEMPLATE.format(title=title)

    response = client.chat.completions.create(
        model=LLM_MODEL_OPENAI,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()
    return json.loads(raw)


def _call_anthropic(title: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = PROMPT_TEMPLATE.format(title=title)

    message = client.messages.create(
        model=LLM_MODEL_ANTHROPIC,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def analyze(title: str) -> tuple[bool, float, list[str], str, str]:
    """
    Returns (playable, llm_score, signals, category, explanation).
    Raises on API error or JSON parse failure — let the caller handle it.
    """
    if LLM_PROVIDER == "anthropic":
        result = _call_anthropic(title)
    else:
        result = _call_openai(title)

    playable = bool(result.get("playable", False))
    score = float(result["llm_score"])
    signals = [s for s in result.get("signals", []) if s in VALID_SIGNALS]
    category = str(result["category"])
    explanation = str(result["explanation"])

    # Enforce hard rule: no rare event + bureaucratic content → not playable, score <= 3
    if not playable and score > 3:
        score = 3.0

    return playable, score, signals, category, explanation

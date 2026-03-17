# backend/llm/analyzer.py

import json

from config.settings import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_MODEL_OPENAI,
    LLM_MODEL_ANTHROPIC,
)

VALID_SIGNALS = {"tech_ai", "algorithm_logic", "internet_discourse", "rare_event", "local_absurdity"}

PROMPT_TEMPLATE = """You are evaluating news headlines for a 25-40 year old audience interested in unusual, surprising, or internet-worthy stories.

Headline: {title}

Score the headline 0-10 for how interesting, surprising, or discussable it is. High scores go to stories that are rare, visually strange, or would spread online. Low scores go to routine government policy, committee decisions, or regulatory updates.

Identify which of these signals apply (use as many as fit):
- rare_event: an unusual real-world event that is surprising or uncommon
- internet_discourse: likely to spark online discussion, debate, or go viral
- tech_ai: involves AI, tech companies, or technology culture
- algorithm_logic: algorithmic or data-driven thinking applied to human life
- local_absurdity: strange cultural behaviors specific to a city environment

Return ONLY a JSON object with exactly these fields, no markdown, no explanation:
{{
  "llm_score": <integer 0-10>,
  "signals": [<zero or more signal strings from the list above>],
  "category": "<short label>",
  "explanation": "<one sentence explaining why this story is unusual or interesting>"
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


def analyze(title: str) -> tuple[float, list[str], str, str]:
    """
    Returns (llm_score, signals, category, explanation).
    Raises on API error or JSON parse failure — let the caller handle it.
    """
    if LLM_PROVIDER == "anthropic":
        result = _call_anthropic(title)
    else:
        result = _call_openai(title)

    score = float(result["llm_score"])
    signals = [s for s in result.get("signals", []) if s in VALID_SIGNALS]
    category = str(result["category"])
    explanation = str(result["explanation"])
    return score, signals, category, explanation

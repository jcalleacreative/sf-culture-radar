# backend/llm/analyzer.py

import json

from config.settings import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_MODEL_OPENAI,
    LLM_MODEL_ANTHROPIC,
)

VALID_SIGNALS = {"tech_ai", "algorithm_logic", "reddit_discourse", "policy_contradiction", "local_absurdity"}

PROMPT_TEMPLATE = """You are evaluating San Francisco news headlines for comedy sketch potential.

Headline: {title}

Score the headline 0-10 for sketch comedy potential, then identify which of these signals apply:
- tech_ai: involves AI, tech companies, or Silicon Valley culture
- algorithm_logic: algorithmic or data-driven thinking applied to human situations
- reddit_discourse: internet argument culture, viral outrage, or Reddit-style debate
- policy_contradiction: a rule or policy produces an obviously absurd or opposite outcome
- local_absurdity: unusual San Francisco cultural norms or only-in-SF situations

Return ONLY a JSON object with exactly these fields, no markdown, no explanation:
{{
  "llm_score": <integer 0-10>,
  "signals": [<zero or more signal strings from the list above>],
  "category": "<short label>",
  "explanation": "<one sentence describing the contradiction or absurdity>"
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

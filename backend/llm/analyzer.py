# backend/llm/analyzer.py

import json

from config.settings import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    LLM_MODEL_OPENAI,
    LLM_MODEL_ANTHROPIC,
)

PROMPT_TEMPLATE = """You are evaluating San Francisco news headlines for comedy sketch potential.

Headline: {title}

Look for contradictions or absurdity involving:
- dog culture
- environmental ideology vs. behavior
- tech culture and entitlement
- bureaucratic dysfunction
- tourism vs. local norms

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "score": <integer 0-10>,
  "category": "<short label>",
  "explanation": "<one sentence>"
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
    return json.loads(raw)


def analyze(title: str) -> tuple[float, str, str]:
    """
    Returns (score, category, explanation).
    Raises on API error or JSON parse failure — let the caller handle it.
    """
    if LLM_PROVIDER == "anthropic":
        result = _call_anthropic(title)
    else:
        result = _call_openai(title)

    score = float(result["score"])
    category = str(result["category"])
    explanation = str(result["explanation"])
    return score, category, explanation

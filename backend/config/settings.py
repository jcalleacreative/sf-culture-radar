# backend/config/settings.py

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "sf_radar.db")

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "sf-sketch-radar/1.0")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # "openai" or "anthropic"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

LLM_MODEL_OPENAI = os.getenv("LLM_MODEL_OPENAI", "gpt-4o-mini")
LLM_MODEL_ANTHROPIC = os.getenv("LLM_MODEL_ANTHROPIC", "claude-haiku-4-5-20251001")

REDDIT_POST_LIMIT = int(os.getenv("REDDIT_POST_LIMIT", "25"))

API_KEY = os.getenv("API_KEY", "")

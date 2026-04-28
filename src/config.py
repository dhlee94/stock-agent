import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env file from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# LLM Configuration
# Main reasoning LLM (Planner / Executor / Reflector / Summarizer)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
# Embeddings for episodic/semantic memory (Anthropic has no embedding API,
# so this is restricted to providers that do).
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "gemini").lower()
# Keyword extraction in DriverMemory (defaults to the main LLM provider).
KEYWORD_LLM_PROVIDER = os.environ.get("KEYWORD_LLM_PROVIDER", LLM_PROVIDER).lower()

# Per-provider default model names per role. Override with LLM_MODEL /
# KEYWORD_LLM_MODEL / EMBEDDING_MODEL env vars when you want a different
# model on the same provider (e.g. Anthropic Haiku vs. Sonnet).
DEFAULT_MAIN_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-sonnet-4-6",
}
DEFAULT_KEYWORD_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-haiku-4-5-20251001",
}
DEFAULT_EMBEDDING_MODELS = {
    "gemini": "models/text-embedding-004",
    "openai": "text-embedding-3-small",
}

LLM_MODEL = os.environ.get("LLM_MODEL") or DEFAULT_MAIN_MODELS.get(LLM_PROVIDER, "")
KEYWORD_LLM_MODEL = os.environ.get("KEYWORD_LLM_MODEL") or DEFAULT_KEYWORD_MODELS.get(KEYWORD_LLM_PROVIDER, "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODELS.get(EMBEDDING_PROVIDER, "")

# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# App Settings
DEFAULT_MARKET = os.environ.get("DEFAULT_MARKET", "KR")
RISK_TOLERANCE = os.environ.get("RISK_TOLERANCE", "Medium")

# Paths
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = SRC_DIR / "prompts"

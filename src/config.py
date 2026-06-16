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

# Per-provider default model names per role.
DEFAULT_MAIN_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-sonnet-4-6",
}
DEFAULT_KEYWORD_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-haiku-4-5-20251001",
}
DEFAULT_EMBEDDING_MODELS = {
    "gemini": "models/gemini-embedding-001",
    "openai": "text-embedding-3-small",
}

LLM_MODEL = os.environ.get("LLM_MODEL") or DEFAULT_MAIN_MODELS.get(LLM_PROVIDER, "")
KEYWORD_LLM_MODEL = os.environ.get("KEYWORD_LLM_MODEL") or DEFAULT_KEYWORD_MODELS.get(KEYWORD_LLM_PROVIDER, "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODELS.get(EMBEDDING_PROVIDER, "")

# Per-agent model overrides (fall back to LLM_MODEL if unset)
PLANNER_MODEL             = os.environ.get("PLANNER_MODEL")             or LLM_MODEL
EXECUTOR_MODEL            = os.environ.get("EXECUTOR_MODEL")            or LLM_MODEL
SUMMARIZER_MODEL          = os.environ.get("SUMMARIZER_MODEL")          or LLM_MODEL
NEWS_ANALYST_MODEL        = os.environ.get("NEWS_ANALYST_MODEL")        or LLM_MODEL
TECHNICAL_ANALYST_MODEL   = os.environ.get("TECHNICAL_ANALYST_MODEL")   or LLM_MODEL
GLOBAL_PLANNER_MODEL      = os.environ.get("GLOBAL_PLANNER_MODEL")      or LLM_MODEL
LOCAL_REFLECTOR_MODEL     = os.environ.get("LOCAL_REFLECTOR_MODEL")     or KEYWORD_LLM_MODEL
GLOBAL_REFLECTOR_MODEL    = os.environ.get("GLOBAL_REFLECTOR_MODEL")    or LLM_MODEL
JUDGE_MODEL               = os.environ.get("JUDGE_MODEL")               or LLM_MODEL
MEMORY_COMPRESSOR_MODEL   = os.environ.get("MEMORY_COMPRESSOR_MODEL")   or KEYWORD_LLM_MODEL

# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# News source — Naver Open API
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

# KRX credentials
KRX_ID = os.environ.get("KRX_ID", "")
KRX_PW = os.environ.get("KRX_PW", "")

# Torch compute device for the local embedding fallback (memory_store)
TORCH_DEVICE = os.environ.get("TORCH_DEVICE", "auto")

# Agent iteration limits
MAX_GLOBAL_ITER = int(os.environ.get("MAX_GLOBAL_ITER", "3"))

# Wall-clock budget (seconds) for the analysis flow. Must stay under the
# web layer's hard request timeout (web/app.py = 600s) with margin for the
# final summarizer. When the budget is exceeded, the flow stops launching
# new refinement rounds / the integration step and returns a partial report
# instead of letting the request hard-time-out with no result.
FLOW_TIME_BUDGET_SEC = int(os.environ.get("FLOW_TIME_BUDGET_SEC", "480"))

# App Settings
DEFAULT_MARKET = os.environ.get("DEFAULT_MARKET", "KR")
RISK_TOLERANCE = os.environ.get("RISK_TOLERANCE", "Medium")

# Paths
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = SRC_DIR / "prompts"

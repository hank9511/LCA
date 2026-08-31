"""Configuration settings for the LCA analysis system"""

import os
import warnings

try:
    from dotenv import load_dotenv
    import pathlib

    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    try:
        import pathlib

        env_path = pathlib.Path(__file__).parent.parent / ".env"
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
    except Exception:
        pass

DATABASE_PATH = "ecoinvent 3.12 Cutoff Unit 2025-12-19"
PREFERRED_LCIA_METHOD = "EF v3.1"

UNCERTAINTY_ANALYSIS_ENABLED = False
MONTE_CARLO_ITERATIONS = 1000
DISPLAY_UNCERTAINTY_DETAILS = False
UNCERTAINTY_DISTRIBUTION_TYPE = "LOG_NORMAL"
APPLY_CUSTOM_UNCERTAINTY_TO_EXCHANGES = False
MONTE_CARLO_SELECTED_CATEGORIES = [
    "Climate change",
]
MC_SAFE_LINK_SANITIZE = True

USE_LLM_FOR_PROVIDER_SELECTION = False
LLM_PROVIDER_SELECTION_MIN_CANDIDATES = 5
LLM_PROVIDER_SELECTION_MAX_CANDIDATES = 10

PROVIDER_SELECTION_MODE = "semantic_only"
CANDIDATE_CONSTRAINT_MODE = "constrained"
ENABLE_LIFECYCLE_STAGE_CLASSIFICATION = True

MAX_PROVIDERS_TO_CHECK_OUTPUT = 40
PROVIDER_CHECK_BATCH_SIZE = 20
ENABLE_FAST_PREFILTER = True
PROVIDER_PRE_FILTER_LIMIT = 40
ENABLE_PROVIDER_OUTPUT_CHECK = True

UPSTREAM_TRACING_MAX_DEPTH = 0
PREFER_EXCEL_PROVIDERS = True
ENABLE_UNLIMITED_EXCEL_LINKING = True
DISABLE_BACKGROUND_UPSTREAM_TRACING = True

CUTOFF_THRESHOLD = 0.0001
DISABLE_UPSTREAM_EXPANSION_FOR_DEBUG = False
ENABLE_DETAILED_LCIA_CHECKS = False

PREFER_MARKET_PROCESSES = True
MARKET_PROCESSES_AS_CUTOFF = True
MARKET_PROCESS_PATTERN = r"(?i)^market\s+(group\s+)?for\s+"
MARKET_ACTIVITY_BOOST = 3.0
GEOGRAPHIC_MATCH_BOOST = 2.0

ENABLE_WASTE_FLOW_LINKING = True
WASTE_FLOW_MAX_DEPTH = 1

ENABLE_CHINESE_FLOW_TRANSLATION = True
CHINESE_FLOW_SIMILARITY_THRESHOLD = 0.6
CHINESE_FLOW_LLM_EVALUATION = True

DIAGNOSTIC_SHOW_SCALING_FACTORS = False
VERBOSE_OUTPUT = False
DEFAULT_ALLOCATION_METHOD = "NONE"
SKIP_DUMMY_PROVIDERS = True
DUMMY_PROCESS_NAME_PATTERN = r"(?i)^dummy[\s_-]"

LLM_PROXY = os.getenv("LLM_PROXY", "").strip()

LLM_CONFIGS = {
    "grok": {
        "model": os.getenv("GROK_MODEL", "x-ai/grok-4.3"),
        "api_key": os.getenv("GROK_API_KEY"),
        "base_url": os.getenv("GROK_BASE_URL", "https://openrouter.ai/api/v1"),
    },
    "deepseek": {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash"),
        "api_key": os.getenv("GROK_API_KEY"),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://openrouter.ai/api/v1"),
    },
    "gpt": {
        "model": os.getenv("GPT_MODEL", "openai/gpt-5.4"),
        "api_key": os.getenv("GROK_API_KEY"),
        "base_url": os.getenv("GPT_BASE_URL", "https://openrouter.ai/api/v1"),
    },
    "qwen": {
        "model": os.getenv("QWEN_MODEL", "qwen/qwen3.6-35b-a3b"),
        "api_key": os.getenv("GROK_API_KEY"),
        "base_url": os.getenv("QWEN_BASE_URL", "https://openrouter.ai/api/v1"),
    },
    "gemini": {
        "model": os.getenv("GEMINI_MODEL", "google/gemini-3-flash-preview"),
        "api_key": os.getenv("GROK_API_KEY"),
        "base_url": os.getenv("GEMINI_BASE_URL", "https://openrouter.ai/api/v1"),
    },
}

LLM_PREFERRED_ORDER = ("qwen",)

if not LLM_CONFIGS["deepseek"]["api_key"] and USE_LLM_FOR_PROVIDER_SELECTION:
    warnings.warn(
        "GROK_API_KEY is not set; LLM-based helpers will be disabled.",
        RuntimeWarning,
    )

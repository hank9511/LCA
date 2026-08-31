"""LLM utility functions for the LCA analysis system"""

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Any
from openai import OpenAI
import httpx
import olca_schema as o
import olca_ipc as ipc
import re
from .config import LLM_CONFIGS, LLM_PROXY

_PERMANENT_FAILURE_KEYWORDS = (
    "deprecated",
    "model not found",
    "no such model",
    "404",
    "401",
    "403",
    "model_not_found",
)


def is_permanent_llm_failure(error: BaseException) -> bool:

    if error is None:
        return False
    msg = str(error).lower()
    return any(kw in msg for kw in _PERMANENT_FAILURE_KEYWORDS)


def pick_available_llm(
    llm_clients: Dict[str, Any],
    preferred: Optional[Sequence[str]] = None,
    exclude: Optional[Iterable[str]] = None,
) -> Optional[str]:

    if not llm_clients:
        return None

    if preferred is None:

        try:
            from .config import LLM_PREFERRED_ORDER as _default

            preferred = _default
        except Exception:
            preferred = ("deepseek",)

    exclude_set: Set[str] = set(exclude or ())

    for name in preferred:
        if name in exclude_set:
            continue
        if name in llm_clients and llm_clients[name] is not None:
            return name

    return None


def get_configured_model_id(llm_provider_key: str) -> str:
    """Resolve the API model id used in ``chat.completions.create`` for a client key."""
    cfg = LLM_CONFIGS.get(llm_provider_key)
    if cfg and cfg.get("model"):
        return str(cfg["model"])
    return llm_provider_key


def _normalize_proxy(url: Optional[str]) -> Optional[str]:

    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    low = u.lower()
    if low.startswith("socks4"):
        rest = u.split("://", 1)[1] if "://" in u else u
        new = "socks5h://" + rest
        print(f"⚠️ 检测到 socks4 代理（httpx 不支持），已自动改用 {new}")
        return new
    return u


def build_llm_http_client() -> httpx.Client:

    proxy = _normalize_proxy(LLM_PROXY)

    if proxy and proxy.lower().startswith("socks"):
        try:
            import socksio
        except ImportError:
            print(
                '⚠️ 使用 socks 代理需要先安装依赖： pip install "httpx[socks]"；'
                "当前未安装，已回退为直连。"
            )
            proxy = None

    timeout = httpx.Timeout(60.0, connect=30.0)
    try:
        if proxy:
            print(f"🌐 LLM 请求将通过代理：{proxy}")
            return httpx.Client(proxy=proxy, trust_env=False, timeout=timeout)
        return httpx.Client(trust_env=False, timeout=timeout)
    except Exception as e:
        print(f"⚠️ 创建带代理的 HTTP 客户端失败（{e}），改用直连客户端")
        return httpx.Client(trust_env=False, timeout=timeout)


def initialize_llm_clients() -> Dict[str, OpenAI]:
    """Initialize LLM clients"""
    llm_clients = {}

    if not LLM_CONFIGS:
        print("⚠️ LLM_CONFIGS is empty, no LLM clients to initialize")
        return llm_clients

    print(f"📋 找到 {len(LLM_CONFIGS)} 个LLM配置，开始初始化...")

    http_client = build_llm_http_client()

    for name, config in LLM_CONFIGS.items():
        try:
            print(f"  🔄 正在初始化 {name} LLM客户端...")

            if not config:
                print(f"⚠️ {name} LLM: 配置为空，跳过初始化")
                llm_clients[name] = None
                continue

            api_key = config.get("api_key")
            if not api_key:
                print(f"⚠️ {name} LLM: API key not set, skipping initialization")
                llm_clients[name] = None
                continue

            base_url = config.get("base_url", "https://api.openai.com/v1")
            print(f"  📡 使用base_url: {base_url}")

            llm_clients[name] = OpenAI(
                api_key=api_key, base_url=base_url, http_client=http_client
            )
            print(f"✅ 成功初始化 {name} LLM客户端")

        except Exception as e:
            import traceback

            error_msg = str(e)
            print(f"❌ 初始化 {name} LLM客户端失败: {error_msg}")
            print(f"   错误详情: {traceback.format_exc()}")
            llm_clients[name] = None

    working_count = sum(1 for client in llm_clients.values() if client is not None)
    total_count = len(llm_clients)
    print(f"📊 LLM初始化完成: {working_count}/{total_count} 个客户端可用")

    return llm_clients


def call_llm_api(
    llm_clients: Dict[str, OpenAI],
    llm_name: str,
    prompt: str,
    max_tokens: int = 1000,
    temperature: float = 0.1,
) -> str:
    """Call specified LLM API"""
    if llm_name not in llm_clients or llm_clients[llm_name] is None:
        raise ValueError(f"LLM client '{llm_name}' is not available")

    try:
        client = llm_clients[llm_name]
        model_name = LLM_CONFIGS[llm_name]["model"]

        token_budget = max_tokens
        max_retries = 2

        for attempt in range(max_retries + 1):
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=token_budget,
                temperature=temperature,
            )

            if not response or not getattr(response, "choices", None):
                raise ValueError(f"Empty response object from {llm_name} API")

            choice0 = response.choices[0]
            finish_reason = getattr(choice0, "finish_reason", None)
            message = getattr(choice0, "message", None)
            content = getattr(message, "content", None) if message is not None else None

            text = None
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):

                parts = []
                for part in content:
                    if isinstance(part, dict):
                        part_text = part.get("text")
                        if isinstance(part_text, str):
                            parts.append(part_text)
                    else:
                        part_text = getattr(part, "text", None)
                        if isinstance(part_text, str):
                            parts.append(part_text)
                text = "\n".join(p for p in parts if p)

            if (
                (text is None or not str(text).strip())
                and finish_reason == "length"
                and attempt < max_retries
            ):
                token_budget = min(token_budget * 2, 8000)
                print(
                    f"⚠️ {llm_name} returned empty content with finish_reason=length; "
                    f"retrying with max_tokens={token_budget} (attempt {attempt + 2}/{max_retries + 1})"
                )
                continue

            if text is None:
                raise ValueError(
                    f"{llm_name} returned empty message.content (finish_reason={finish_reason})"
                )

            stripped = text.strip()
            if not stripped:
                raise ValueError(
                    f"{llm_name} returned blank text after trim (finish_reason={finish_reason})"
                )

            return stripped

        raise ValueError(f"{llm_name} failed to produce non-empty text after retries")

    except Exception as e:
        raise ValueError(f"Failed to call {llm_name} API: {str(e)}")

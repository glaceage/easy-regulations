from openai import AsyncOpenAI

from apps.api.config import get_settings


def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.xiaomi_api_key or "not-set",
        base_url=settings.xiaomi_base_url,
        timeout=settings.llm_timeout_seconds,
    )

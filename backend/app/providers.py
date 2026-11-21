from .ai import DemoProvider, LiveProvider, LLMProvider
from .config import Settings
from .gemini import GeminiProvider


def live_provider(settings: Settings) -> LLMProvider:
    return (
        GeminiProvider(settings)
        if settings.ai_provider == "gemini"
        else LiveProvider(settings)
    )


def runtime_provider(settings: Settings) -> LLMProvider:
    return DemoProvider() if settings.ai_mode == "demo" else live_provider(settings)

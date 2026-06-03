# src/llm/llm_factory.py
import yaml
from pathlib import Path
from .base_client import BaseLLMClient

# Providers are imported lazily inside the function so that
# a missing optional package (google-genai, openai, etc.) does
# NOT crash the entire application on startup.

def create_llm_client(config_path: str = "config.yaml") -> BaseLLMClient:
    """설정 파일을 읽어 적절한 LLM 클라이언트 인스턴스를 반환합니다."""

    if not Path(config_path).exists():
        raise FileNotFoundError(f"❌ [Error] 설정 파일을 찾을 수 없습니다: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    provider    = config.get("llm", {}).get("provider", "gemini").lower()
    model_name  = config.get("llm", {}).get("model", "gemini-2.5-pro")
    temperature = config.get("llm", {}).get("temperature", 0.2)

    if provider == "gemini":
        from .gemini_client import GeminiClient          # lazy — needs google-genai
        return GeminiClient(model_name=model_name, temperature=temperature)

    elif provider == "claude":
        from .claude_client import ClaudeClient          # lazy — needs anthropic
        return ClaudeClient(model_name=model_name, temperature=temperature)

    elif provider == "gpt":
        raise NotImplementedError("GPT client is not implemented yet.")

    else:
        raise ValueError(f"❌ [Error] 지원하지 않는 LLM 제공자입니다: {provider}")
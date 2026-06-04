# src/llm/llm_factory.py
import yaml
from pathlib import Path
from .base_client import BaseLLMClient
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-pro",
    "gpt": "gpt-4o",
    "openai": "gpt-4o",
    "claude": "claude-3-5-sonnet-20241022",
    "anthropic": "claude-3-5-sonnet-20241022",
}

def create_llm_client(config_path: str = "config.yaml", provider_override: str = None, model_override: str = None) -> BaseLLMClient:
    """설정 파일 및 CLI 옵션을 읽어 적절한 LLM 클라이언트 인스턴스를 반환합니다."""
    
    # 기본값 설정
    provider = "gemini"
    model_name = DEFAULT_MODELS[provider]
    temperature = 0.2
    
    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            llm_config = config.get("llm", {})
            provider = llm_config.get("provider", provider).lower()
            model_name = llm_config.get("model", model_name)
            temperature = float(llm_config.get("temperature", temperature))
    else:
        print(f"⚠️ [Warning] 설정 파일을 찾을 수 없어 기본값을 사용합니다: {config_path}")
        
    # CLI 인자(override)가 존재하면 config.yaml 설정을 무시하고 덮어씌움
    if provider_override:
        provider = provider_override.lower()
        if not model_override:
            model_name = DEFAULT_MODELS.get(provider, model_name)
    if model_override:
        model_name = model_override
        
    if provider == "gemini":
        return GeminiClient(model_name=model_name, temperature=temperature)
    elif provider in ["gpt", "openai"]:
        return OpenAIClient(model_name=model_name, temperature=temperature)
    elif provider in ["claude", "anthropic"]:
        return AnthropicClient(model_name=model_name, temperature=temperature)
    else:
        raise ValueError(f"❌ [Error] 지원하지 않는 LLM 제공자입니다: {provider}")

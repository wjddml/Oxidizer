# src/llm/claude_client.py
import os
from typing import List, Dict
from .base_client import BaseLLMClient


class ClaudeClient(BaseLLMClient):
    """
    Anthropic Claude API 클라이언트.
    BaseLLMClient 인터페이스를 구현합니다.
    """

    def __init__(self, model_name: str = "claude-sonnet-4-20250514", temperature: float = 0.2):
        import anthropic  # lazy import — only fails if package missing

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Export it or pass it through the web UI."
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model_name
        self.temperature = temperature
        self.max_tokens = 4096

    def generate(self, messages: List[Dict[str, str]]) -> str:
        """
        Anthropic Messages API 호출 후 텍스트 반환.
        system 역할 메시지는 최상위 system 파라미터로 분리합니다.
        """
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_msgs = [m for m in messages if m["role"] != "system"]

        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=user_msgs,
        )
        if sys_msg:
            kwargs["system"] = sys_msg

        response = self.client.messages.create(**kwargs)
        return response.content[0].text.strip()

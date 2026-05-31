# src/llm/anthropic_client.py
import os
from dotenv import load_dotenv
from typing import List, Dict
from .base_client import BaseLLMClient

load_dotenv()

class AnthropicClient(BaseLLMClient):
    def __init__(self, model_name: str, temperature: float = 0.2):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("❌ [Error] ANTHROPIC_API_KEY가 없습니다. .env 파일에 등록해주세요.")
        
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("anthropic 패키지가 없습니다. 'pip install anthropic'을 실행하세요.")
            
        self.model_name = model_name
        self.temperature = temperature

    def generate(self, messages: List[Dict[str, str]]) -> str:
        print("🤖 [LLM] Anthropic(Claude)에게 변환/수정을 요청하는 중...")
        
        system_msg = ""
        user_msgs = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                user_msgs.append({"role": msg["role"], "content": msg["content"]})
        
        try:
            response = self.client.messages.create(
                model=self.model_name,
                system=system_msg,
                messages=user_msgs,
                max_tokens=4096,  # 코드를 온전히 출력하기 위해 넉넉한 토큰 확보
                temperature=self.temperature
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"❌ [Error] Anthropic API 호출 중 오류 발생: {e}")
            return ""
# src/llm/openai_client.py
import os
from dotenv import load_dotenv
from typing import List, Dict
from .base_client import BaseLLMClient
from utils.logger import logger  # 로거 임포트

load_dotenv()

class OpenAIClient(BaseLLMClient):
    def __init__(self, model_name: str, temperature: float = 0.2):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("❌ [Error] OPENAI_API_KEY가 없습니다. .env 파일에 등록해주세요.")
        
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai 패키지가 없습니다. 'pip install openai'를 실행하세요.")
            
        self.model_name = model_name
        self.temperature = temperature

    def generate(self, messages: List[Dict[str, str]]) -> str:
        # 터미널 깨짐 방지를 위해 info -> debug로 강등
        logger.debug("🤖 [LLM] OpenAI(GPT)에게 변환/수정을 요청하는 중...")
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"❌ [Error] OpenAI API 호출 중 오류 발생: {e}")
            return ""
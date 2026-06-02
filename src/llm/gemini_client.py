# src/llm/gemini_client.py
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import List, Dict
from .base_client import BaseLLMClient
from utils.logger import logger

load_dotenv()

class GeminiClient(BaseLLMClient):
    def __init__(self, model_name: str, temperature: float = 0.2):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ [Error] GEMINI_API_KEY가 없습니다. .env 파일에 등록해주세요.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature

    def generate(self, messages: List[Dict[str, str]]) -> str:
        # 터미널 깨짐 방지를 위해 info -> debug로 강등
        logger.debug("🤖 [LLM] Gemini API 호출 중...") 
        
        system_instruction = ""
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction += msg["content"] + "\n"
            else:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role, 
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )

        config_args = {"temperature": self.temperature}
        if system_instruction:
            config_args["system_instruction"] = system_instruction.strip()

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(**config_args)
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"❌ [Error] Gemini API 호출 중 오류 발생: {e}")
            return ""
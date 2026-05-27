# src/llm/gemini_client.py
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import List, Dict
from .base_client import BaseLLMClient

# 환경 변수 로드
load_dotenv()

class GeminiClient(BaseLLMClient):
    def __init__(self, model_name: str, temperature: float = 0.2):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ [Error] GEMINI_API_KEY가 없습니다.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature

    def generate(self, messages: List[Dict[str, str]]) -> str:
        print("🤖 [LLM] Gemini에게 변환/수정을 요청하는 중...")
        
        system_instruction = ""
        contents = []
        
        # 메시지 배열을 Gemini SDK 규격에 맞게 변환
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
            
            # 마스터의 마크다운 정제 로직 유지
            refined_code = response.text.strip()
            if refined_code.startswith("```rust"):
                refined_code = refined_code[7:]
            elif refined_code.startswith("```"):
                refined_code = refined_code[3:]
            if refined_code.endswith("```"):
                refined_code = refined_code[:-3]
                
            return refined_code.strip()
            
        except Exception as e:
            print(f"❌ [Error] Gemini API 호출 중 오류 발생: {e}")
            return ""
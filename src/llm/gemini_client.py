# src/llm_client.py
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ [Error] GEMINI_API_KEY가 없습니다.")

client = genai.Client(api_key=api_key)

def request_safe_rust(system_prompt: str, user_prompt: str) -> str:
    print("🤖 [Step 3] Gemini에게 관용적(Idiomatic) Safe Rust 변환을 요청하는 중...")
    try:
        # 💡 구글의 신규 계정 정책 우회 및 가장 똑똑한 1.5 Pro 모델 사용
        model_id = "gemini-2.5-pro" 
        
        response = client.models.generate_content(
            model=model_id,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
            ),
        )
        
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
        return None
# src/prompter/repair_builder.py
import yaml
from pathlib import Path
from typing import List, Dict

class RepairBuilder:
    """
    파싱된 컴파일 에러를 기반으로 LLM에게 전달할 '맞춤형 피드백 프롬프트'를 조립합니다.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        project_root = Path(__file__).resolve().parent.parent.parent
        prompts_dir_name = self.config.get("paths", {}).get("prompts_dir", "prompts")
        self.rules_dir = project_root / prompts_dir_name / "rules"
        
        self.category_guidelines = {
            "Borrow/Lifetime": "To fix Borrow/Lifetime errors, consider using `.clone()` to duplicate data, or rewrite the logic to use safe slicing (`&[T]`) instead of raw pointers. Do not use `unsafe` to bypass the borrow checker.",
            "Unsafe": "Unsafe blocks or operations were detected. You MUST remove all `unsafe` keywords. Replace raw pointer arithmetic with safe iterators or indexing. Replace C library calls with Rust standard library equivalents.",
            "Mutability": "To fix Mutability errors, check if you need to declare the variable as `mut`. If dealing with global mutable state, consider encapsulating it in a safe struct or passing it as a mutable reference parameter.",
            "Type Mismatch": "To fix Type Mismatch errors, ensure that you are strictly matching the expected Rust types. Use `.as_ref()`, `.as_mut()`, or explicit safe casting (`as usize`, etc.) where appropriate.",
            "Missing/Not Found": "To fix Missing/Not Found errors, ensure you have included all necessary standard library imports (e.g., `use std::ptr;`, `use std::slice;`). Do NOT import `libc`."
        }

    def _get_targeted_guidelines(self, parsed_errors: List[Dict[str, str]]) -> str:
        """현재 발생한 에러 카테고리에 맞는 가이드라인만 추출합니다."""
        active_categories = {err['category'] for err in parsed_errors}
        
        guidance_text = ""
        for idx, category in enumerate(active_categories, 1):
            if category in self.category_guidelines:
                guidance_text += f"{idx}. [{category}] {self.category_guidelines[category]}\n"
                
        if not guidance_text:
            guidance_text = "Analyze the provided compiler errors step-by-step and fix them strictly using Safe Rust."
            
        return guidance_text

    def build_repair_messages(
        self, 
        broken_rust_code: str, 
        formatted_errors: str, 
        parsed_errors: List[Dict[str, str]], 
        attempt: int
    ) -> List[Dict[str, str]]:
        """
        에러 피드백을 포함한 LLM 요청용 메시지 리스트를 반환합니다.
        """
        targeted_guidelines = self._get_targeted_guidelines(parsed_errors)
        
        system_instruction = (
            "You are an expert at repairing Rust code. Your task is to fix compilation errors "
            "in the provided Rust code. You MUST strictly follow these rules:\n"
            "- Produce the ENTIRE file when repairing it, not just the changed parts.\n"
            "- Do NOT change the function signatures or return types.\n"
            "- Each error MUST be solved using SAFE Rust code. Do NOT use `unsafe`.\n"
            "- Do NOT use Foreign Function Interface calls like `libc`.\n"
            "Think step-by-step about why the error occurred, then output the corrected code."
        )
        
        # 문자열 충돌(마크다운 렌더링 에러) 방지를 위해 괄호와 f-string 조합으로 안전하게 구성
        user_prompt = (
            f"### Current Rust Code (Attempt {attempt}):\n"
            "```rust\n"
            f"{broken_rust_code}\n"
            "```\n\n"
            f"{formatted_errors}\n\n"
            "### Guidelines to fix these specific errors:\n"
            f"{targeted_guidelines}\n\n"
            "Please provide the fully repaired Rust code enclosed in ```rust ``` tags."
        )
        
        return [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ]
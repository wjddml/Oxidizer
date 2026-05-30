# src/prompter/repair_builder.py
from typing import List, Dict, Any

class RepairBuilder:
    def __init__(self, config_path: str = "config.yaml"):
        pass

    def build_repair_messages(
        self, 
        rust_code: str, 
        formatted_errors: str, 
        parsed_errors: List[Dict[str, Any]], 
        attempt: int
    ) -> List[Dict[str, str]]:
        """
        컴파일 에러 수리를 위한 프롬프트를 구성합니다.
        LLM의 출력 안정성을 위해 '구조화된 마크다운(Structured Markdown)' 포맷을 강제합니다.
        """
        
        system_prompt = """You are an expert automated Rust code repair agent. 
Your sole task is to fix the given compilation errors and return the corrected code.

[CRITICAL OUTPUT FORMAT]
You MUST strictly follow this markdown structure. Do not deviate.

### 1. REPAIR PLAN
Write a brief analysis of the compiler error and your strategy to fix it.

### 2. FIXED RUST CODE
Provide the ENTIRE, completely fixed Rust source code inside a single ```rust ... ``` block.
Do not omit any part of the code. Do not output multiple code blocks.
"""

        user_prompt = (
            f"### Attempt: {attempt}/5\n\n"
            f"### Current Broken Rust Code:\n```rust\n{rust_code}\n```\n\n"
            f"### Compiler Error Messages:\n```\n{formatted_errors}\n```\n\n"
            "Please follow the exact markdown structure requested to fix the code."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
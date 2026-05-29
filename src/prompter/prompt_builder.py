# src/prompter/prompt_builder.py
import yaml
from pathlib import Path
from typing import List, Dict

class PromptBuilder:
    """
    시스템 템플릿(system_template.txt)을 로드하고,
    정적 분석 결과(static_context)와 RAG 검색 규칙(dynamic_rules)을 매핑하여
    최종 LLM 프롬프트를 조립합니다.
    """
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        project_root = Path(__file__).resolve().parent.parent.parent
        prompts_dir = project_root / self.config.get("paths", {}).get("prompts_dir", "prompts")
        
        # 마스터가 작성한 시스템 템플릿 로드
        template_path = prompts_dir / "templates" / "system_template.txt"
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                self.system_template = f.read()
        else:
            raise FileNotFoundError(f"시스템 템플릿을 찾을 수 없습니다: {template_path}")

    def build_master_prompt(
        self, 
        c_code: str, 
        c2rust_code: str, 
        c_fingerprint_str: str, 
        mir_liveness_str: str, 
        rag_rules_str: str
    ) -> List[Dict[str, str]]:
        """
        모든 분석 데이터를 템플릿에 주입하고, LLM용 메시지 배열을 생성합니다.
        """
        
        # 1. {static_context} 영역 조립 (C DFG 지문 + Rust MIR 생존 변수)
        static_context_parts = []
        if c_fingerprint_str:
            static_context_parts.append(c_fingerprint_str)
        if mir_liveness_str:
            static_context_parts.append(mir_liveness_str)
        
        static_context_combined = "\n\n".join(static_context_parts)
        if not static_context_combined:
            static_context_combined = "// No specific static analysis data triggered for this chunk."
            
        # 2. 시스템 프롬프트 포맷팅 (템플릿의 플레이스홀더 치환)
        system_content = self.system_template.format(
            static_context=static_context_combined,
            dynamic_rules=rag_rules_str
        )

        # 3. 유저 프롬프트 구성 (원본 C 및 C2Rust 참고 코드 제공)
        user_content = (
            "### Original C Code:\n"
            "```c\n"
            f"{c_code}\n"
            "```\n\n"
            "### C2Rust Unsafe Code (Reference):\n"
            "```rust\n"
            f"{c2rust_code}\n"
            "```\n\n"
            "Please execute your `// PLAN:` and generate the idiomatic Safe Rust translation following the tags (<FUNC>, <IMPORTS>) specified in the system instructions."
        )
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
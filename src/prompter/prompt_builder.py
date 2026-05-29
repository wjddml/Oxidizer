# src/prompter/prompt_builder.py
import yaml
from pathlib import Path
from typing import List, Dict

class PromptBuilder:
    """
    1. 5개의 인간 변환 규칙(YAML)을 로드하고 코드 내 트리거(Trigger)와 매칭합니다.
    2. 시스템 템플릿(system_template.txt)을 로드합니다.
    3. 정적 분석 지문, 매칭된 규칙, RAG 예시 코드를 융합하여 마스터 프롬프트를 조립합니다.
    """
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.prompts_dir = self.project_root / self.config.get("paths", {}).get("prompts_dir", "prompts")
        
        # 1. 마스터가 작성한 시스템 템플릿 로드
        template_path = self.prompts_dir / "templates" / "system_template.txt"
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                self.system_template = f.read()
        else:
            raise FileNotFoundError(f"시스템 템플릿을 찾을 수 없습니다: {template_path}")

        # 2. NDSS 5대 규칙(YAML) 사전 로드
        self.human_rules = self._load_human_rules()

    def _load_human_rules(self) -> List[Dict]:
        """prompts/rules 디렉토리 내의 모든 YAML 규칙을 메모리에 적재합니다."""
        rules = []
        rules_dir = self.prompts_dir / "rules"
        if rules_dir.exists():
            for yaml_file in rules_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if data and "rules" in data:
                            rules.extend(data["rules"])
                except Exception as e:
                    print(f"⚠️ [Warning] {yaml_file.name} 규칙 로드 실패: {e}")
        return rules

    def _match_rules(self, code: str) -> str:
        """C 코드 및 C2Rust 코드 텍스트 내에 규칙의 trigger 키워드가 있는지 검사합니다."""
        matched_rules = []
        for rule in self.human_rules:
            triggers = rule.get("trigger", [])
            # 트리거 중 하나라도 코드에 존재하면 해당 규칙을 발동
            if any(t in code for t in triggers):
                matched_rules.append(f"- **{rule.get('name', 'Rule')}**: {rule.get('description', '')}")
        
        if not matched_rules:
            return "Proceed with standard idiomatic Safe Rust practices."
        return "\n".join(matched_rules)

    def build_master_prompt(
        self, 
        c_code: str, 
        c2rust_code: str, 
        c_fingerprint_str: str, 
        rag_examples_str: str
    ) -> List[Dict[str, str]]:
        """
        모든 분석 데이터와 예시 코드를 템플릿에 주입하고, LLM용 메시지 배열을 생성합니다.
        (참고: mir_liveness_str 인자는 파이프라인에서 제거되었습니다.)
        """
        
        # 1. 5대 규칙 트리거 매칭 (C 원본과 C2Rust 코드를 모두 스캔)
        combined_code = f"{c_code}\n{c2rust_code}"
        dynamic_rules_str = self._match_rules(combined_code)

        # 2. {static_context} 영역 조립 (C DFG 지문 + RAG에서 가져온 예시 코드)
        static_context_parts = []
        if c_fingerprint_str:
            static_context_parts.append("### Static Analysis (C DFG Fingerprints)\n" + c_fingerprint_str)
        if rag_examples_str:
            static_context_parts.append("### Safe Rust Examples (from RAG)\n" + rag_examples_str)
        
        static_context_combined = "\n\n".join(static_context_parts)
        if not static_context_combined:
            static_context_combined = "// No specific static analysis or examples found."
            
        # 3. 시스템 프롬프트 포맷팅 (.replace()를 사용하여 중괄호 충돌 방지)
        system_content = self.system_template.replace(
            "{static_context}", static_context_combined
        ).replace(
            "{dynamic_rules}", dynamic_rules_str
        )

        # 4. 유저 프롬프트 구성 (원본 C 및 C2Rust 참고 코드 제공)
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
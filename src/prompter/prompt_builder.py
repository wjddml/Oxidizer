# src/prompt_gen.py
import os
import yaml
import re
from pathlib import Path

class CodeScanner:
    """C2Rust 코드를 스캔하여 어떤 문법(키워드)이 사용되었는지 분석합니다."""
    @staticmethod
    def scan(code: str) -> set:
        found_triggers = set()
        # 검색할 기본 키워드들 (정적 분석의 기초)
        keywords = ["malloc", "free", ".offset(", "static mut", "*mut", "libc::"]
        for kw in keywords:
            if kw in code:
                found_triggers.add(kw)
        return found_triggers

class RuleEngine:
    """여러 YAML 파일에서 규칙을 로드하고, 스캔 결과에 맞춰 필터링합니다."""
    def __init__(self, rules_dir: Path):
        self.rules_dir = rules_dir

    def get_active_rules(self, code_triggers: set) -> str:
        active_rules = []
        rule_counter = 1

        if not self.rules_dir.exists():
            return "No rules directory found."

        # rules/ 폴더 안의 모든 yaml 파일을 순회
        for yaml_file in self.rules_dir.glob("*.yaml"):
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data or 'rules' not in data:
                    continue

                for rule in data['rules']:
                    # Trigger가 없거나, 코드에서 발견된 트리거와 하나라도 겹치면 규칙 활성화
                    triggers = rule.get('trigger', [])
                    if not triggers or any(t in code_triggers for t in triggers):
                        formatted_rule = f"{rule_counter}. [{rule['name']}]\n   - {rule['description']}"
                        if rule.get('few_shot'):
                            formatted_rule += f"\n   - Example:\n     {rule['few_shot'].strip()}"
                        active_rules.append(formatted_rule)
                        rule_counter += 1

        if not active_rules:
            return "General idiomatic safe Rust translation required."
        
        return "\n\n".join(active_rules)

class PromptManager:
    """스캐너와 룰 엔진을 결합하여 최종 프롬프트를 생성하는 마스터 클래스입니다."""
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.prompts_dir = self.project_root / "prompts"
        
        self.template_path = self.prompts_dir / "system_template.txt"
        self.rules_dir = self.prompts_dir / "rules"
        
        self.scanner = CodeScanner()
        self.rule_engine = RuleEngine(self.rules_dir)

    def load_system_template(self) -> str:
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template not found: {self.template_path}")
        with open(self.template_path, 'r', encoding='utf-8') as f:
            return f.read()

    def build_translation_prompt(self, c2rust_code: str):
        # 1. 정적 분석: 코드 스캔
        detected_triggers = self.scanner.scan(c2rust_code)
        
        # 2. 규칙 필터링: 상황에 맞는 규칙만 조립
        active_rules_text = self.rule_engine.get_active_rules(detected_triggers)
        
        # 3. 템플릿 로드 및 [CONTEXT] 주입 (현재는 빈칸, 미래를 위한 대비)
        template = self.load_system_template()
        static_context = "No additional global context provided for this chunk."
        
        # 4. 최종 System Instruction 조립
        system_instruction = template.format(
            static_context=static_context,
            dynamic_rules=active_rules_text
        )

        # 5. User Prompt 조립
        user_prompt = f"Here is the C2Rust generated code to translate:\n\n```rust\n{c2rust_code}\n```"

        return system_instruction, user_prompt

# 단독 실행 테스트용
if __name__ == "__main__":
    pm = PromptManager()
    dummy_code = "let p: *mut libc::c_char = libc::malloc(10); p.offset(1);"
    sys_prompt, user_prompt = pm.build_translation_prompt(dummy_code)
    
    print("=== [Code Scanning Result] ===")
    print(pm.scanner.scan(dummy_code))
    print("\n=== [Generated System Instruction] ===\n")
    print(sys_prompt)
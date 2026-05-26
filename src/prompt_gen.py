# src/prompt_gen.py
import os
import yaml
from pathlib import Path

class PromptManager:
    def __init__(self):
        # 프로젝트 루트 경로 찾기 (src/ 의 부모)
        self.project_root = Path(__file__).resolve().parent.parent
        self.prompts_dir = self.project_root / "prompts"
        
        self.template_path = self.prompts_dir / "system_template.txt"
        self.rules_path = self.prompts_dir / "rules.yaml"

    def load_rules(self) -> str:
        """YAML 파일에서 규칙을 읽어와서 하나의 문자열로 예쁘게 포맷팅합니다."""
        if not self.rules_path.exists():
            return "No specific rules provided."

        with open(self.rules_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data or 'rules' not in data:
            return "No valid rules found in YAML."

        formatted_rules = ""
        for i, rule in enumerate(data['rules'], 1):
            formatted_rules += f"{i}. [{rule['name']}]\n   - {rule['description']}\n"
            if rule.get('few_shot'):
                formatted_rules += f"   - Example:\n     {rule['few_shot'].strip()}\n"
            formatted_rules += "\n"

        return formatted_rules.strip()

    def load_system_template(self) -> str:
        """텍스트 템플릿 파일을 읽어옵니다."""
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template file not found at {self.template_path}")
            
        with open(self.template_path, 'r', encoding='utf-8') as f:
            return f.read()

    def build_translation_prompt(self, c2rust_code: str):
        """
        [Step 2: 통찰력 주입]
        템플릿과 YAML 규칙을 결합하여 최종 프롬프트를 생성합니다.
        """
        # 1. 템플릿과 규칙 가져오기
        template = self.load_system_template()
        rules_text = self.load_rules()

        # 2. 템플릿의 {dynamic_rules} 구멍에 규칙 문자열 꽂아 넣기
        system_instruction = template.format(dynamic_rules=rules_text)

        # 3. LLM에게 보낼 User Prompt 구성
        user_prompt = f"Here is the code to translate:\n\n```rust\n{c2rust_code}\n```"

        return system_instruction, user_prompt

# (선택) 단독 실행 테스트용
if __name__ == "__main__":
    pm = PromptManager()
    sys_prompt, user_prompt = pm.build_translation_prompt("// dummy code")
    print("=== [Generated System Instruction] ===\n")
    print(sys_prompt)
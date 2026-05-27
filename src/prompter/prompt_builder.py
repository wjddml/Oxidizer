import yaml
from pathlib import Path

class CodeScanner:
    """C2Rust 코드를 스캔하여 특정 문법(키워드) 사용 여부를 분석합니다."""
    @staticmethod
    def scan(code: str) -> set:
        found_triggers = set()
        keywords = ["malloc", "free", ".offset(", "static mut", "*mut", "libc::", "union "]
        for kw in keywords:
            if kw in code:
                found_triggers.add(kw)
        return found_triggers

class RuleEngine:
    """YAML 파일들에서 규칙을 로드하고 스캔 결과에 맞춰 필터링합니다."""
    def __init__(self, rules_dir: Path):
        self.rules_dir = rules_dir

    def get_active_rules(self, code_triggers: set) -> str:
        active_rules = []
        rule_counter = 1

        if not self.rules_dir.exists():
            return "No rules directory found."

        for yaml_file in self.rules_dir.glob("*.yaml"):
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data or 'rules' not in data:
                    continue

                for rule in data['rules']:
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

class PromptBuilder:
    """스캐너와 룰 엔진을 결합하여 LLM용 메시지 배열을 생성합니다."""
    def __init__(self, config_path: str = "config.yaml"):
        # config.yaml 읽기
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        # 경로 동적 설정
        project_root = Path(__file__).resolve().parent.parent.parent
        prompts_dir_name = self.config.get("paths", {}).get("prompts_dir", "prompts")
        self.prompts_dir = project_root / prompts_dir_name
        
        # 템플릿과 규칙 경로 매핑
        self.template_path = self.prompts_dir / "templates" / "system_template.txt"
        self.rules_dir = self.prompts_dir / "rules"
        
        self.scanner = CodeScanner()
        self.rule_engine = RuleEngine(self.rules_dir)

    def build_messages(self, c2rust_code: str) -> list[dict]:
        """
        코드를 분석하여 LLM 클라이언트가 요구하는 messages 리스트를 반환합니다.
        """
        detected_triggers = self.scanner.scan(c2rust_code)
        active_rules_text = self.rule_engine.get_active_rules(detected_triggers)
        
        if not self.template_path.exists():
            raise FileNotFoundError(f"❌ [Error] 템플릿 파일이 없습니다: {self.template_path}")
            
        with open(self.template_path, 'r', encoding='utf-8') as f:
            template = f.read()
            
        system_instruction = template.format(
            static_context="No additional global context provided for this chunk.",
            dynamic_rules=active_rules_text
        )

        user_prompt = f"Here is the C2Rust generated code to translate:\n\n```rust\n{c2rust_code}\n```"

        return [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ]
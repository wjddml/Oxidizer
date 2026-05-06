# src/prompt_gen.py

class PromptManager:
    def __init__(self):
        # 기본 변환 규칙(Policy)들을 딕셔너리로 관리
        # 언제든지 외부에서 .add_policy()로 규칙을 추가할 수 있습니다.
        self.policies = {
            "semantic_lifting": "Replace raw pointers (*mut T, *const T) with safe Rust types like String, Vec<T>, or slices (&[T], &mut [T]).",
            "borrow_checker": "If multiple mutable pointers cause aliasing issues, use the `.clone()` strategy or iterators to separate lifetimes.",
            "zero_unsafe": "Remove ALL `unsafe` blocks. Do NOT use `libc` functions if safe Rust standard library equivalents exist."
        }

    def add_policy(self, rule_name: str, description: str):
        """새로운 프롬프트 정책을 유연하게 추가합니다."""
        self.policies[rule_name] = description

    def remove_policy(self, rule_name: str):
        """기존 프롬프트 정책을 제거합니다."""
        if rule_name in self.policies:
            del self.policies[rule_name]

    def build_translation_prompt(self, c2rust_code: str):
        """
        [Step 2: 통찰력 주입]
        현재 등록된 정책들을 모아 시스템 지시문(System Instruction)과 사용자 메시지를 생성합니다.
        """
        # 딕셔너리에 있는 정책들을 예쁘게 번호 매겨서 문자열로 조립
        policy_text = ""
        for i, (name, desc) in enumerate(self.policies.items(), 1):
            # ex) 1. Semantic Lifting: Replace raw pointers...
            policy_text += f"{i}. {name.replace('_', ' ').title()}: {desc}\n"

        # Gemini에게 부여할 역할과 가이드라인 (System Instruction)
        system_instruction = f"""You are an expert Rust developer and a C-to-Rust transpiler.
Your task is to refactor the provided C2Rust-generated code into idiomatic, Safe Rust.

[Human Insight Guidelines]
{policy_text}
Return ONLY the complete, compilable Rust code. Do not include markdown blocks like ```rust or any explanations.
"""
        # 실제 변환할 대상 코드
        user_prompt = f"Here is the C2Rust generated code:\n\n{c2rust_code}"

        return system_instruction, user_prompt
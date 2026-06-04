# src/analyzer/skeleton_generator.py
from pathlib import Path
from typing import Dict, List
import tree_sitter_c as ts_c
from tree_sitter import Language, Parser

from llm.llm_factory import create_llm_client

class SkeletonGenerator:
    """
    C 코드의 AST를 분석하여 함수 본문을 제외한 인터페이스(구조체, 시그니처 등)를 추출하고,
    LLM을 이용해 unimplemented!() 매크로로 채워진 Rust Skeleton 프로젝트를 생성합니다.
    """
    def __init__(self, config_path: str = "config.yaml", llm_provider: str = None, llm_model: str = None):
        self.c_language = Language(ts_c.language())
        self.parser = Parser(self.c_language)
        self.llm = create_llm_client(
            config_path,
            provider_override=llm_provider,
            model_override=llm_model
        )
        
    def _extract_c_interface(self, c_code: str) -> str:
        """
        C 코드에서 구조체, 타입 정의, 매크로, 전역 변수, 함수 시그니처만 추출합니다.
        (함수 내부의 복잡한 로직은 모두 제거하여 LLM의 토큰 낭비를 막고 환각을 방지합니다.)
        """
        tree = self.parser.parse(bytes(c_code, "utf8"))
        root_node = tree.root_node
        
        interface_lines = []
        
        for node in root_node.children:
            # 매크로, 구조체, 타입 정의, 전역 변수는 그대로 유지
            if node.type in ["preproc_def", "struct_specifier", "type_definition", "declaration"]:
                interface_lines.append(node.text.decode("utf-8"))
                
            # 함수 정의의 경우, 시그니처만 추출하고 본문은 세미콜론으로 대체
            elif node.type == "function_definition":
                for child in node.children:
                    # 함수 선언부(반환형 + 이름 + 매개변수) 추출
                    if child.type in ["function_declarator", "primitive_type", "type_identifier"]:
                        interface_lines.append(child.text.decode("utf-8"))
                        if child.type == "function_declarator":
                            interface_lines[-1] += ";" # 시그니처 끝에 세미콜론 추가
                            break
                            
        return "\n".join(interface_lines)

    def generate_rust_skeleton(self, c_file_path: Path, c_code: str) -> str:
        """
        추출된 C 인터페이스를 기반으로 Safe Rust 스켈레톤 코드를 생성합니다.
        """
        print(f"🦴 [Skeleton] '{c_file_path.name}'의 인터페이스 추출 및 뼈대 생성 중...")
        
        # 1. C 인터페이스 추출 (본문 제거)
        c_interface = self._extract_c_interface(c_code)
        
        # 2. LLM 스켈레톤 변환 프롬프트 조립
        system_instruction = (
            "You are an expert systems programmer translating C headers and interfaces to Safe Rust.\n"
            "Your task is to generate a compilable Rust 'Skeleton' code based on the provided C interface.\n\n"
            "STRICT RULES:\n"
            "1. Translate all `struct`, `typedef`, and global variables to idiomatic Safe Rust.\n"
            "2. Translate all function signatures. Replace C pointers with Rust references (`&T`, `&mut T`), `Box`, or `Option` where appropriate. Avoid `*mut` and `*const`.\n"
            "3. DO NOT implement the function bodies. You MUST fill EVERY function body strictly with `{ unimplemented!(); }`.\n"
            "4. Do NOT use the `unsafe` keyword anywhere.\n"
            "5. Output ONLY the raw Rust code inside ```rust ``` tags. No explanations."
        )
        
        user_prompt = (
            f"### C Interface extracted from {c_file_path.name}:\n"
            "```c\n"
            f"{c_interface}\n"
            "```\n\n"
            "Generate the corresponding Safe Rust skeleton."
        )
        
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ]
        
        # 3. LLM 호출 및 결과 정제
        response = self.llm.generate(messages)
        return self._extract_code_block(response)

    def _extract_code_block(self, text: str) -> str:
        """LLM 응답에서 순수 Rust 코드만 추출합니다."""
        lines = text.strip().split('\n')
        in_block = False
        code = []
        for line in lines:
            if line.startswith("```"):
                if in_block:
                    break
                in_block = True
                continue
            if in_block:
                code.append(line)
        return "\n".join(code) if code else text

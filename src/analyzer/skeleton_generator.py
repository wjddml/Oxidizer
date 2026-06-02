# src/analyzer/skeleton_generator.py
from pathlib import Path
from typing import Dict, List
import tree_sitter_c as ts_c
from tree_sitter import Language, Parser

from llm.llm_factory import create_llm_client
from utils.logger import logger  # 로거 임포트

class SkeletonGenerator:
    def __init__(self, config_path: str = "config.yaml"):
        self.c_language = Language(ts_c.language())
        self.parser = Parser(self.c_language)
        self.llm = create_llm_client(config_path)
        
    def _extract_c_interface(self, c_code: str) -> str:
        tree = self.parser.parse(bytes(c_code, "utf8"))
        root_node = tree.root_node
        
        interface_lines = []
        
        for node in root_node.children:
            if node.type in ["preproc_def", "struct_specifier", "type_definition", "declaration"]:
                interface_lines.append(node.text.decode("utf-8"))
                
            elif node.type == "function_definition":
                for child in node.children:
                    if child.type in ["function_declarator", "primitive_type", "type_identifier"]:
                        interface_lines.append(child.text.decode("utf-8"))
                        if child.type == "function_declarator":
                            interface_lines[-1] += ";"
                            break
                            
        return "\n".join(interface_lines)

    def generate_rust_skeleton(self, c_file_path: Path, c_code: str) -> str:
        logger.debug(f"🦴 [Skeleton] '{c_file_path.name}'의 인터페이스 추출 및 뼈대 생성 중...")
        
        c_interface = self._extract_c_interface(c_code)
        
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
        
        response = self.llm.generate(messages)
        return self._extract_code_block(response)

    def _extract_code_block(self, text: str) -> str:
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
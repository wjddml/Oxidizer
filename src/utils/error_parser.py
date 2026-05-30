# src/utils/error_parser.py
import re
from typing import List, Dict

class ErrorParser:
    """
    rustc의 stderr 로그를 파싱하여 구조화된 에러 데이터를 추출하고,
    CRUST-Bench의 분류 체계를 확장하여 에러 카테고리를 할당합니다.
    """
    
    def __init__(self):
        # DOTALL을 적용하여 여러 줄에 걸친 에러 메시지도 완벽히 포획
        # 일반 error 뿐만 아니라 fatal error, panic, 코드 없는 에러 등도 낚아챔
        self.error_regex = re.compile(
            r"(?:error|fatal error|panic)(?:\[(E\d{4})\])?:\s*(.*?)\n\s*-->\s*([^\n:]+):(\d+):(\d+)",
            re.IGNORECASE | re.DOTALL
        )
        
        self.category_keywords = {
            "Syntax": ["syntax", "expected", "found", "unknown start of token", "unexpected token"],
            "Borrow/Lifetime": ["borrowed", "borrow", "moved", "lifetime", "lifetimes", "reference to a local variable"],
            "Mutability": ["mutable", "immutable"],
            "Unresolved Import": ["import unresolved", "unresolved import", "unresolved imports"],
            "Missing/Not Found": ["missing", "not found", "cannot find", "undeclared", "Unresolved", "non-existent", "import"],
            "Trait": ["trait"],
            "Type Mismatch": ["cast", "sized types", "bindings", "type", "identifier", "expression", "dereference", "mismatched types"],
            "Arguments": ["args", "argument", "arguments"],
            "Unsafe": ["unsafe"]
        }

    def _categorize_error(self, error_msg: str, error_code: str) -> str:
        lower_msg = error_msg.lower()
        
        # 1. Unsafe 에러 특별 처리 (가장 중요)
        if error_code == "E0133" or "unsafe" in lower_msg:
            return "Unsafe"
            
        # 2. 키워드 기반 카테고리 매칭
        for category, keywords in self.category_keywords.items():
            if any(keyword in lower_msg for keyword in keywords):
                return category
                
        return "Syntax/Other"

    def parse_stderr(self, stderr_output: str) -> List[Dict[str, str]]:
        """
        :return: [{"code": "E0382", "message": "...", "file": "...", "line": "12", "col": "5", "category": "Borrow/Lifetime"}]
        """
        if not stderr_output:
            return []

        parsed_errors = []
        seen_hashes = set()  # 중복 에러 필터링용 해시셋

        # 1. 정규식으로 표준 에러 포맷 파싱
        matches = self.error_regex.finditer(stderr_output)
        
        for match in matches:
            error_code = match.group(1) if match.group(1) else "Unknown"
            # 정규식 DOTALL로 인해 포함된 줄바꿈과 다중 공백을 한 줄로 깔끔하게 압축
            message = re.sub(r'\s+', ' ', match.group(2).strip())
            file_path = match.group(3).strip()
            line = match.group(4)
            col = match.group(5)
            
            # 동일 라인의 동일 에러 중복 수집 방지
            error_hash = f"{error_code}:{file_path}:{line}"
            if error_hash not in seen_hashes:
                seen_hashes.add(error_hash)
                category = self._categorize_error(message, error_code)
                
                parsed_errors.append({
                    "code": error_code,
                    "message": message,
                    "file": file_path,
                    "line": line,
                    "col": col,
                    "category": category
                })

        # 2. 환경적 치명타(Fatal) 방어 코드
        # 정규식 매칭은 안되었지만 컴파일러 자체가 죽은 경우 (OOM 등)
        if not parsed_errors:
            if "memory allocation" in stderr_output.lower():
                parsed_errors.append({
                    "code": "FATAL_OOM",
                    "message": "Rust compiler ran out of memory. Check memory limits.",
                    "file": "env", "line": "0", "col": "0",
                    "category": "Environment"
                })
            elif "panicked" in stderr_output.lower():
                parsed_errors.append({
                    "code": "FATAL_PANIC",
                    "message": "Rust compiler panicked internally.",
                    "file": "env", "line": "0", "col": "0",
                    "category": "Environment"
                })

        # 라인 번호 순으로 정렬하여 리턴 (위에서 아래로 고치는 것이 안정적임)
        parsed_errors.sort(key=lambda x: int(x["line"]))
        return parsed_errors

    def format_for_llm(self, errors: List[Dict[str, str]]) -> str:
        """
        파싱된 에러 리스트를 LLM 프롬프트에 주입하기 좋은 형태의 텍스트로 변환합니다.
        """
        if not errors:
            return "No compilation errors detected."
            
        formatted_str = "## Compilation Errors to Fix:\n"
        for i, err in enumerate(errors, 1):
            if err['category'] == "Environment":
                formatted_str += f"{i}. [Environment/Compiler Crash] {err['message']}\n"
            else:
                formatted_str += f"{i}. [Line {err['line']}] {err['category']} Error ({err['code']}): {err['message']}\n"
            
        return formatted_str
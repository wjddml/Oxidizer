# src/analyzer/c_semantic_extractor.py
import clang.cindex
import os
from ctypes.util import find_library
from pathlib import Path
from typing import Dict, List, Any

# --- libclang 동적 경로 탐색 및 자동 연결 로직 ---
def _setup_libclang():
    if clang.cindex.Config.library_file or clang.cindex.Config.library_path:
        return
        
    # 1차 시도: OS의 기본 동적 라이브러리 탐색
    lib_name = find_library('clang')
    if lib_name:
        try:
            clang.cindex.Config.set_library_file(lib_name)
            return
        except clang.cindex.LibclangError:
            pass
            
    # 2차 시도: 우분투/데비안 계열의 일반적인 설치 경로 순회
    common_paths = [
        '/usr/lib/x86_64-linux-gnu/libclang.so',
        '/usr/lib/x86_64-linux-gnu/libclang.so.1',
        '/usr/lib/llvm-19/lib/libclang.so.1',
        '/usr/lib/llvm-18/lib/libclang.so.1',
        '/usr/lib/llvm-17/lib/libclang.so.1',
        '/usr/lib/llvm-16/lib/libclang.so.1',
        '/usr/lib/llvm-15/lib/libclang.so.1',
        '/usr/lib/llvm-14/lib/libclang.so.1',
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            clang.cindex.Config.set_library_file(path)
            return

_setup_libclang()
# ---------------------------------------------------

class CSemanticExtractor:
    """
    원본 C 코드를 분석하여 포인터 및 변수의 사용 패턴(DFG)을 추적하고,
    RAG 검색을 위한 '의미론적 지문(Semantic Fingerprint)'을 생성합니다.
    """
    def __init__(self):
        # 자동 탐색된 경로를 바탕으로 Index 생성
        self.index = clang.cindex.Index.create()

    def _parse_file(self, file_path: Path) -> clang.cindex.TranslationUnit:
        args = ['-x', 'c', '-std=c99', '-I/usr/include', '-I/usr/local/include']
        return self.index.parse(str(file_path), args=args)

    def extract_semantic_fingerprint(self, file_path: Path, target_func: str) -> Dict[str, Any]:
        """
        특정 함수 내의 포인터 변수를 분석하여 Rust 변환 의도(Intent)를 추출합니다.
        """
        print(f"🔍 [Semantic Extractor] '{target_func}' 함수의 DFG 및 포인터 의도 분석 중...")
        tu = self._parse_file(file_path)
        
        # 1. 대상 함수 노드 찾기
        func_node = None
        for node in tu.cursor.get_children():
            if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.spelling == target_func and node.is_definition():
                func_node = node
                break
                
        if not func_node:
            return {}

        # 2. 변수별 사용 패턴 수집
        fingerprints = {}
        
        def _track_variable_usage(cursor, var_name: str, usage_data: Dict):
            if cursor.kind == clang.cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
                usage_data["is_array"] = True
            elif cursor.kind == clang.cindex.CursorKind.UNARY_OPERATOR:
                # ++, -- 등의 포인터 연산 확인
                tokens = [t.spelling for t in cursor.get_tokens()]
                if '++' in tokens or '--' in tokens:
                    usage_data["is_iterator"] = True
            elif cursor.kind == clang.cindex.CursorKind.CALL_EXPR:
                if cursor.spelling == "malloc":
                    usage_data["is_allocated"] = True
                elif cursor.spelling == "free":
                    usage_data["is_freed"] = True
                    
            for child in cursor.get_children():
                _track_variable_usage(child, var_name, usage_data)

        # 3. 파라미터 및 지역 변수 스캔
        for node in func_node.walk_preorder():
            if node.kind in [clang.cindex.CursorKind.PARM_DECL, clang.cindex.CursorKind.VAR_DECL]:
                type_spelling = node.type.spelling
                
                # 포인터 타입만 집중 분석
                if "*" in type_spelling or "[" in type_spelling:
                    var_name = node.spelling
                    usage_data = {
                        "type": type_spelling,
                        "is_array": False,
                        "is_iterator": False,
                        "is_allocated": False,
                        "is_freed": False,
                        "rust_intent": "Reference" # 기본값
                    }
                    
                    # 함수 본문 전체에서 이 변수가 어떻게 쓰이는지 추적
                    _track_variable_usage(func_node, var_name, usage_data)
                    
                    # 4. 수집된 DFG 데이터를 기반으로 Rust Intent 결정 (Expert Rule)
                    if usage_data["is_allocated"]:
                        if usage_data["is_array"]:
                            usage_data["rust_intent"] = "Vec<T>"
                        else:
                            usage_data["rust_intent"] = "Box<T>"
                    elif usage_data["is_iterator"]:
                        usage_data["rust_intent"] = "Iterator (e.g., .iter())"
                    elif usage_data["is_array"]:
                        usage_data["rust_intent"] = "&[T] (Slice)"
                        
                    fingerprints[var_name] = usage_data

        return {"function": target_func, "fingerprints": fingerprints}

    def format_for_prompt(self, fingerprint_data: Dict[str, Any]) -> str:
        """분석 결과를 프롬프트에 주입하기 좋은 마크다운 형태로 변환합니다."""
        if not fingerprint_data or not fingerprint_data.get("fingerprints"):
            return ""
            
        lines = ["### Semantic Fingerprint (C DFG Analysis):"]
        lines.append("Based on data flow analysis, the following C pointers have specific logical intents:")
        
        for var, data in fingerprint_data["fingerprints"].items():
            features = []
            if data["is_array"]: features.append("Array Access")
            if data["is_iterator"]: features.append("Pointer Arithmetic")
            if data["is_allocated"]: features.append("Heap Allocated")
            
            feat_str = ", ".join(features) if features else "Scalar usage"
            lines.append(f"- **`{var}`** (`{data['type']}`): Detected features: [{feat_str}]. **Recommended Rust Type:** `{data['rust_intent']}`")
            
        return "\n".join(lines)
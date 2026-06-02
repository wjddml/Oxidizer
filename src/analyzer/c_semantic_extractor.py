# src/analyzer/c_semantic_extractor.py
import clang.cindex
import os
from ctypes.util import find_library
from pathlib import Path
from typing import Dict, List, Any
from utils.logger import logger  # 로거 임포트

def _setup_libclang():
    if clang.cindex.Config.library_file or clang.cindex.Config.library_path:
        return
        
    lib_name = find_library('clang')
    if lib_name:
        try:
            clang.cindex.Config.set_library_file(lib_name)
            return
        except clang.cindex.LibclangError:
            pass
            
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

class CSemanticExtractor:
    def __init__(self):
        self.index = clang.cindex.Index.create()

    def _parse_file(self, file_path: Path) -> clang.cindex.TranslationUnit:
        args = ['-x', 'c', '-std=c99', '-I/usr/include', '-I/usr/local/include']
        return self.index.parse(str(file_path), args=args)

    def extract_semantic_fingerprint(self, file_path: Path, target_func: str) -> Dict[str, Any]:
        logger.debug(f"🔍 [Semantic Extractor] '{target_func}' 함수의 DFG 및 포인터 의도 분석 중...")
        tu = self._parse_file(file_path)
        
        func_node = None
        for node in tu.cursor.get_children():
            if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.spelling == target_func and node.is_definition():
                func_node = node
                break
                
        if not func_node:
            return {}

        fingerprints = {}
        
        def _track_variable_usage(cursor, var_name: str, usage_data: Dict):
            if cursor.kind == clang.cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
                usage_data["is_array"] = True
            elif cursor.kind == clang.cindex.CursorKind.UNARY_OPERATOR:
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

        for node in func_node.walk_preorder():
            if node.kind in [clang.cindex.CursorKind.PARM_DECL, clang.cindex.CursorKind.VAR_DECL]:
                type_spelling = node.type.spelling
                
                if "*" in type_spelling or "[" in type_spelling:
                    var_name = node.spelling
                    usage_data = {
                        "type": type_spelling,
                        "is_array": False,
                        "is_iterator": False,
                        "is_allocated": False,
                        "is_freed": False,
                        "rust_intent": "Reference"
                    }
                    
                    _track_variable_usage(func_node, var_name, usage_data)
                    
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
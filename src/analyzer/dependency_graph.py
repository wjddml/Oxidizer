# src/analyzer/dependency_graph.py
import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import tree_sitter_c as ts_c
from tree_sitter import Language, Parser

class DependencyAnalyzer:
    """
    Tree-sitter를 활용하여 C 프로젝트의 구조적 의존성(#include)을 파악하고,
    안전한 번역 순서를 위한 위상 정렬(Topological Sort)을 수행합니다.
    """
    
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        
        # Tree-sitter 파서 초기화
        self.c_language = Language(ts_c.language())
        self.parser = Parser(self.c_language)
        
        self.files: Dict[str, str] = {}  # 파일 상대경로 -> 소스 코드
        self.dependencies: Dict[str, List[str]] = defaultdict(list)
        
    def scan_project(self, src_folders: List[str] = ["."]):
        """프로젝트 내의 모든 .c, .h 파일을 스캔하고 메모리에 적재합니다."""
        for folder in src_folders:
            scan_path = self.project_root / folder
            if not scan_path.exists():
                continue
                
            for root, _, fs in os.walk(scan_path):
                if 'test' in Path(root).name.lower():  # 테스트 폴더 제외
                    continue
                    
                for f in fs:
                    if 'test' in f.lower():
                        continue
                        
                    if f.endswith('.c') or f.endswith('.h'):
                        file_path = Path(root) / f
                        rel_path = file_path.relative_to(self.project_root).as_posix()
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                                self.files[rel_path] = file.read()
                        except Exception as e:
                            print(f"⚠️ [Warning] 파일 읽기 실패 ({rel_path}): {e}")

    def extract_includes(self):
        """Tree-sitter를 이용해 각 파일의 로컬 #include "..." 의존성을 추출합니다."""
        for rel_path, source_code in self.files.items():
            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node
            
            # 전처리기 include 구문 탐색
            for child in root_node.children:
                if child.type == "preproc_include":
                    include_text = child.text.decode("utf-8").strip()
                    # #include "filename.h" 패턴만 추출 (시스템 헤더 <...> 제외)
                    match = re.search(r'#include\s+"([^"]+)"', include_text)
                    if match:
                        included_file = match.group(1)
                        # 상대 경로 매칭 로직 (단순화된 형태)
                        matched_path = self._resolve_include_path(rel_path, included_file)
                        if matched_path:
                            self.dependencies[rel_path].append(matched_path)

    def _resolve_include_path(self, current_file: str, included_file: str) -> str | None:
        """include된 파일명이 프로젝트 내 어떤 파일에 해당하는지 찾습니다."""
        include_base = Path(included_file).name
        for proj_file in self.files.keys():
            if Path(proj_file).name == include_base:
                return proj_file
        return None

    def find_circular_dependencies(self) -> List[List[str]]:
        """Tarjan 알고리즘을 사용하여 순환 참조(SCC)를 탐지합니다."""
        disc_time = {}
        low_link = {}
        on_stack = set()
        stack = []
        scc = []
        time = [0]
        
        def tarjan(node):
            disc_time[node] = time[0]
            low_link[node] = time[0]
            time[0] += 1
            stack.append(node)
            on_stack.add(node)
            
            for neighbor in self.dependencies.get(node, []):
                if neighbor not in disc_time:
                    tarjan(neighbor)
                    low_link[node] = min(low_link[node], low_link[neighbor])
                elif neighbor in on_stack:
                    low_link[node] = min(low_link[node], disc_time[neighbor])
                    
            if low_link[node] == disc_time[node]:
                component = []
                while True:
                    v = stack.pop()
                    on_stack.remove(v)
                    component.append(v)
                    if v == node:
                        break
                if len(component) > 1 or (len(component) == 1 and component[0] in self.dependencies.get(component[0], [])):
                    scc.append(component)
                    
        for node in list(self.files.keys()):
            if node not in disc_time:
                tarjan(node)
                
        return scc

    def topological_sort(self) -> List[str]:
        """DFS 기반으로 파일 번역 순서(Callee -> Caller)를 위상 정렬합니다."""
        visited = set()
        temp_mark = set()
        order = []
        
        def visit(node):
            if node in temp_mark:
                return  # Cycle detected, handled separately
            if node not in visited:
                temp_mark.add(node)
                for neighbor in self.dependencies.get(node, []):
                    visit(neighbor)
                temp_mark.remove(node)
                visited.add(node)
                order.append(node)
                
        # 독립적인 노드들도 포함되도록 모든 파일에 대해 실행
        for node in sorted(self.files.keys()):
            if node not in visited:
                visit(node)
                
        return order

    def get_translation_order(self) -> Tuple[List[str], List[List[str]]]:
        """최종적으로 정렬된 번역 순서와 순환 참조 목록을 반환합니다."""
        self.extract_includes()
        cycles = self.find_circular_dependencies()
        order = self.topological_sort()
        return order, cycles
# src/analyzer/dependency_graph.py
import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import tree_sitter_c as ts_c
from tree_sitter import Language, Parser
from utils.logger import logger  # 로거 임포트

class DependencyAnalyzer:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        
        self.c_language = Language(ts_c.language())
        self.parser = Parser(self.c_language)
        
        self.files: Dict[str, str] = {}
        self.dependencies: Dict[str, List[str]] = defaultdict(list)
        
    def scan_project(self, src_folders: List[str] = ["."]):
        for folder in src_folders:
            scan_path = self.project_root / folder
            if not scan_path.exists():
                continue
                
            for root, _, fs in os.walk(scan_path):
                if 'test' in Path(root).name.lower():
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
                            logger.warning(f"⚠️ [Warning] 파일 읽기 실패 ({rel_path}): {e}")

    def extract_includes(self):
        for rel_path, source_code in self.files.items():
            tree = self.parser.parse(bytes(source_code, "utf8"))
            root_node = tree.root_node
            
            for child in root_node.children:
                if child.type == "preproc_include":
                    include_text = child.text.decode("utf-8").strip()
                    match = re.search(r'#include\s+"([^"]+)"', include_text)
                    if match:
                        included_file = match.group(1)
                        matched_path = self._resolve_include_path(rel_path, included_file)
                        if matched_path:
                            self.dependencies[rel_path].append(matched_path)

    def _resolve_include_path(self, current_file: str, included_file: str) -> str | None:
        include_base = Path(included_file).name
        for proj_file in self.files.keys():
            if Path(proj_file).name == include_base:
                return proj_file
        return None

    def find_circular_dependencies(self) -> List[List[str]]:
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
        visited = set()
        temp_mark = set()
        order = []
        
        def visit(node):
            if node in temp_mark:
                return
            if node not in visited:
                temp_mark.add(node)
                for neighbor in self.dependencies.get(node, []):
                    visit(neighbor)
                temp_mark.remove(node)
                visited.add(node)
                order.append(node)
                
        for node in sorted(self.files.keys()):
            if node not in visited:
                visit(node)
                
        return order

    def get_translation_order(self) -> Tuple[List[str], List[List[str]]]:
        self.extract_includes()
        cycles = self.find_circular_dependencies()
        order = self.topological_sort()
        return order, cycles
# src/agent/orchestrator.py
import re
import shutil
import subprocess
import yaml
from pathlib import Path
from typing import Optional

from llm.llm_factory import create_llm_client
from prompter.prompt_builder import PromptBuilder
from agent.repair_agent import RepairAgent
from utils.cargo_runner import CargoRunner
from utils.test_runner import TestRunner
from utils.file_io import WorkspaceManager

from analyzer.dependency_graph import DependencyAnalyzer
from analyzer.skeleton_generator import SkeletonGenerator
from analyzer.c_semantic_extractor import CSemanticExtractor
from prompter.rag_retriever import RagRetriever

class Orchestrator:
    """
    Oxidizer 하이브리드 파이프라인 사령탑.
    (Tree-sitter 뼈대 생성 ➡️ Clang DFG 분석 ➡️ RAG 예시 검색 ➡️ LLM 합성 ➡️ Repair)
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = self.project_root / self.config.get("paths", {}).get("data_dir", "data") / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.llm = create_llm_client(config_path)
        self.prompt_builder = PromptBuilder(config_path)
        self.repair_agent = RepairAgent(config_path)
        self.cargo_runner = CargoRunner(config_path)
        self.test_runner = TestRunner()
        self.workspace = WorkspaceManager(self.output_dir)
        
        self.skeleton_gen = SkeletonGenerator(config_path)
        self.c_extractor = CSemanticExtractor()
        self.rag_retriever = RagRetriever()
        
        # RAG 시드 예시 데이터베이스 빌드 (data/examples 폴더)
        examples_path = self.project_root / "data" / "examples"
        examples_path.mkdir(parents=True, exist_ok=True)
        self.rag_retriever.seed_database(examples_path)

    def _run_c2rust(self, c_file: Path) -> Optional[Path]:
        """참고용 C2Rust 코드 임시 생성"""
        temp_c_file = self.output_dir / c_file.name
        shutil.copy2(c_file, temp_c_file)
        try:
            subprocess.run(
                ["c2rust", "transpile", str(temp_c_file.name)],
                cwd=self.output_dir, capture_output=True, text=True, check=True
            )
            generated_rs_path = self.output_dir / temp_c_file.with_suffix('.rs').name
            temp_c_file.unlink(missing_ok=True)
            return generated_rs_path if generated_rs_path.exists() else None
        except subprocess.CalledProcessError:
            return None

    def _parse_llm_response(self, text: str) -> tuple[str, str, str]:
        plan_match = re.search(r'// PLAN:(.*?)(?=<IMPORTS>|<FUNC>|$)', text, re.DOTALL)
        imports_match = re.search(r'<IMPORTS>(.*?)</IMPORTS>', text, re.DOTALL)
        func_match = re.search(r'<FUNC>(.*?)</FUNC>', text, re.DOTALL)

        plan = plan_match.group(1).strip() if plan_match else ""
        imports = imports_match.group(1).strip() if imports_match else ""
        func_body = func_match.group(1).strip() if func_match else ""
        
        if not func_body:
            func_body = self.repair_agent._extract_rust_code(text)
            
        return plan, imports, func_body

    def _inject_into_skeleton(self, skeleton_code: str, imports: str, func_body: str) -> str:
        injected_code = skeleton_code
        if imports:
            injected_code = f"{imports}\n\n{injected_code}"
        if func_body:
            injected_code = re.sub(r'\{[\s\n]*unimplemented!\(\);[\s\n]*\}', f"{{\n{func_body}\n}}", injected_code, count=1)
        return injected_code

    def run_pipeline(self, c_file: Path, input_data: str = None, expected_output: str = None, options: dict = None) -> bool:
        if options is None:
            options = {"use_skeleton": True, "use_dfg": True, "use_rag": True, "use_repair": True}

        print("="*60)
        print(f"🔥 Oxidizer 파이프라인 가동: {c_file.name}")
        print("="*60)
        
        with open(c_file, "r", encoding="utf-8") as f:
            c_code = f.read()
            
        # 1. 뼈대 생성
        rust_skeleton_code = ""
        if options.get("use_skeleton", True):
            rust_skeleton_code = self.skeleton_gen.generate_rust_skeleton(c_file, c_code)
        
        # 2. C DFG 분석 (지문 추출)
        c_fingerprint = {}
        c_fingerprint_str = ""
        if options.get("use_dfg", True):
            c_fingerprint = self.c_extractor.extract_semantic_fingerprint(c_file, "main")
            c_fingerprint_str = self.c_extractor.format_for_prompt(c_fingerprint)
        
        # 3. 참고용 C2Rust 생성
        c2rust_rs_path = self._run_c2rust(c_file)
        c2rust_code = self.workspace.read_code(c2rust_rs_path) if c2rust_rs_path else ""
            
        # 4. RAG 처방전 (Safe Rust 예시) 검색
        rag_examples_str = ""
        if options.get("use_rag", True):
            retrieved_snippets = self.rag_retriever.retrieve_examples(c_fingerprint)
            rag_examples_str = self.rag_retriever.format_for_prompt(retrieved_snippets)
        
        # 5. 프롬프트 조립 (5대 YAML 규칙 자동 매핑 포함)
        print("\n🧠 [Phase 4] LLM에게 변환 요청 중...")
        master_messages = self.prompt_builder.build_master_prompt(
            c_code=c_code,
            c2rust_code=c2rust_code,
            c_fingerprint_str=c_fingerprint_str,
            rag_examples_str=rag_examples_str
        )
        
        llm_response = self.llm.generate(master_messages)
        plan, imports, func_body = self._parse_llm_response(llm_response)
        
        if plan:
            print(f"\n💡 [LLM Reasoning PLAN]\n{plan}\n")
            
        # 6. 스켈레톤 이식
        if options.get("use_skeleton", True) and rust_skeleton_code:
            final_code = self._inject_into_skeleton(rust_skeleton_code, imports, func_body)
        else:
            final_code = f"{imports}\n\n{func_body}" if func_body else self.repair_agent._extract_rust_code(llm_response)
        
        final_rs_path = self.output_dir / c_file.with_suffix('.rs').name
        self.workspace.write_code(final_rs_path, final_code)
        
        # 7. 사후 복구
        if options.get("use_repair", True):
            target_rs_path = self.repair_agent.run(final_rs_path, c_file.stem, is_bin=True)
            if not target_rs_path:
                print("\n❌ 파이프라인 완료 실패: 컴파일 수리 불가능")
                return False
            print(f"\n✅ 파이프라인 성공! 결과물: {target_rs_path}")
        else:
            print(f"\n✅ 결과물 저장 완료: {final_rs_path}")

        return True
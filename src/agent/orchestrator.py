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
from utils.logger import logger  # 전역 로거 임포트

from analyzer.dependency_graph import DependencyAnalyzer
from analyzer.skeleton_generator import SkeletonGenerator
from analyzer.c_semantic_extractor import CSemanticExtractor
from prompter.rag_retriever import RagRetriever

class Orchestrator:
    """
    Oxidizer 하이브리드 파이프라인 사령탑.
    (Tree-sitter 뼈대 생성 ➡️ Clang DFG 분석 ➡️ RAG 예시 검색 ➡️ LLM 합성 ➡️ Repair)
    """
    
    def __init__(self, config_path: str = "config.yaml", llm_provider: str = None, llm_model: str = None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = self.project_root / self.config.get("paths", {}).get("data_dir", "data") / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # CLI에서 넘어온 LLM 옵션을 팩토리와 RepairAgent로 전달
        self.llm = create_llm_client(config_path, provider_override=llm_provider, model_override=llm_model)
        self.prompt_builder = PromptBuilder(config_path)
        self.repair_agent = RepairAgent(config_path, llm_provider=llm_provider, llm_model=llm_model)
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

    def _parse_llm_response(self, response_text: str) -> tuple[str, str]:
        """
        LLM 응답에서 구조화된 마크다운을 파싱하여 plan과 safe rust 코드를 안전하게 추출합니다.
        유연한 정규식과 강력한 Fallback 필터로 백틱(```) 찌꺼기 혼입을 원천 차단합니다.
        """
        refined = response_text.strip()
        plan = ""
        rust_code = ""
        
        plan_marker = "### 1. TRANSLATION PLAN"
        code_marker = "### 2. SAFE RUST CODE"
        
        plan_start = refined.find(plan_marker)
        code_start = refined.find(code_marker)
        
        # 1. Translation Plan 추출
        if plan_start != -1:
            end_plan_idx = code_start if code_start != -1 else len(refined)
            plan = refined[plan_start + len(plan_marker):end_plan_idx].strip()
            
        # 2. Safe Rust Code 추출
        # code_marker 이후의 텍스트에 한정해서 첫 번째 코드 블록만 스캔합니다.
        target_text = refined[code_start:] if code_start != -1 else refined
        
        backticks = "`" * 3
        # 줄바꿈(\n) 강제 조건을 \s* 로 완화하여 백틱 주변의 형태가 어긋나도 유연하게 매칭
        pattern = rf'{backticks}(?:rust)?\s*(.*?)\s*{backticks}'
        match = re.search(pattern, target_text, re.DOTALL)
        
        if match:
            rust_code = match.group(1).strip()
        else:
            # 3. 방어 코드 (Fallback)
            # 마커 이후의 텍스트 전체를 가져오되, 혹시 모를 백틱 찌꺼기를 강제로 제거
            if code_start != -1:
                rust_code = refined[code_start + len(code_marker):].strip()
            else:
                rust_code = refined
                
            # 텍스트 앞부분의 ```rust 또는 ``` 제거
            rust_code = re.sub(rf'^{backticks}(?:rust)?\s*', '', rust_code, flags=re.IGNORECASE)
            # 텍스트 뒷부분의 ``` 제거
            rust_code = re.sub(rf'\s*{backticks}$', '', rust_code)
            
            rust_code = rust_code.strip()
                
        return plan, rust_code

    def run_pipeline(self, c_file: Path, input_data: str = None, expected_output: str = None, options: dict = None) -> bool:
        if options is None:
            options = {"use_skeleton": True, "use_dfg": True, "use_rag": True, "use_repair": True}

        logger.info("="*60)
        logger.info(f"🔥 Oxidizer 파이프라인 가동: {c_file.name}")
        logger.info("="*60)
        
        with open(c_file, "r", encoding="utf-8") as f:
            c_code = f.read()
            
        # 1. 뼈대 생성
        rust_skeleton_code = ""
        if options.get("use_skeleton", True):
            rust_skeleton_code = self.skeleton_gen.generate_rust_skeleton(c_file, c_code)
        
        # 2. C DFG 분석
        c_fingerprint = {}
        c_fingerprint_str = ""
        if options.get("use_dfg", True):
            c_fingerprint = self.c_extractor.extract_semantic_fingerprint(c_file, "main")
            c_fingerprint_str = self.c_extractor.format_for_prompt(c_fingerprint)
        
        # 3. 참고용 C2Rust 생성
        c2rust_rs_path = self._run_c2rust(c_file)
        c2rust_code = self.workspace.read_code(c2rust_rs_path) if c2rust_rs_path else ""
            
        # 4. RAG 처방전 검색
        rag_examples_str = ""
        if options.get("use_rag", True):
            retrieved_snippets = self.rag_retriever.retrieve_examples(c_fingerprint)
            rag_examples_str = self.rag_retriever.format_for_prompt(retrieved_snippets)
        
        # 5. 프롬프트 조립 및 LLM 호출
        logger.info("🧠 [Phase 4] LLM에게 변환 요청 중...")
        master_messages = self.prompt_builder.build_master_prompt(
            c_code=c_code,
            c2rust_code=c2rust_code,
            c_fingerprint_str=c_fingerprint_str,
            rag_examples_str=rag_examples_str,
            skeleton_code=rust_skeleton_code
        )
        
        # 원시 프롬프트를 디버그 로그에만 기록
        logger.debug(f"MASTER PROMPT MESSAGES:\n{master_messages}")
        
        llm_response = self.llm.generate(master_messages)
        plan, final_code = self._parse_llm_response(llm_response)
        
        if plan:
            logger.info("💡 [LLM Reasoning PLAN] 추출 완료 (디버그 로그 참조)")
            logger.debug(f"LLM Reasoning PLAN:\n{plan}")
            
        # 6. 결과물 저장
        final_rs_path = self.output_dir / c_file.with_suffix('.rs').name
        self.workspace.write_code(final_rs_path, final_code)
        
        # 7. 사후 복구 (Repair Agent)
        if options.get("use_repair", True):
            target_rs_path = self.repair_agent.run(final_rs_path, c_file.stem, is_bin=True)
            if not target_rs_path:
                logger.error("❌ 파이프라인 완료 실패: 컴파일 수리 불가능")
                return False
            logger.info(f"✅ 파이프라인 성공! 결과물: {target_rs_path}")
        else:
            logger.info(f"✅ 결과물 저장 완료: {final_rs_path}")

        return True
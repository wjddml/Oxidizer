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
from analyzer.mir_slicer import MIRAnalyzer
from prompter.rag_retriever import RagRetriever

class Orchestrator:
    """
    Oxidizer 파이프라인의 총괄 지휘자.
    분석 ➡️ 뼈대 구축 ➡️ 의미 추출 ➡️ RAG 처방 ➡️ 본문 이식 ➡️ 컴파일 복구를 수행합니다.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = self.project_root / self.config.get("paths", {}).get("data_dir", "data") / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 모듈 인스턴스화
        self.llm = create_llm_client(config_path)
        self.prompt_builder = PromptBuilder(config_path)
        self.repair_agent = RepairAgent(config_path)
        self.cargo_runner = CargoRunner(config_path)
        self.test_runner = TestRunner()
        self.workspace = WorkspaceManager(self.output_dir)
        
        self.skeleton_gen = SkeletonGenerator(config_path)
        self.c_extractor = CSemanticExtractor()
        self.mir_analyzer = MIRAnalyzer()
        self.rag_retriever = RagRetriever()
        
        # RAG 시드 규칙 데이터베이스 빌드
        rules_path = self.project_root / self.config.get("paths", {}).get("prompts_dir", "prompts") / "rules"
        if rules_path.exists():
            self.rag_retriever.seed_database(rules_path)

    def _run_c2rust(self, c_file: Path) -> Optional[Path]:
        """[Phase 2 - Prep] 컴파일러 분석을 위해 c2rust 코드를 임시 생성합니다."""
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
        """LLM 응답에서 PLAN, IMPORTS, FUNC 태그를 파싱합니다."""
        plan_match = re.search(r'// PLAN:(.*?)(?=<IMPORTS>|<FUNC>|$)', text, re.DOTALL)
        imports_match = re.search(r'<IMPORTS>(.*?)</IMPORTS>', text, re.DOTALL)
        func_match = re.search(r'<FUNC>(.*?)</FUNC>', text, re.DOTALL)

        plan = plan_match.group(1).strip() if plan_match else ""
        imports = imports_match.group(1).strip() if imports_match else ""
        func_body = func_match.group(1).strip() if func_match else ""
        
        # 태그를 찾지 못한 경우에 대한 폴백 (일반적인 코드 블록 파싱)
        if not func_body:
            func_body = self.repair_agent._extract_rust_code(text)
            
        return plan, imports, func_body

    def _inject_into_skeleton(self, skeleton_code: str, imports: str, func_body: str) -> str:
        """Skeleton 코드의 최상단에 imports를 넣고, unimplemented!()를 실제 함수로 교체합니다."""
        injected_code = skeleton_code
        if imports:
            injected_code = f"{imports}\n\n{injected_code}"
            
        # 단순 치환 로직 (실제로는 정규식이나 Tree-sitter로 더 정밀하게 치환 가능)
        # Skeleton 생성기가 함수 내부를 { unimplemented!(); } 로 만들었다고 가정
        if func_body:
            injected_code = re.sub(r'\{[\s\n]*unimplemented!\(\);[\s\n]*\}', f"{{\n{func_body}\n}}", injected_code, count=1)
            
        return injected_code

    def run_pipeline(self, c_file: Path, input_data: str = None, expected_output: str = None, options: dict = None) -> bool:
        """Oxidizer 하이브리드 파이프라인 전체 가동 (모듈 선택형)"""
        if options is None:
            options = {"use_skeleton": True, "use_dfg": True, "use_mir": True, "use_rag": True, "use_repair": True}

        print("="*60)
        print(f"🔥 Oxidizer 파이프라인 가동: {c_file.name}")
        print(f"⚙️ 활성 모듈: {', '.join([k.replace('use_', '') for k, v in options.items() if v])}")
        print("="*60)
        
        with open(c_file, "r", encoding="utf-8") as f:
            c_code = f.read()
            
        # [Phase 1] Safe Rust 스켈레톤(뼈대) 생성
        rust_skeleton_code = ""
        if options["use_skeleton"]:
            rust_skeleton_code = self.skeleton_gen.generate_rust_skeleton(c_file, c_code)
        
        # [Phase 2 - A] 정적 분석 (C DFG 지문 추출)
        c_fingerprint = {}
        c_fingerprint_str = ""
        if options["use_dfg"]:
            c_fingerprint = self.c_extractor.extract_semantic_fingerprint(c_file, "main")
            c_fingerprint_str = self.c_extractor.format_for_prompt(c_fingerprint)
        
        # [Phase 2 - B] 컴파일러 분석 (Rust MIR Slicer)
        mir_liveness_str = ""
        c2rust_code = ""
        if options["use_mir"]:
            c2rust_rs_path = self._run_c2rust(c_file)
            if c2rust_rs_path:
                c2rust_code = self.workspace.read_code(c2rust_rs_path)
                project_dir = c2rust_rs_path.parent.parent
                mir_data = self.mir_analyzer.run_slicer(project_dir)
                func_mir = self.mir_analyzer.extract_liveness_context(mir_data, "main")
                mir_liveness_str = self.mir_analyzer.format_mir_feedback_for_llm(func_mir)
            
        # [Phase 3] RAG 처방전 검색
        rag_rules_str = ""
        if options["use_rag"]:
            # DFG 지문이 없으면 빈 딕셔너리가 전달되어 빈 결과 반환됨
            retrieved_rules = self.rag_retriever.retrieve_rules(c_fingerprint)
            rag_rules_str = self.rag_retriever.format_for_prompt(retrieved_rules)
        
        # [Phase 4] 프롬프트 조립 및 생성 요청
        print("\n🧠 [Phase 4] LLM에게 변환 요청 중...")
        master_messages = self.prompt_builder.build_master_prompt(
            c_code=c_code,
            c2rust_code=c2rust_code,
            c_fingerprint_str=c_fingerprint_str,
            mir_liveness_str=mir_liveness_str,
            rag_rules_str=rag_rules_str
        )
        
        llm_response = self.llm.generate(master_messages)
        
        # 마스터 포맷 태그 파싱
        plan, imports, func_body = self._parse_llm_response(llm_response)
        if plan:
            print(f"\n💡 [LLM Reasoning PLAN]\n{plan}\n")
            
        # 스켈레톤 사용 여부에 따른 최종 코드 이식
        if options["use_skeleton"] and rust_skeleton_code:
            final_code = self._inject_into_skeleton(rust_skeleton_code, imports, func_body)
        else:
            # 스켈레톤이 꺼져 있다면, LLM이 생성한 코드를 그대로 사용
            final_code = f"{imports}\n\n{func_body}" if func_body else self.repair_agent._extract_rust_code(llm_response)
        
        final_rs_path = self.output_dir / c_file.with_suffix('.rs').name
        self.workspace.write_code(final_rs_path, final_code)
        
        # [Phase 5] 사후 컴파일 복구 루프 (Syntax Repair Loop)
        if options["use_repair"]:
            project_name = c_file.stem
            target_rs_path = self.repair_agent.run(final_rs_path, project_name, is_bin=True)
            
            if not target_rs_path:
                print("\n❌ 파이프라인 완료 실패: 컴파일 수리 불가능")
                return False
                
            print(f"\n✅ 파이프라인 성공! 결과물: {target_rs_path}")
        else:
            print(f"\n✅ 수리 과정 패스 (Repair Disabled). 결과물: {final_rs_path}")

        return True
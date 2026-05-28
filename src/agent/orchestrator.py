# src/agent/orchestrator.py
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

class Orchestrator:
    """
    Oxidizer 파이프라인의 총괄 지휘자.
    초기 변환부터 컴파일 수리(Phase 1), 논리 수리(Phase 2)까지 전체 흐름을 제어합니다.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        project_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = project_root / self.config.get("paths", {}).get("data_dir", "data") / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_semantic_retries = self.config.get("agent", {}).get("max_retries", 5)
        
        # 모든 모듈 인스턴스화
        self.llm = create_llm_client(config_path)
        self.prompt_builder = PromptBuilder(config_path)
        self.repair_agent = RepairAgent(config_path)
        self.cargo_runner = CargoRunner(config_path)
        self.test_runner = TestRunner()
        self.workspace = WorkspaceManager(self.output_dir)

    def _run_c2rust(self, c_file: Path) -> Optional[Path]:
        """[Step 1] C 코드를 C2Rust를 이용해 초기 .rs 코드로 정적 변환합니다."""
        print(f"\n🚀 [Phase 0] C2Rust 초기 정적 변환 시작: {c_file.name}")
        
        temp_c_file = self.output_dir / c_file.name
        shutil.copy2(c_file, temp_c_file)
        
        try:
            subprocess.run(
                ["c2rust", "transpile", str(temp_c_file.name)],
                cwd=self.output_dir,
                capture_output=True, text=True, check=True
            )
            generated_rs_path = self.output_dir / temp_c_file.with_suffix('.rs').name
            temp_c_file.unlink(missing_ok=True)
            
            if generated_rs_path.exists():
                return generated_rs_path
            return None
        except subprocess.CalledProcessError as e:
            print(f"❌ [Error] C2Rust 변환 실패:\n{e.stderr}")
            return None

    def _semantic_repair_loop(self, project_dir: Path, target_rs_path: Path, project_name: str, input_data: str, expected_output: str) -> bool:
        """[Phase 2] 테스트 결과를 바탕으로 논리적 오류(Semantic Error)를 수정합니다."""
        print(f"\n🧪 [Phase 2] 기능 동등성(Semantic) 검증 및 수리 루프 시작")
        
        binary_path = project_dir / "target" / "debug" / project_name
        
        for attempt in range(1, self.max_semantic_retries + 1):
            # 1. 바이너리 빌드
            build_success, _, build_stderr = self.cargo_runner.run_build(project_dir)
            if not build_success:
                print(f"⚠️ [Semantic Attempt {attempt}] 빌드 실패. (Syntax 루프로 돌아가야 할 수 있음)")
                return False
                
            # 2. 테스트 실행 및 I/O 비교
            status, msg, actual = self.test_runner.run_test(binary_path, input_data, expected_output)
            
            if status == "passed":
                print(f"🎉 [Phase 2 성공] 기능 테스트 통과! 완벽한 Safe Rust 코드가 완성되었습니다.")
                return True
                
            print(f"⚠️ [Semantic Attempt {attempt}] 테스트 실패 ({status}). LLM에게 논리 수리를 요청합니다.")
            
            # 3. LLM에게 I/O 불일치 피드백 전송 (SACToR 방식)
            broken_code = self.workspace.read_code(target_rs_path)
            self.workspace.backup_file(target_rs_path)
            
            semantic_prompt = (
                "### Current Rust Code:\n"
                "```rust\n"
                f"{broken_code}\n"
                "```\n\n"
                "### Test Failure Report:\n"
                f"Type: {status.upper()}\n"
                "Details:\n"
                f"{msg}\n\n"
                "The compiled Rust code does not functionally match the original C code.\n"
                "Fix the logical errors so it produces the expected output.\n"
                "Do NOT change function signatures. Output the ENTIRE repaired file inside ```rust ``` tags."
            )
            
            messages = [
                {"role": "system", "content": "You are an expert Rust developer fixing logical and runtime errors in C-to-Rust translated code."},
                {"role": "user", "content": semantic_prompt}
            ]
            
            response_text = self.llm.generate(messages)
            if not response_text:
                self.workspace.rollback_file(target_rs_path)
                break
                
            repaired_code = self.repair_agent._extract_rust_code(response_text)
            self.workspace.write_code(target_rs_path, repaired_code)
            
        print("❌ [Phase 2 실패] 최대 논리 수리 시도 횟수를 초과했습니다.")
        self.workspace.rollback_file(target_rs_path)
        return False

    def run_pipeline(self, c_file: Path, input_data: str = None, expected_output: str = None) -> bool:
        """
        단일 C 파일에 대해 Oxidizer의 전체 파이프라인을 가동합니다.
        """
        print("="*60)
        print(f"🔥 Oxidizer Pipeline 시작: {c_file.name}")
        print("="*60)
        
        # [Step 1] C2Rust 변환
        c2rust_rs_path = self._run_c2rust(c_file)
        if not c2rust_rs_path:
            return False
            
        c2rust_code = self.workspace.read_code(c2rust_rs_path)
        
        # [Step 2] 인간 통찰력(Human Insight) 기반 1차 LLM 변환
        print("\n🧠 [Phase 1-A] 인간 통찰력 프롬프트 조립 및 1차 Safe Rust 변환 요청...")
        messages = self.prompt_builder.build_messages(c2rust_code)
        initial_safe_code = self.llm.generate(messages)
        initial_safe_code = self.repair_agent._extract_rust_code(initial_safe_code)
        
        # 1차 결과물을 임시 저장
        self.workspace.write_code(c2rust_rs_path, initial_safe_code)
        
        # [Step 3] 구문 수리 (Syntax Repair Loop)
        project_name = c_file.stem
        target_rs_path = self.repair_agent.run(c2rust_rs_path, project_name, is_bin=True)
        
        if not target_rs_path:
            print("\n❌ 파이프라인 중단: 구문(Syntax) 복구 실패")
            return False
            
        # [Step 4] 의미 수리 (Semantic Repair Loop - Test & Verification)
        if input_data is not None and expected_output is not None:
            project_dir = target_rs_path.parent.parent
            is_semantic_success = self._semantic_repair_loop(
                project_dir, target_rs_path, project_name, input_data, expected_output
            )
            return is_semantic_success
            
        print("\n✅ 파이프라인 완료 (테스트 데이터 없음): 구문 수리가 완료된 코드가 저장되었습니다.")
        return True
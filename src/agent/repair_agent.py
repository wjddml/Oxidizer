# src/agent/repair_agent.py
import yaml
from pathlib import Path
from typing import Optional

from utils.file_io import WorkspaceManager
from utils.cargo_runner import CargoRunner
from utils.error_parser import ErrorParser
from prompter.repair_builder import RepairBuilder
from llm.llm_factory import create_llm_client

class RepairAgent:
    """
    컴파일러의 피드백을 받아 LLM에게 수정을 지시하는 자율 복구 에이전트입니다.
    """
    def __init__(self, config_path: str = "config.yaml"):
        # 설정 로드
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.max_retries = self.config.get("agent", {}).get("max_retries", 5)
        
        project_root = Path(__file__).resolve().parent.parent.parent
        data_dir_name = self.config.get("paths", {}).get("data_dir", "data")
        base_output_dir = project_root / data_dir_name / "outputs"
        
        # 에이전트의 손과 발(도구함) 초기화
        self.workspace = WorkspaceManager(base_output_dir)
        self.runner = CargoRunner(config_path)
        self.parser = ErrorParser()
        self.builder = RepairBuilder(config_path)
        self.llm = create_llm_client(config_path)

    def _extract_rust_code(self, response_text: str) -> str:
        """LLM 응답에서 순수 Rust 코드만 안전하게 추출합니다."""
        refined = response_text.strip()
        if refined.startswith("```rust"):
            refined = refined[7:]
        elif refined.startswith("```"):
            refined = refined[3:]
        if refined.endswith("```"):
            refined = refined[:-3]
        return refined.strip()

    def run(self, raw_rs_path: Path, project_name: str, is_bin: bool = True) -> Optional[Path]:
        """
        자동 복구 루프를 실행합니다.
        :return: 복구 성공 시 최종 .rs 파일 경로 반환, 실패 시 None 반환
        """
        print(f"\n🧠 [Repair Agent] '{project_name}' 자동 복구 루프 시작 (최대 {self.max_retries}회)")
        
        # 1. 샌드박스 작업 공간(Cargo Project) 세팅
        project_dir = self.workspace.setup_cargo_project(raw_rs_path, project_name, is_bin)
        target_rs_path = project_dir / "src" / ("main.rs" if is_bin else "lib.rs")
        
        for attempt in range(1, self.max_retries + 1):
            print(f"\n🔄 [Attempt {attempt}/{self.max_retries}] 컴파일 검증 중...")
            
            # 2. 컴파일 검증 (cargo check)
            success, stdout, stderr = self.runner.run_check(project_dir)
            
            if success:
                print(f"✅ [Attempt {attempt}] 컴파일 성공! 안전한 Rust 코드가 확보되었습니다.")
                return target_rs_path
                
            # 3. 에러 파싱 및 카테고리화
            print(f"⚠️ [Attempt {attempt}] 컴파일 실패. 에러를 분석합니다.")
            parsed_errors = self.parser.parse_stderr(stderr)
            formatted_errors = self.parser.format_for_llm(parsed_errors)
            
            # (예외 처리) 파싱된 정규 에러가 없다면(링커 에러, 타임아웃 등) stderr 전체를 피드백으로 사용
            if not parsed_errors:
                formatted_errors = f"## Fatal/Unknown Errors:\n```\n{stderr}\n```"
                parsed_errors = [{"category": "General/Other"}]
                
            # 4. 코드 백업 (LLM이 코드를 망칠 경우를 대비)
            self.workspace.backup_file(target_rs_path)
            broken_code = self.workspace.read_code(target_rs_path)
            
            # 5. 맞춤형 프롬프트 조립
            messages = self.builder.build_repair_messages(broken_code, formatted_errors, parsed_errors, attempt)
            
            # 6. LLM 수리 요청
            print(f"🤖 [Attempt {attempt}] LLM에게 맞춤형 에러 수정 요청 중...")
            response_text = self.llm.generate(messages)
            
            if not response_text:
                print("❌ [Error] LLM 응답이 비어있습니다. 이전 상태로 롤백합니다.")
                self.workspace.rollback_file(target_rs_path)
                break
                
            repaired_code = self._extract_rust_code(response_text)
            
            # 7. 수정된 코드를 파일에 덮어쓰기
            self.workspace.write_code(target_rs_path, repaired_code)
            print(f"📝 [Attempt {attempt}] 수정된 코드를 프로젝트에 적용했습니다.")

        # 루프를 모두 소모했는데도 success가 되지 않은 경우
        print(f"\n❌ [Repair Agent] {self.max_retries}회 시도 초과. 복구에 실패했습니다.")
        self.workspace.rollback_file(target_rs_path)
        return None
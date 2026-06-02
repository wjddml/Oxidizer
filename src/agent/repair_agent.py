# src/agent/repair_agent.py
import yaml
import re
from pathlib import Path
from typing import Optional, Tuple

from utils.file_io import WorkspaceManager
from utils.cargo_runner import CargoRunner
from utils.error_parser import ErrorParser
from prompter.repair_builder import RepairBuilder
from llm.llm_factory import create_llm_client
from utils.logger import logger

class RepairAgent:
    """
    컴파일러의 피드백을 받아 LLM에게 수정을 지시하는 자율 복구 에이전트입니다.
    """
    def __init__(self, config_path: str = "config.yaml", llm_provider: str = None, llm_model: str = None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.max_retries = self.config.get("agent", {}).get("max_retries", 5)
        
        project_root = Path(__file__).resolve().parent.parent.parent
        data_dir_name = self.config.get("paths", {}).get("data_dir", "data")
        base_output_dir = project_root / data_dir_name / "outputs"
        
        self.workspace = WorkspaceManager(base_output_dir)
        self.runner = CargoRunner(config_path)
        self.parser = ErrorParser()
        self.builder = RepairBuilder(config_path)
        
        self.llm = create_llm_client(config_path, provider_override=llm_provider, model_override=llm_model)

    def _extract_rust_code(self, response_text: str) -> str:
        refined = response_text.strip()
        
        plan_marker = "### 1. REPAIR PLAN"
        code_marker = "### 2. FIXED RUST CODE"
        
        plan_start = refined.find(plan_marker)
        code_start = refined.find(code_marker)
        
        if plan_start != -1:
            end_plan_idx = code_start if code_start != -1 else len(refined)
            plan_text = refined[plan_start + len(plan_marker):end_plan_idx].strip()
            if plan_text:
                logger.info(f"   💡 [Repair Plan]: {plan_text.splitlines()[0]}")
                logger.debug(f"FULL REPAIR PLAN:\n{plan_text}")
        
        target_text = refined[code_start:] if code_start != -1 else refined
        
        backticks = "`" * 3
        pattern = rf'{backticks}(?:rust)?\s*(.*?)\s*{backticks}'
        match = re.search(pattern, target_text, re.DOTALL)
        
        if match:
            return match.group(1).strip()
            
        if code_start != -1:
            fallback_text = refined[code_start + len(code_marker):].strip()
        else:
            fallback_text = refined
            
        fallback_text = re.sub(rf'^{backticks}(?:rust)?\s*', '', fallback_text, flags=re.IGNORECASE)
        fallback_text = re.sub(rf'\s*{backticks}$', '', fallback_text)
            
        return fallback_text.strip()

    def run(self, raw_rs_path: Path, project_name: str, is_bin: bool = True) -> tuple[Optional[Path], int]:
        """
        자동 복구 루프를 실행합니다.
        :return: (최종 .rs 파일 경로, 사용된 시도 횟수)
        """
        logger.info(f"🧠 [Repair Agent] '{project_name}' 자동 복구 루프 시작 (최대 {self.max_retries}회)")
        
        project_dir = self.workspace.setup_cargo_project(raw_rs_path, project_name, is_bin)
        target_rs_path = project_dir / "src" / ("main.rs" if is_bin else "lib.rs")
        
        for attempt in range(1, self.max_retries + 1):
            logger.info(f"🔄 [Attempt {attempt}/{self.max_retries}] 컴파일 검증 중...")
            
            success, stdout, stderr = self.runner.run_check(project_dir)
            
            if success:
                logger.info(f"✅ [Attempt {attempt}] 컴파일 성공! 안전한 Rust 코드가 확보되었습니다.")
                return target_rs_path, attempt
                
            logger.warning(f"⚠️ [Attempt {attempt}] 컴파일 실패. 에러를 분석합니다.")
            logger.debug(f"[Attempt {attempt}] COMPILER STDERR:\n{stderr}")
            
            parsed_errors = self.parser.parse_stderr(stderr)
            formatted_errors = self.parser.format_for_llm(parsed_errors)
            
            if not parsed_errors:
                formatted_errors = f"## Fatal/Unknown Errors:\n```\n{stderr}\n```"
                parsed_errors = [{"category": "General/Other"}]
                
            self.workspace.backup_file(target_rs_path)
            broken_code = self.workspace.read_code(target_rs_path)
            
            messages = self.builder.build_repair_messages(broken_code, formatted_errors, parsed_errors, attempt)
            
            logger.info(f"🤖 [Attempt {attempt}] LLM에게 맞춤형 에러 수정 요청 중...")
            response_text = self.llm.generate(messages)
            
            if not response_text:
                logger.error("❌ [Error] LLM 응답이 비어있습니다. 이전 상태로 롤백합니다.")
                self.workspace.rollback_file(target_rs_path)
                return None, attempt
                
            repaired_code = self._extract_rust_code(response_text)
            logger.debug(f"[Attempt {attempt}] REPAIRED CODE:\n{repaired_code}")
            
            self.workspace.write_code(target_rs_path, repaired_code)
            logger.info(f"📝 [Attempt {attempt}] 수정된 코드를 프로젝트에 적용했습니다.")

        logger.error(f"❌ [Repair Agent] {self.max_retries}회 시도 초과. 복구에 실패했습니다.")
        self.workspace.rollback_file(target_rs_path)
        return None, self.max_retries
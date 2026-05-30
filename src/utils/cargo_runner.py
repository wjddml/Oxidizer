# src/utils/cargo_runner.py
import os
import subprocess
import yaml
from pathlib import Path
from typing import Tuple

class CargoRunner:
    """
    Cargo 명령어를 안전하게 실행하는 샌드박스 유틸리티.
    컴파일러(rustc)의 정상적인 실행을 위해 메모리 제한을 해제하고,
    타임아웃 및 출력 길이 제한 기능만 유지합니다.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        # 1. 설정 파일 로드
        self.timeout_seconds = 60
        self.max_output_size = 2 * 1024 * 1024  # 기본 2MB (출력 폭주 방지)
        
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                agent_config = config.get("agent", {})
                self.timeout_seconds = agent_config.get("timeout_seconds", 60)
                
    def _truncate_output(self, output: str) -> str:
        """에러 로그나 출력이 너무 길면 LLM 토큰 낭비를 막기 위해 잘라냄"""
        encoded_output = output.encode('utf-8')
        if len(encoded_output) > self.max_output_size:
            print("   ⚠️ [Warning] Output truncated due to size limit.")
            # 에러는 보통 뒤에 있으므로 뒷부분 위주로 남김
            return encoded_output[-self.max_output_size:].decode('utf-8', 'ignore')
        return output

    def _execute_command(self, command: list[str], cwd: Path) -> Tuple[bool, str, str]:
        """안전하게 명령어를 실행하고 (성공여부, stdout, stderr) 반환"""
        try:
            # 메모리 제한(preexec_fn) 족쇄 해제: rustc가 자유롭게 메모리를 할당할 수 있도록 허용
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )
            
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)
            
            # 프로세스가 OS 시그널에 의해 강제 종료되었는지 검사 (시스템의 진짜 OOM, SIGKILL 등)
            if result.returncode < 0:
                signal_num = abs(result.returncode)
                if signal_num == 9:  # SIGKILL
                    stderr += f"\n\n[FATAL ERROR] Compiler killed by SIGKILL (Signal 9). The host system might be actually out of memory."
                else:
                    stderr += f"\n\n[FATAL ERROR] Compiler terminated abnormally by signal {signal_num}."
            
            return (result.returncode == 0, stdout, stderr)
            
        except subprocess.TimeoutExpired:
            error_msg = f"❌ [Timeout] Command '{' '.join(command)}' exceeded {self.timeout_seconds}s."
            return (False, "", error_msg)
            
        except Exception as e:
            return (False, "", f"❌ [Fatal Error] {str(e)}")

    # --- 외부에서 호출할 API ---

    def run_check(self, project_dir: Path) -> Tuple[bool, str, str]:
        """구문 오류 및 타입 체크만 수행 (가장 빠름, Phase 1 피드백용)"""
        return self._execute_command(["cargo", "check", "--color", "never"], cwd=project_dir)

    def run_build(self, project_dir: Path) -> Tuple[bool, str, str]:
        """바이너리 빌드 수행 (Phase 2 테스팅을 위한 준비)"""
        return self._execute_command(["cargo", "build", "--color", "never"], cwd=project_dir)

    def run_test(self, project_dir: Path) -> Tuple[bool, str, str]:
        """Rust 내부의 #[test] 실행용"""
        return self._execute_command(["cargo", "test", "--color", "never"], cwd=project_dir)
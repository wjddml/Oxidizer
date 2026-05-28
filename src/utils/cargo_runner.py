# src/utils/cargo_runner.py
import os
import subprocess
import yaml
from pathlib import Path
from typing import Tuple

try:
    import resource  # Unix/Linux 시스템 메모리 제한용 (SafeTrans 기법)
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False

class CargoRunner:
    """
    Cargo 명령어를 안전하게 실행하는 샌드박스 유틸리티.
    타임아웃, 메모리 제한, 출력 길이 제한 기능을 포함합니다.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        # 1. 설정 파일 로드
        self.timeout_seconds = 60
        self.memory_limit_mb = 1024  # 기본 1GB
        self.max_output_size = 2 * 1024 * 1024  # 기본 2MB (출력 폭주 방지)
        
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                agent_config = config.get("agent", {})
                self.timeout_seconds = agent_config.get("timeout_seconds", 60)
                
    def _limit_memory(self):
        """서브프로세스가 사용할 메모리 한도를 설정 (OOM 방지)"""
        if HAS_RESOURCE:
            mem_limit_bytes = self.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit_bytes, mem_limit_bytes))

    def _truncate_output(self, output: str) -> str:
        """에러 로그나 출력이 너무 길면 LLM 토큰 낭비를 막기 위해 잘라냄"""
        encoded_output = output.encode('utf-8')
        if len(encoded_output) > self.max_output_size:
            print("⚠️ [Warning] Output truncated due to size limit.")
            # 앞부분과 뒷부분을 섞어서 자르거나 뒷부분 위주로 남김 (에러는 보통 뒤에 있음)
            return encoded_output[-self.max_output_size:].decode('utf-8', 'ignore')
        return output

    def _execute_command(self, command: list[str], cwd: Path) -> Tuple[bool, str, str]:
        """안전하게 명령어를 실행하고 (성공여부, stdout, stderr) 반환"""
        try:
            # Popen 대신 간편하고 안전한 subprocess.run 사용
            # preexec_fn을 통해 자식 프로세스에만 메모리 제한 적용
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                preexec_fn=self._limit_memory if HAS_RESOURCE else None
            )
            
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)
            
            return (result.returncode == 0, stdout, stderr)
            
        except subprocess.TimeoutExpired as e:
            # SafeTrans의 Infinite Loop 대응
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
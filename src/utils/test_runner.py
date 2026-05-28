# src/utils/test_runner.py
import subprocess
import difflib
from pathlib import Path
from typing import Tuple, Optional

try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False

class TestRunner:
    """
    컴파일된 바이너리를 블랙박스 테스팅하여 기능적 동등성(I/O)을 검증합니다.
    SafeTrans 논문의 런타임 검증(무한루프, 메모리 초과 등) 로직을 포함합니다.
    """
    def __init__(self, timeout_seconds: int = 10, memory_limit_mb: int = 512):
        self.timeout_seconds = timeout_seconds
        self.memory_limit_mb = memory_limit_mb
        self.max_output_size = 1 * 1024 * 1024  # 1MB 출력 제한

    def _limit_memory(self):
        """런타임 메모리 제한 (OOM 방지)"""
        if HAS_RESOURCE:
            mem_limit_bytes = self.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit_bytes, mem_limit_bytes))

    def _truncate(self, text: str) -> str:
        encoded = text.encode('utf-8')
        if len(encoded) > self.max_output_size:
            return encoded[:self.max_output_size].decode('utf-8', 'ignore') + "\n...[TRUNCATED]"
        return text

    def run_test(self, binary_path: Path, input_data: str, expected_output: str) -> Tuple[str, str, str]:
        """
        바이너리를 실행하고 결과를 비교합니다.
        :return: (결과상태, 상세메시지, 생성된출력)
                 결과상태: "passed", "failed", "runtime_error", "timeout"
        """
        if not binary_path.exists():
            return "runtime_error", f"Executable not found at {binary_path}", ""

        try:
            # 바이너리 실행 후 stdin으로 input_data 주입
            process = subprocess.Popen(
                [str(binary_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=self._limit_memory if HAS_RESOURCE else None
            )
            
            stdout_data, stderr_data = process.communicate(
                input=input_data.encode('utf-8'), 
                timeout=self.timeout_seconds
            )
            
            actual_output = self._truncate(stdout_data.decode('utf-8', 'ignore').strip())
            error_output = self._truncate(stderr_data.decode('utf-8', 'ignore').strip())
            expected_output = expected_output.strip()

            # 1. 런타임 에러 확인 (Panic, Segfault 등)
            if process.returncode != 0:
                if abs(process.returncode) == 9: # SIGKILL (OOM 등)
                    return "runtime_error", "Memory limit exceeded (Killed).", actual_output
                return "runtime_error", f"Runtime panic/error:\n{error_output}", actual_output

            # 2. 결과 비교 (Functional Equivalence)
            if actual_output == expected_output:
                return "passed", "Output matches exactly.", actual_output
            else:
                # 차이점(Diff) 계산하여 LLM 피드백용으로 제공
                diff = "\n".join(difflib.unified_diff(
                    expected_output.splitlines(), 
                    actual_output.splitlines(),
                    fromfile='Expected', 
                    tofile='Actual',
                    lineterm=''
                ))
                return "failed", f"Output mismatch.\nDiff:\n{diff}", actual_output

        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return "timeout", f"Execution exceeded {self.timeout_seconds}s (Infinite loop detected).", ""
            
        except Exception as e:
            return "runtime_error", f"Execution failed: {str(e)}", ""
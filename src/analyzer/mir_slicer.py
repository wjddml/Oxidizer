# src/analyzer/mir_slicer.py
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

class MIRAnalyzer:
    """
    Rust 컴파일러 내부(MIR)의 Dataflow 분석 결과를 가져와,
    LLM이 이해할 수 있는 변수 생존 주기(Liveness) 및 제어 흐름(CFG) 컨텍스트로 가공합니다.
    (마스터가 구축한 cargo-slicer Rust 바이너리와 통신하는 브릿지 클래스입니다.)
    """
    def __init__(self, slicer_executable: str = "cargo-slicer"):
        self.slicer_executable = slicer_executable

    def run_slicer(self, rust_project_dir: Path) -> List[Dict[str, Any]]:
        """
        대상 Rust 프로젝트에서 cargo-slicer를 실행하여 MIR 분석 결과(JSON)를 추출합니다.
        """
        print(f"🔪 [MIR Slicer] '{rust_project_dir.name}'의 Rust 컴파일러 제어 흐름(CFG/DFG) 분석 중...")
        
        # 실제 환경에서는 cargo-slicer를 호출하여 JSON 결과를 생성합니다.
        # (예: subprocess.run(["cargo", "slicer", "check"], cwd=rust_project_dir))
        # 이 함수는 생성된 output.json을 파싱하여 반환한다고 가정합니다.
        
        output_json_path = rust_project_dir / "output.json"
        
        # [실행 시뮬레이션]
        try:
            # subprocess.run(["cargo", "slicer", "check"], cwd=rust_project_dir, check=True, capture_output=True)
            if output_json_path.exists():
                with open(output_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                print(f"⚠️ [Warning] Slicer 출력 파일을 찾을 수 없습니다: {output_json_path}")
                return []
        except Exception as e:
            print(f"❌ [Error] MIR Slicer 실행 실패: {e}")
            return []

    def extract_liveness_context(self, mir_data: List[Dict[str, Any]], target_func_name: str) -> Optional[Dict[str, Any]]:
        """
        전체 분석 데이터에서 특정 함수의 Live-in, Live-out 및 청크(Chunk) 정보를 추출합니다.
        """
        for func_data in mir_data:
            # func_defid 포맷(예: "DefId(0:4 ~ main[317d]::func)")에서 함수명 추출
            defid_str = func_data.get("func_defid", "")
            if target_func_name in defid_str:
                return func_data
        return None

    def format_mir_feedback_for_llm(self, func_context: Dict[str, Any]) -> str:
        """
        추출된 MIR 분석 데이터를 LLM 프롬프트에 주입할 마크다운 지시문으로 조립합니다.
        """
        if not func_context:
            return ""

        chunks = func_context.get("chunks", [])
        if not chunks:
            # 청크가 나뉘지 않은 짧은 함수일 경우
            return ""

        prompt_lines = [
            "### Compiler MIR Analysis (Dataflow & Liveness):",
            "This function is large and has been sliced into logical blocks. Pay strict attention to the variables that cross block boundaries (Live-in / Live-out):",
        ]

        for i, chunk in enumerate(chunks, 1):
            live_in = chunk.get("live_in", [])
            live_out = chunk.get("live_out", [])
            
            prompt_lines.append(f"\n#### [Chunk {i}]")
            
            if live_in:
                live_in_str = ", ".join([f"`{var}`" for var in live_in])
                prompt_lines.append(f"- **Live-in variables:** {live_in_str} (These must be borrowed or passed correctly from the previous context)")
            else:
                prompt_lines.append("- **Live-in variables:** None")
                
            if live_out:
                live_out_str = ", ".join([f"`{var}`" for var in live_out])
                prompt_lines.append(f"- **Live-out variables:** {live_out_str} (These mutate and escape this block; ensure their ownership/lifetimes are valid for subsequent chunks)")
            else:
                prompt_lines.append("- **Live-out variables:** None")
                
            # Ownership 최적화 가이드라인 주입 (전문가 피드백 반영)
            if any("mut " in var for var in live_out):
                prompt_lines.append("> *Optimization Hint:* Mutable live-out variables indicate state mutation. Consider returning them or using `&mut` to shrink borrow overlap.")

        return "\n".join(prompt_lines)
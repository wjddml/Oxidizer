# src/main.py
import argparse
import shutil
import sys
from pathlib import Path
from agent.orchestrator import Orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"

def check_dependencies():
    # C2Rust는 Phase 2에서 참고용 unsafe 코드를 뽑을 때 여전히 사용되므로 체크 유지
    if shutil.which("c2rust") is None:
        print("❌ [Error] 'c2rust' 명령어를 찾을 수 없습니다. (초기 참고 코드 생성에 필요)")
        return False
    if shutil.which("cargo") is None:
        print("❌ [Error] 'cargo' 명령어를 찾을 수 없습니다.")
        return False
    return True

def main():
    print("="*60)
    print("🔥 Oxidizer Modular Pipeline Engine 가동 준비")
    print("="*60)
    
    parser = argparse.ArgumentParser(description="Oxidizer: RAG & 정적 분석 기반 C-to-Rust 에이전트")
    parser.add_argument("--target", type=str, default="test.c", help="변환할 C 파일 이름")
    parser.add_argument("--input_txt", type=str, default=None, help="테스트 입력 텍스트 파일")
    parser.add_argument("--output_txt", type=str, default=None, help="예상 출력 텍스트 파일")
    
    # 🤖 LLM 제어 옵션 추가
    parser.add_argument("--llm", type=str, choices=["gpt", "claude", "gemini"], help="사용할 LLM 제공자 (config.yaml을 오버라이드)")
    parser.add_argument("--llm-model", type=str, help="사용할 구체적인 LLM 모델명 (ex: gpt-4o, gemini-1.5-pro)")
    
    # 🎛️ 모듈 제어 스위치 (Ablation Study용)
    parser.add_argument("--disable-skeleton", action="store_true", help="[Phase 1] 스켈레톤(뼈대) 생성 비활성화")
    parser.add_argument("--disable-dfg", action="store_true", help="[Phase 2] C DFG 의미론적 분석 비활성화")
    parser.add_argument("--disable-rag", action="store_true", help="[Phase 3] RAG 규칙 검색 비활성화")
    parser.add_argument("--disable-repair", action="store_true", help="[Phase 4] 사후 피드백 복구 루프 비활성화")
    args = parser.parse_args()

    # 옵션 딕셔너리 구성
    pipeline_options = {
        "use_skeleton": not args.disable_skeleton,
        "use_dfg": not args.disable_dfg,
        "use_rag": not args.disable_rag,
        "use_repair": not args.disable_repair
    }

    target_c_file = INPUT_DIR / args.target
    if not target_c_file.exists():
        print(f"❌ [Error] 타겟 파일이 없습니다: {target_c_file}")
        sys.exit(1)

    if not check_dependencies():
        sys.exit(1)

    # 테스트 입출력 데이터 로드
    input_data = None
    expected_output = None
    if args.input_txt and args.output_txt:
        input_path = Path(args.input_txt)
        output_path = Path(args.output_txt)
        if input_path.exists() and output_path.exists():
            with open(input_path, 'r', encoding='utf-8') as f:
                input_data = f.read()
            with open(output_path, 'r', encoding='utf-8') as f:
                expected_output = f.read()

    config_path = str(PROJECT_ROOT / "config.yaml")
    
    # ⚙️ Orchestrator에 LLM 커맨드라인 옵션 전달
    orchestrator = Orchestrator(
        config_path=config_path,
        llm_provider=args.llm,
        llm_model=args.llm_model
    )
    
    success = orchestrator.run_pipeline(
        c_file=target_c_file,
        input_data=input_data,
        expected_output=expected_output,
        options=pipeline_options
    )
    
    if success:
        print("\n✨ Oxidizer 파이프라인이 성공적으로 종료되었습니다.")
    else:
        print("\n💥 Oxidizer 파이프라인이 실패로 종료되었습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main()
# src/main.py
import argparse
import shutil
from pathlib import Path
from agent.orchestrator import Orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"

def check_dependencies(options):
    if options.get("use_mir") and shutil.which("c2rust") is None:
        print("❌ [Error] 'c2rust' 명령어를 찾을 수 없습니다. (MIR 분석에 필요)")
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
    
    # 🎛️ 모듈 제어 스위치 (Ablation Study용)
    parser.add_argument("--disable-skeleton", action="store_true", help="[Phase 1] 스켈레톤(뼈대) 생성 비활성화")
    parser.add_argument("--disable-dfg", action="store_true", help="[Phase 2] C DFG 의미론적 분석 비활성화")
    parser.add_argument("--disable-mir", action="store_true", help="[Phase 2] Rust MIR 수명 추적 비활성화")
    parser.add_argument("--disable-rag", action="store_true", help="[Phase 3] RAG 규칙 검색 비활성화")
    parser.add_argument("--disable-repair", action="store_true", help="[Phase 4] 사후 피드백 복구 루프 비활성화")
    args = parser.parse_args()

    # 옵션 딕셔너리 구성 (기본값 True, disable 플래그가 있으면 False)
    pipeline_options = {
        "use_skeleton": not args.disable_skeleton,
        "use_dfg": not args.disable_dfg,
        "use_mir": not args.disable_mir,
        "use_rag": not args.disable_rag,
        "use_repair": not args.disable_repair
    }

    target_c_file = INPUT_DIR / args.target
    if not target_c_file.exists():
        print(f"❌ [Error] 타겟 파일이 없습니다: {target_c_file}")
        return

    if not check_dependencies(pipeline_options):
        return

    input_data = None
    expected_output = None
    if args.input_txt and args.output_txt:
        # 파일 로드 로직 생략 (기존과 동일하게 구현 가능)
        pass

    config_path = str(PROJECT_ROOT / "config.yaml")
    orchestrator = Orchestrator(config_path=config_path)
    
    # 옵션과 함께 파이프라인 가동
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

if __name__ == "__main__":
    main()
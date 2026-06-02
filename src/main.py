# src/main.py
import argparse
import shutil
import sys
from pathlib import Path
from agent.orchestrator import Orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"

def check_dependencies():
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
    
    # 1. 공통 옵션을 처리할 부모 파서(Parent Parser) 생성
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--config", type=str, default="config.yaml", help="설정 파일 경로")
    common_parser.add_argument("--llm", type=str, choices=["gpt", "claude", "gemini"], help="사용할 LLM 제공자 (config.yaml 오버라이드)")
    common_parser.add_argument("--llm-model", type=str, help="사용할 구체적인 LLM 모델명")
    common_parser.add_argument("--disable-skeleton", action="store_true", help="[Phase 1] 스켈레톤(뼈대) 생성 비활성화")
    common_parser.add_argument("--disable-dfg", action="store_true", help="[Phase 2] C DFG 의미론적 분석 비활성화")
    common_parser.add_argument("--disable-rag", action="store_true", help="[Phase 3] RAG 규칙 검색 비활성화")
    common_parser.add_argument("--disable-repair", action="store_true", help="[Phase 4] 사후 피드백 복구 루프 비활성화")

    # 2. 메인 파서 및 서브 커맨드 등록
    parser = argparse.ArgumentParser(description="Oxidizer: RAG & 정적 분석 기반 C-to-Rust 에이전트")
    subparsers = parser.add_subparsers(dest="command", help="실행할 명령어를 선택하세요")

    # [서브 커맨드] run: 단일 파일 변환
    run_parser = subparsers.add_parser("run", parents=[common_parser], help="단일 C 파일 변환")
    run_parser.add_argument("target", type=str, help="변환할 C 파일 이름 (data/inputs 기준)")
    run_parser.add_argument("--input_txt", type=str, default=None, help="테스트 입력 텍스트 파일")
    run_parser.add_argument("--output_txt", type=str, default=None, help="예상 출력 텍스트 파일")

    # [서브 커맨드] batch: 디렉토리 전체 변환
    batch_parser = subparsers.add_parser("batch", parents=[common_parser], help="디렉토리 내 모든 C 파일 자동 변환")
    batch_parser.add_argument("dir", type=str, help="변환할 디렉토리 경로 (data/inputs 기준)")

    # [서브 커맨드] eval: 성능 평가 및 지표 분석 (예정)
    eval_parser = subparsers.add_parser("eval", parents=[common_parser], help="변환된 코드 지표 분석 및 테스트")
    eval_parser.add_argument("target", type=str, help="평가할 대상 (파일 또는 디렉토리)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if not check_dependencies():
        sys.exit(1)

    # 3. 파이프라인 옵션 구성
    pipeline_options = {
        "use_skeleton": not args.disable_skeleton,
        "use_dfg": not args.disable_dfg,
        "use_rag": not args.disable_rag,
        "use_repair": not args.disable_repair
    }

    config_path = str(PROJECT_ROOT / args.config)

    # 4. 커맨드별 분기 처리
    if args.command == "run":
        target_c_file = INPUT_DIR / args.target
        if not target_c_file.exists():
            print(f"❌ [Error] 타겟 파일이 없습니다: {target_c_file}")
            sys.exit(1)

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
            print("\n✨ Oxidizer 파이프라인 단일 변환이 성공적으로 종료되었습니다.")
        else:
            print("\n💥 Oxidizer 파이프라인 단일 변환이 실패로 종료되었습니다.")
            sys.exit(1)

    elif args.command == "batch":
        target_dir = INPUT_DIR / args.dir
        if not target_dir.exists() or not target_dir.is_dir():
            print(f"❌ [Error] 대상 디렉토리가 없거나 폴더가 아닙니다: {target_dir}")
            sys.exit(1)
        
        c_files = list(target_dir.glob("*.c"))
        if not c_files:
            print(f"⚠️ [Warning] 해당 디렉토리 내에 .c 파일이 없습니다: {target_dir}")
            sys.exit(0)

        print(f"📂 총 {len(c_files)}개의 C 파일을 발견했습니다. 배치 변환을 시작합니다.")
        
        orchestrator = Orchestrator(
            config_path=config_path,
            llm_provider=args.llm,
            llm_model=args.llm_model
        )

        success_count = 0
        for idx, c_file in enumerate(c_files, 1):
            print(f"\n{'='*40}")
            print(f"🔄 [{idx}/{len(c_files)}] 변환 대상: {c_file.name}")
            print(f"{'='*40}")
            if orchestrator.run_pipeline(c_file=c_file, options=pipeline_options):
                success_count += 1
        
        print(f"\n✨ 배치 변환 완료: {success_count}/{len(c_files)} 성공.")

    elif args.command == "eval":
        print("⏳ [Phase 3] 지표 분석 및 테스팅 모듈(eval)은 현재 구축 중입니다.")
        sys.exit(0)

if __name__ == "__main__":
    main()
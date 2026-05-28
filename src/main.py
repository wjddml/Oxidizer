# src/main.py
import argparse
import shutil
from pathlib import Path

# 💡 새롭게 완성된 오케스트레이터 import
from agent.orchestrator import Orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"

def check_dependencies():
    if shutil.which("c2rust") is None:
        print("❌ [Error] 'c2rust' 명령어를 찾을 수 없습니다.")
        return False
    if shutil.which("cargo") is None:
        print("❌ [Error] 'cargo' 명령어를 찾을 수 없습니다. Rust 툴체인을 설치해주세요.")
        return False
    return True

def main():
    print("="*60)
    print("🔥 Oxidizer Pipeline Engine 가동 준비")
    print("="*60)
    
    if not check_dependencies():
        return

    # CLI 인자 파싱 설정
    parser = argparse.ArgumentParser(description="Oxidizer: Autonomous C to Safe Rust Translation Agent")
    parser.add_argument("--target", type=str, default="test.c", help="Target C file in data/inputs directory")
    parser.add_argument("--input_txt", type=str, default=None, help="Path to test input text file (e.g., input.txt)")
    parser.add_argument("--output_txt", type=str, default=None, help="Path to expected output text file (e.g., output.txt)")
    args = parser.parse_args()

    target_c_file = INPUT_DIR / args.target
    if not target_c_file.exists():
        print(f"❌ [Error] 타겟 파일이 없습니다: {target_c_file}")
        return

    # 테스트 데이터 로드 (입력값이 있을 경우 Phase 2 Semantic Repair까지 진행)
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
        else:
            print("⚠️ [Warning] 지정된 테스트 입력/출력 파일을 찾을 수 없습니다. 구문 수리(Phase 1)까지만 진행합니다.")

    # 💡 오케스트레이터 가동
    config_path = str(PROJECT_ROOT / "config.yaml")
    orchestrator = Orchestrator(config_path=config_path)
    
    success = orchestrator.run_pipeline(
        c_file=target_c_file,
        input_data=input_data,
        expected_output=expected_output
    )
    
    if success:
        print("\n✨ Oxidizer 파이프라인이 성공적으로 종료되었습니다.")
    else:
        print("\n💥 Oxidizer 파이프라인이 실패로 종료되었습니다.")

if __name__ == "__main__":
    main()
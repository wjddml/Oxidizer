# src/main.py
import argparse
import shutil
from pathlib import Path
from agent.orchestrator import Orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"

def check_dependencies():
    if shutil.which("c2rust") is None:
        print("❌ [Error] 'c2rust' 명령어를 찾을 수 없습니다.")
        return False
    if shutil.which("cargo") is None:
        print("❌ [Error] 'cargo' 명령어를 찾을 수 없습니다.")
        return False
    return True

def main():
    print("="*60)
    print("🔥 Oxidizer Hybrid Pipeline Engine 가동 준비")
    print("="*60)
    
    if not check_dependencies(): return

    parser = argparse.ArgumentParser(description="Oxidizer: RAG & MIR 기반 C to Safe Rust 에이전트")
    parser.add_argument("--target", type=str, default="test.c", help="변환할 C 파일 이름 (data/inputs 내)")
    args = parser.parse_args()

    target_c_file = INPUT_DIR / args.target
    if not target_c_file.exists():
        print(f"❌ [Error] 타겟 파일이 없습니다: {target_c_file}")
        return

    # 오케스트레이터 가동
    config_path = str(PROJECT_ROOT / "config.yaml")
    orchestrator = Orchestrator(config_path=config_path)
    
    success = orchestrator.run_pipeline(c_file=target_c_file)
    
    if success:
        print("\n✨ Oxidizer 파이프라인이 성공적으로 종료되었습니다.")
    else:
        print("\n💥 Oxidizer 파이프라인이 실패로 종료되었습니다.")

if __name__ == "__main__":
    main()
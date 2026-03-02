import os
import subprocess
import shutil
from pathlib import Path

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"
OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs"

def check_dependencies():
    """파이프라인 실행에 필요한 외부 도구(C2Rust)가 설치되어 있는지 확인합니다."""
    if shutil.which("c2rust") is None:
        print("❌ [Error] 'c2rust' 명령어를 찾을 수 없습니다.")
        print("💡 터미널에서 'cargo install c2rust'를 실행하여 설치해주세요.")
        return False
    return True

def run_c2rust(c_file_path: Path) -> Path:
    """
    [Step 1: 정적 변환]
    C2Rust를 실행하여 C 코드를 Rust로 변환합니다.
    """
    print(f"\n🚀 [Step 1] C2Rust 정적 변환 시작: {c_file_path.name}")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    command = ["c2rust", "transpile", str(c_file_path)]
    
    try:
        result = subprocess.run(
            command, 
            cwd=OUTPUT_DIR, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        # 기본적으로 OUTPUT_DIR에 생성되기를 기대함
        generated_rs_name = c_file_path.with_suffix('.rs').name
        generated_rs_path = OUTPUT_DIR / generated_rs_name
        
        if generated_rs_path.exists():
            print(f"✅ [Step 1] 변환 성공! -> {generated_rs_path}")
            return generated_rs_path
        else:
            # 원본 C 파일이 있는 폴더(INPUT_DIR)에 생성되었는지 확인하는 Fallback 로직
            fallback_path = c_file_path.with_suffix('.rs')
            if fallback_path.exists():
                print(f"💡 [알림] C2Rust가 원본 폴더에 파일을 생성했습니다. Output 폴더로 이동합니다.")
                shutil.move(str(fallback_path), str(generated_rs_path))
                print(f"✅ [Step 1] 변환 성공! -> {generated_rs_path}")
                return generated_rs_path

            # 파일이 아예 안 만들어진 경우 상세 로그 출력
            print("❌ [Error] C2Rust 실행은 성공(코드 0)했으나 변환된 .rs 파일을 찾을 수 없습니다.")
            print("\n" + "="*20 + " [C2Rust 상세 로그] " + "="*20)
            print("[STDOUT]\n", result.stdout)
            print("[STDERR]\n", result.stderr)
            print("="*60)
            return None
            
    except subprocess.CalledProcessError as e:
        print("❌ [Error] C2Rust 변환 중 치명적 오류 발생:")
        print(e.stderr)
        return None

def main():
    print("="*50)
    print("🔥 Oxidizer Pipeline Engine 가동 준비")
    print("="*50)
    
    if not check_dependencies():
        return

    # 테스트할 타겟 파일 설정
    target_c_file = INPUT_DIR / "test.c"
    
    if not target_c_file.exists():
        print(f"❌ [Error] 타겟 파일을 찾을 수 없습니다: {target_c_file}")
        print("💡 data/inputs/ 폴더에 test.c 파일을 만들어주세요.")
        return

    # 1단계: C2Rust 정적 변환
    base_rs_file = run_c2rust(target_c_file)
    
    if base_rs_file:
        print("\n🎉 이번 주 목표 달성! C2Rust 파이프라인 연동 성공!")

if __name__ == "__main__":
    main()
# src/main.py
import subprocess
import shutil
from pathlib import Path

# 💡 새롭게 재구조화된 모듈들 import
from prompter.prompt_builder import PromptBuilder
from llm.llm_factory import create_llm_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "inputs"
OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs"

def check_dependencies():
    if shutil.which("c2rust") is None:
        print("❌ [Error] 'c2rust' 명령어를 찾을 수 없습니다.")
        return False
    return True

def run_c2rust(c_file_path: Path) -> Path:
    """[Step 1] C2Rust를 안전하게 실행"""
    print(f"\n🚀 [Step 1] C2Rust 정적 변환 시작: {c_file_path.name}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    temp_c_file = OUTPUT_DIR / c_file_path.name
    shutil.copy2(c_file_path, temp_c_file)
    
    command = ["c2rust", "transpile", str(temp_c_file.name)]
    
    try:
        subprocess.run(
            command, 
            cwd=OUTPUT_DIR,
            capture_output=True, text=True, check=True
        )
        generated_rs_path = OUTPUT_DIR / temp_c_file.with_suffix('.rs').name
        temp_c_file.unlink(missing_ok=True)
        
        if generated_rs_path.exists():
            print(f"✅ [Step 1] 변환 성공! -> {generated_rs_path}")
            return generated_rs_path
        else:
            print("❌ [Error] 변환된 .rs 파일을 찾을 수 없습니다.")
            return None
            
    except subprocess.CalledProcessError as e:
        print("❌ [Error] C2Rust 변환 중 오류 발생:")
        print(e.stderr)
        return None

def main():
    print("="*50)
    print("🔥 Oxidizer Pipeline Engine 가동 준비")
    print("="*50)
    
    if not check_dependencies(): return

    target_c_file = INPUT_DIR / "test.c"
    if not target_c_file.exists():
        print(f"❌ [Error] 타겟 파일이 없습니다: {target_c_file}")
        return

    base_rs_file = run_c2rust(target_c_file)
    if not base_rs_file: return

    with open(base_rs_file, 'r', encoding='utf-8') as f:
        c2rust_code = f.read()

    print(f"\n🧠 [Step 2] 인간 통찰력(Human Insight) 프롬프트 조립 중...")
    # 💡 새로운 PromptBuilder 사용
    prompt_builder = PromptBuilder()
    messages = prompt_builder.build_messages(c2rust_code)

    print("🤖 [Step 3] LLM에게 관용적(Idiomatic) Safe Rust 변환을 요청하는 중...")
    # 💡 새로운 LLM 팩토리 사용
    llm_client = create_llm_client()
    safe_rust_code = llm_client.generate(messages)

    if safe_rust_code:
        final_rs_name = target_c_file.stem + "_safe.rs"
        final_rs_path = OUTPUT_DIR / final_rs_name
        with open(final_rs_path, 'w', encoding='utf-8') as f:
            f.write(safe_rust_code)
            
        print(f"\n✅ [Step 3] 변환 완료! Safe Rust 코드가 저장되었습니다 -> {final_rs_path}")

if __name__ == "__main__":
    main()
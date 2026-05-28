# src/utils/file_io.py
import os
import shutil
from pathlib import Path

class WorkspaceManager:
    """
    Cargo 프로젝트 스캐폴딩(Scaffolding) 및 코드의 상태(백업/롤백)를 관리합니다.
    """
    
    def __init__(self, base_output_dir: Path):
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    def setup_cargo_project(self, raw_rs_path: Path, project_name: str, is_bin: bool = True) -> Path:
        """
        C2Rust가 생성한 단일 .rs 파일을 Cargo 프로젝트 구조로 래핑합니다.
        :param raw_rs_path: 변환된 원본 .rs 파일 경로
        :param project_name: 생성할 프로젝트(폴더) 이름
        :param is_bin: 실행 파일(main.rs)인지 라이브러리(lib.rs)인지 여부
        :return: 생성된 Cargo 프로젝트의 루트 경로
        """
        project_dir = self.base_output_dir / f"WIP_{project_name}"
        src_dir = project_dir / "src"
        
        # 1. 기존 작업 공간이 있다면 초기화 (충돌 방지)
        if project_dir.exists():
            shutil.rmtree(project_dir)
        src_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Cargo.toml 생성 (libc 의존성 강제 주입)
        cargo_toml_content = f"""[package]
name = "{project_name}"
version = "0.1.0"
edition = "2021"

[dependencies]
libc = "0.2"
"""
        with open(project_dir / "Cargo.toml", "w", encoding="utf-8") as f:
            f.write(cargo_toml_content)
            
        # 3. 소스 코드를 src/ 내부로 이동 및 이름 변경
        target_file_name = "main.rs" if is_bin else "lib.rs"
        target_rs_path = src_dir / target_file_name
        shutil.copy2(raw_rs_path, target_rs_path)
        
        print(f"📦 [Scaffold] Cargo 프로젝트 세팅 완료: {project_dir}")
        return project_dir

    def backup_file(self, file_path: Path):
        """LLM이 코드를 수정하기 전, 안전하게 .old 확장자로 백업합니다."""
        if file_path.exists():
            backup_path = file_path.with_suffix(".rs.old")
            shutil.copy2(file_path, backup_path)

    def rollback_file(self, file_path: Path):
        """컴파일 피드백 루프가 최종 실패(예: 5회 초과) 시, 원본 코드로 되돌립니다."""
        backup_path = file_path.with_suffix(".rs.old")
        if backup_path.exists():
            shutil.copy2(backup_path, file_path)
            backup_path.unlink()  # 롤백 후 백업 찌꺼기 삭제
            print(f"🔄 [Rollback] 치명적 오류로 인해 {file_path.name} 파일이 원상 복구되었습니다.")

    def read_code(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_code(self, file_path: Path, code: str):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
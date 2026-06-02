# src/agent/orchestrator.py
import re
import shutil
import subprocess
import yaml
import time
import json
from pathlib import Path
from typing import Optional

from llm.llm_factory import create_llm_client
from prompter.prompt_builder import PromptBuilder
from agent.repair_agent import RepairAgent
from utils.cargo_runner import CargoRunner
from utils.test_runner import TestRunner
from utils.file_io import WorkspaceManager
from utils.logger import logger

from analyzer.dependency_graph import DependencyAnalyzer
from analyzer.skeleton_generator import SkeletonGenerator
from analyzer.c_semantic_extractor import CSemanticExtractor
from prompter.rag_retriever import RagRetriever

from evaluation.metrics import MetricsCollector
from utils.ui_renderer import UIRenderer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

class Orchestrator:
    """Oxidizer 하이브리드 파이프라인 사령탑."""
    
    def __init__(self, config_path: str = "config.yaml", llm_provider: str = None, llm_model: str = None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = self.project_root / self.config.get("paths", {}).get("data_dir", "data") / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.llm = create_llm_client(config_path, provider_override=llm_provider, model_override=llm_model)
        self.prompt_builder = PromptBuilder(config_path)
        self.repair_agent = RepairAgent(config_path, llm_provider=llm_provider, llm_model=llm_model)
        self.cargo_runner = CargoRunner(config_path)
        self.test_runner = TestRunner()
        self.workspace = WorkspaceManager(self.output_dir)
        
        self.skeleton_gen = SkeletonGenerator(config_path)
        self.c_extractor = CSemanticExtractor()
        self.rag_retriever = RagRetriever()
        self.metrics_collector = MetricsCollector()
        
        examples_path = self.project_root / "data" / "examples"
        examples_path.mkdir(parents=True, exist_ok=True)
        self.rag_retriever.seed_database(examples_path)

    def _run_c2rust(self, c_file: Path) -> Optional[Path]:
        temp_c_file = self.output_dir / c_file.name
        shutil.copy2(c_file, temp_c_file)
        try:
            subprocess.run(
                ["c2rust", "transpile", str(temp_c_file.name)],
                cwd=self.output_dir, capture_output=True, text=True, check=True
            )
            generated_rs_path = self.output_dir / temp_c_file.with_suffix('.rs').name
            temp_c_file.unlink(missing_ok=True)
            return generated_rs_path if generated_rs_path.exists() else None
        except subprocess.CalledProcessError:
            return None

    def _parse_llm_response(self, response_text: str) -> tuple[str, str]:
        refined = response_text.strip()
        plan, rust_code = "", ""
        
        plan_marker = "### 1. TRANSLATION PLAN"
        code_marker = "### 2. SAFE RUST CODE"
        
        plan_start = refined.find(plan_marker)
        code_start = refined.find(code_marker)
        
        if plan_start != -1:
            end_plan_idx = code_start if code_start != -1 else len(refined)
            plan = refined[plan_start + len(plan_marker):end_plan_idx].strip()
            
        target_text = refined[code_start:] if code_start != -1 else refined
        
        backticks = "`" * 3
        pattern = rf'{backticks}(?:rust)?\s*(.*?)\s*{backticks}'
        match = re.search(pattern, target_text, re.DOTALL)
        
        if match:
            rust_code = match.group(1).strip()
        else:
            if code_start != -1:
                rust_code = refined[code_start + len(code_marker):].strip()
            else:
                rust_code = refined
            rust_code = re.sub(rf'^{backticks}(?:rust)?\s*', '', rust_code, flags=re.IGNORECASE)
            rust_code = re.sub(rf'\s*{backticks}$', '', rust_code)
            rust_code = rust_code.strip()
                
        return plan, rust_code

    def run_pipeline(self, c_file: Path, input_data: str = None, expected_output: str = None, options: dict = None) -> bool:
        if options is None:
            options = {"use_skeleton": True, "use_dfg": True, "use_rag": True, "use_repair": True}

        from rich.status import Status
        from utils.ui_renderer import console

        console.print(f"\n[bold blue][~][/bold blue] Target C Source : [bold white]{c_file.name}[/bold white]")
        console.print(f"[bold blue][~][/bold blue] Engine Config   : [bold white]{self.llm.model_name}[/bold white]")
        console.print(f"[bold red][!][/bold red] Initializing Oxidizer Sequence...\n")
        
        with open(c_file, "r", encoding="utf-8") as f:
            c_code = f.read()
            
        start_time = time.time()
        final_rs_path = self.output_dir / c_file.with_suffix('.rs').name
        target_rs_path = None
        pipeline_success = False
        repair_attempts = 0
        
        # RustScan 스타일: 스피너가 돌다가 완료되면 로그가 남는 방식
        with Status("[bold cyan]Waking up modules...[/bold cyan]", spinner="bouncingBar", console=console) as status:
            
            # [Phase 1]
            status.update("[bold cyan][Phase 1][/bold cyan] Extracting AST Skeleton...")
            rust_skeleton_code = ""
            if options.get("use_skeleton", True):
                rust_skeleton_code = self.skeleton_gen.generate_rust_skeleton(c_file, c_code)
            console.print("[bold green][+][/bold green] [bold white]Phase 1[/bold white] : AST Skeleton extracted successfully.")
            
            # [Phase 2]
            status.update("[bold cyan][Phase 2][/bold cyan] Analyzing Semantic DFG & Pointers...")
            c_fingerprint = {}
            c_fingerprint_str = ""
            if options.get("use_dfg", True):
                c_fingerprint = self.c_extractor.extract_semantic_fingerprint(c_file, "main")
                c_fingerprint_str = self.c_extractor.format_for_prompt(c_fingerprint)
            console.print("[bold green][+][/bold green] [bold white]Phase 2[/bold white] : DFG fingerprints mapping completed.")
            
            # [Phase 3]
            status.update("[bold cyan][Phase 3][/bold cyan] Running C2Rust & Searching RAG database...")
            c2rust_rs_path = self._run_c2rust(c_file)
            c2rust_code = self.workspace.read_code(c2rust_rs_path) if c2rust_rs_path else ""
            rag_examples_str = ""
            if options.get("use_rag", True):
                retrieved_snippets = self.rag_retriever.retrieve_examples(c_fingerprint)
                rag_examples_str = self.rag_retriever.format_for_prompt(retrieved_snippets)
            console.print("[bold green][+][/bold green] [bold white]Phase 3[/bold white] : RAG idioms & context retrieved.")
            
            # [Phase 4]
            status.update("[bold magenta][Phase 4][/bold magenta] Synthesizing Prompts & LLM Generation (Standby...)")
            master_messages = self.prompt_builder.build_master_prompt(
                c_code=c_code,
                c2rust_code=c2rust_code,
                c_fingerprint_str=c_fingerprint_str,
                rag_examples_str=rag_examples_str,
                skeleton_code=rust_skeleton_code
            )
            llm_response = self.llm.generate(master_messages)
            plan, final_code = self._parse_llm_response(llm_response)
            self.workspace.write_code(final_rs_path, final_code)
            console.print("[bold green][+][/bold green] [bold white]Phase 4[/bold white] : Safe Rust generated by LLM.")
            
            # [Phase 5]
            status.update("[bold yellow][Phase 5][/bold yellow] Cargo compilation & Auto-Repair Agent running...")
            if options.get("use_repair", True):
                target_rs_path, repair_attempts = self.repair_agent.run(final_rs_path, c_file.stem, is_bin=True)
                if target_rs_path:
                    pipeline_success = True
            else:
                target_rs_path = final_rs_path
                pipeline_success = True
                
            console.print(f"[bold green][+][/bold green] [bold white]Phase 5[/bold white] : Auto-Repair loop finished. (Attempts: {repair_attempts})")
            time.sleep(0.5)

        # 결과 처리 및 지표 저장
        duration_sec = time.time() - start_time
        analysis_target_path = target_rs_path if target_rs_path else final_rs_path
        final_rust_code = self.workspace.read_code(analysis_target_path) if analysis_target_path.exists() else ""
        
        report = self.metrics_collector.generate_report(
            c_code=c_code,
            rust_code=final_rust_code,
            repair_attempts=repair_attempts,
            duration_sec=duration_sec,
            llm_model=self.llm.model_name
        )
        
        UIRenderer.render_dashboard(report, file_name=c_file.name)
        
        # 🔒 [개인정보 보호] 절대 경로를 프로젝트 기준 상대 경로로 변환
        try:
            display_target = analysis_target_path.relative_to(self.project_root)
        except ValueError:
            display_target = analysis_target_path.name
            
        metrics_file = self.output_dir / f"{c_file.stem}_metrics.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)
            
        try:
            display_metrics = metrics_file.relative_to(self.project_root)
        except ValueError:
            display_metrics = metrics_file.name
        
        # 깔끔하게 상대 경로로 출력
        if pipeline_success:
            console.print(f"[bold green]Open[/bold green] ./{display_target}")
        else:
            console.print(f"[bold red]Closed[/bold red] Repair failed. See logs.")
            
        console.print(f"[bold green]Open[/bold green] ./{display_metrics}\n")

        return pipeline_success
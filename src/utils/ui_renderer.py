# src/utils/ui_renderer.py
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# 프로젝트 전역에서 UI 출력을 담당할 콘솔 객체
console = Console()

class UIRenderer:
    """
    수집된 성과 지표(Metrics)를 바탕으로 터미널에 직관적이고 아름다운 대시보드와 배너를 렌더링합니다.
    """
    
    @staticmethod
    def print_banner():
        """강렬한 블록체 스타일의 해커 감성 아스키 아트 배너를 출력합니다."""
        banner = """[bold red]
 ██████╗ ██╗  ██╗██╗██████╗ ██╗███████╗███████╗██████╗ 
██╔═══██╗╚██╗██╔╝██║██╔══██╗██║╚══███╔╝██╔════╝██╔══██╗
██║   ██║ ╚███╔╝ ██║██║  ██║██║  ███╔╝ █████╗  ██████╔╝
██║   ██║ ██╔██╗ ██║██║  ██║██║ ███╔╝  ██╔══╝  ██╔══██╗
╚██████╔╝██╔╝ ██╗██║██████╔╝██║███████╗███████╗██║  ██║
 ╚═════╝ ╚═╝  ╚═╝╚═╝╚═════╝ ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝
[/bold red]
[bold green]The Autonomous C-to-Rust Transpilation Agent.[/bold green]

[bold yellow]------------------------------------------------------------[/bold yellow]
[bold cyan]: Mode    : Autonomous Agent Pipeline                      :[/bold cyan]
[bold cyan]: Feature : Semantic Lifting & Auto-Repair                 :[/bold cyan]
[bold yellow]------------------------------------------------------------[/bold yellow]

[bold white]C2Rust? More like unsafe-rust.[/bold white] 🐢
"""
        console.print(banner)

    @staticmethod
    def render_dashboard(metrics: dict, file_name: str):
        # 1. 테이블 뼈대 생성
        table = Table(show_header=True, header_style="bold magenta", expand=False)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", justify="right", style="bold white", width=25)
        
        # 1.5. LLM 엔진 지표 추가
        table.add_row("LLM Engine", f"[bold yellow]{metrics.get('llm_model', 'Unknown')}[/bold yellow]")
        table.add_section()
        
        # 2. 안전성 지표
        is_safe = metrics.get("is_fully_safe", False)
        safe_text = "[bold green]✅ 100% SAFE[/bold green]" if is_safe else "[bold red]⚠️ UNSAFE ELEMENTS REMAIN[/bold red]"
        
        table.add_row("Safety Status", safe_text)
        
        unsafe_blocks = metrics.get("unsafe_blocks", 0)
        raw_pointers = metrics.get("raw_mut_pointers", 0) + metrics.get("raw_const_pointers", 0)
        
        table.add_row("Remaining `unsafe` Blocks", f"[red]{unsafe_blocks}[/red]" if unsafe_blocks > 0 else "[green]0[/green]")
        table.add_row("Remaining Raw Pointers", f"[red]{raw_pointers}[/red]" if raw_pointers > 0 else "[green]0[/green]")
        
        table.add_section()
        
        # 3. 코드 라인 수
        table.add_row("Original C LOC", f"{metrics.get('c_loc', 0)} lines")
        table.add_row("Generated Rust LOC", f"{metrics.get('rust_loc', 0)} lines")
        table.add_row("Expansion Ratio (Rust/C)", f"{metrics.get('expansion_ratio', 0)}x")
        
        table.add_section()
        
        # 4. 파이프라인 수행 노력 지표
        attempts = metrics.get("repair_attempts", 0)
        attempt_style = "[green]" if attempts == 0 else ("[yellow]" if attempts < 3 else "[red]")
        table.add_row("Auto-Repair Attempts", f"{attempt_style}{attempts} times[/{attempt_style.strip('[ ]')}]")
        table.add_row("Execution Time", f"{metrics.get('duration_seconds', 0)} sec")
        
        # 5. 패널 렌더링
        border_color = "green" if is_safe else "red"
        panel = Panel(
            table, 
            title=f"📊 Oxidizer Final Metrics: [bold]{file_name}[/bold]", 
            border_style=border_color, 
            padding=(1, 2)
        )
        
        console.print("\n")
        console.print(panel)
        console.print("\n")
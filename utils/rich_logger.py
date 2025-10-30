# -*- coding: utf-8 -*-
"""
基于Rich的日志管理模块

提供美观的控制台输出和日志管理功能
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import contextmanager

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich.status import Status
from rich.live import Live
from rich.layout import Layout
from rich.align import Align
from rich.columns import Columns
from rich.rule import Rule
from rich import box
from rich.theme import Theme

# 自定义主题
PUBMINER_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "debug": "dim blue",
    "critical": "bold white on red",
    "highlight": "bold magenta",
    "path": "bold blue",
    "number": "bold cyan",
    "status": "bold yellow",
    "progress": "green",
})

class RichLogger:
    """基于Rich的日志管理器"""
    
    def __init__(
        self,
        name: str = "pubminer",
        level: int = logging.INFO,
        log_dir: Optional[Path] = None,
        console_width: Optional[int] = None,
        show_time: bool = True,
        show_path: bool = False
    ):
        """
        初始化Rich日志管理器
        
        Args:
            name: 日志器名称
            level: 日志级别
            log_dir: 日志文件目录
            console_width: 控制台宽度
            show_time: 是否显示时间
            show_path: 是否显示路径
        """
        self.name = name
        self.level = level
        self.log_dir = Path(log_dir) if log_dir else None
        
        # 创建Rich控制台
        self.console = Console(
            theme=PUBMINER_THEME,
            width=console_width,
            force_terminal=True,
            color_system="auto"
        )
        
        # 设置日志器
        self.logger = self._setup_logger(show_time, show_path)
        
        # 进度条管理
        self._progress_bars: Dict[str, Any] = {}
        self._current_progress = None
        
    def _setup_logger(self, show_time: bool, show_path: bool) -> logging.Logger:
        """设置日志器"""
        logger = logging.getLogger(self.name)
        logger.setLevel(self.level)
        logger.handlers.clear()
        
        # Rich控制台处理器
        rich_handler = RichHandler(
            console=self.console,
            show_time=show_time,
            show_path=show_path,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True
        )
        rich_handler.setLevel(self.level)
        logger.addHandler(rich_handler)
        
        # 文件处理器（如果指定了日志目录）
        if self.log_dir:
            self._setup_file_handlers(logger)
        
        return logger
    
    def _setup_file_handlers(self, logger: logging.Logger):
        """设置文件处理器"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 标准日志文件
        log_file = self.log_dir / f"pubminer_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(self.level)
        
        # 文件日志格式（不包含Rich标记）
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # 错误日志文件
        error_file = self.log_dir / f"pubminer_error_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = logging.FileHandler(error_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        logger.addHandler(error_handler)
    
    def info(self, message: str, **kwargs):
        """信息日志"""
        self.logger.info(f"[info]{message}[/info]", **kwargs)
    
    def warning(self, message: str, **kwargs):
        """警告日志"""
        self.logger.warning(f"[warning]{message}[/warning]", **kwargs)
    
    def error(self, message: str, **kwargs):
        """错误日志"""
        self.logger.error(f"[error]{message}[/error]", **kwargs)
    
    def success(self, message: str, **kwargs):
        """成功日志"""
        self.logger.info(f"[success]✅ {message}[/success]", **kwargs)
    
    def debug(self, message: str, **kwargs):
        """调试日志"""
        self.logger.debug(f"[debug]{message}[/debug]", **kwargs)
    
    def critical(self, message: str, **kwargs):
        """严重错误日志"""
        self.logger.critical(f"[critical]{message}[/critical]", **kwargs)
    
    def print_header(self, title: str, subtitle: str = None):
        """打印标题头部"""
        if subtitle:
            header_text = f"[bold cyan]{title}[/bold cyan]\n[dim]{subtitle}[/dim]"
        else:
            header_text = f"[bold cyan]{title}[/bold cyan]"
        
        panel = Panel(
            Align.center(header_text),
            box=box.DOUBLE,
            style="cyan",
            padding=(1, 2)
        )
        self.console.print(panel)
        self.console.print()
    
    def print_section(self, title: str):
        """打印章节分隔符"""
        self.console.print(Rule(f"[bold yellow]{title}[/bold yellow]", style="yellow"))
        self.console.print()
    
    def print_table(self, title: str, data: list, headers: list):
        """打印表格"""
        table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold magenta")
        
        for header in headers:
            table.add_column(header, style="cyan", no_wrap=False)
        
        for row in data:
            table.add_row(*[str(cell) for cell in row])
        
        self.console.print(table)
        self.console.print()
    
    def print_tree(self, title: str, tree_data: dict):
        """打印树形结构"""
        tree = Tree(f"[bold blue]{title}[/bold blue]")
        
        def add_items(parent, items):
            if isinstance(items, dict):
                for key, value in items.items():
                    if isinstance(value, (dict, list)):
                        branch = parent.add(f"[yellow]{key}[/yellow]")
                        add_items(branch, value)
                    else:
                        parent.add(f"[yellow]{key}[/yellow]: [cyan]{value}[/cyan]")
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, (dict, list)):
                        add_items(parent, item)
                    else:
                        parent.add(f"[cyan]{item}[/cyan]")
        
        add_items(tree, tree_data)
        self.console.print(tree)
        self.console.print()
    
    def print_status_panel(self, status_data: dict):
        """打印状态面板"""
        columns = []
        
        for key, value in status_data.items():
            if isinstance(value, dict):
                # 嵌套状态
                nested_text = "\n".join([f"[dim]{k}:[/dim] [cyan]{v}[/cyan]" for k, v in value.items()])
                panel = Panel(
                    nested_text,
                    title=f"[bold]{key}[/bold]",
                    border_style="blue",
                    padding=(0, 1)
                )
            else:
                # 简单状态
                panel = Panel(
                    f"[number]{value}[/number]",
                    title=f"[bold]{key}[/bold]",
                    border_style="green",
                    padding=(0, 1)
                )
            columns.append(panel)
        
        self.console.print(Columns(columns, equal=True, expand=True))
        self.console.print()
    
    @contextmanager
    def progress(self, description: str = "Processing..."):
        """进度条上下文管理器"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=False
        ) as progress:
            task = progress.add_task(description, total=None)
            self._current_progress = (progress, task)
            try:
                yield progress, task
            finally:
                self._current_progress = None
    
    @contextmanager
    def status(self, message: str):
        """状态指示器上下文管理器"""
        with Status(f"[status]{message}[/status]", console=self.console, spinner="dots") as status:
            yield status
    
    def update_progress(self, task_id, advance: int = 1, description: str = None):
        """更新进度条"""
        if self._current_progress:
            progress, _ = self._current_progress
            progress.update(task_id, advance=advance, description=description)
    
    def print_summary(self, title: str, summary_data: dict):
        """打印总结信息"""
        self.print_section(title)
        
        # 成功/失败统计
        if 'success' in summary_data and 'total' in summary_data:
            success = summary_data['success']
            total = summary_data['total']
            failed = total - success
            success_rate = (success / total * 100) if total > 0 else 0
            
            stats_table = Table(box=box.SIMPLE, show_header=False)
            stats_table.add_column("Metric", style="bold")
            stats_table.add_column("Value", style="number")
            
            stats_table.add_row("总数", str(total))
            stats_table.add_row("成功", f"[success]{success}[/success]")
            stats_table.add_row("失败", f"[error]{failed}[/error]")
            stats_table.add_row("成功率", f"[highlight]{success_rate:.1f}%[/highlight]")
            
            self.console.print(stats_table)
        
        # 其他统计信息
        if 'details' in summary_data:
            self.print_table("详细信息", summary_data['details'], ["项目", "值"])
    
    def print_error_details(self, error: Exception, context: str = None):
        """打印错误详情"""
        error_panel = Panel(
            f"[error]{type(error).__name__}: {str(error)}[/error]",
            title="[bold red]错误详情[/bold red]",
            border_style="red",
            padding=(1, 2)
        )
        
        if context:
            context_panel = Panel(
                f"[dim]{context}[/dim]",
                title="[bold yellow]错误上下文[/bold yellow]",
                border_style="yellow",
                padding=(1, 2)
            )
            self.console.print(context_panel)
        
        self.console.print(error_panel)
        self.console.print()

class RichLoggerMixin:
    """Rich日志混入类"""
    
    @property
    def rich_logger(self) -> RichLogger:
        """获取Rich日志器"""
        if not hasattr(self, '_rich_logger'):
            class_name = self.__class__.__name__
            self._rich_logger = get_rich_logger(f'pubminer.{class_name}')
        return self._rich_logger

# 全局Rich日志器实例
_rich_logger_instance: Optional[RichLogger] = None

def setup_rich_logger(
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
    console_width: Optional[int] = None,
    show_time: bool = True,
    show_path: bool = False
) -> RichLogger:
    """
    设置全局Rich日志器
    
    Args:
        level: 日志级别
        log_dir: 日志文件目录
        console_width: 控制台宽度
        show_time: 是否显示时间
        show_path: 是否显示路径
        
    Returns:
        RichLogger实例
    """
    global _rich_logger_instance
    _rich_logger_instance = RichLogger(
        level=level,
        log_dir=log_dir,
        console_width=console_width,
        show_time=show_time,
        show_path=show_path
    )
    return _rich_logger_instance

def get_rich_logger(name: str = "pubminer") -> RichLogger:
    """
    获取Rich日志器实例
    
    Args:
        name: 日志器名称
        
    Returns:
        RichLogger实例
    """
    global _rich_logger_instance
    if _rich_logger_instance is None:
        _rich_logger_instance = RichLogger(name=name)
    return _rich_logger_instance

# 便捷函数
def print_welcome():
    """打印欢迎信息"""
    logger = get_rich_logger()
    logger.print_header(
        "🔬 PubMiner - 智能文献分析工具",
        "基于大语言模型的模块化文献挖掘系统"
    )

def print_config_summary(config: dict):
    """打印配置摘要"""
    logger = get_rich_logger()
    logger.print_tree("📋 配置信息", config)

def print_results_summary(results: dict):
    """打印结果摘要"""
    logger = get_rich_logger()
    logger.print_summary("📊 执行结果", results)
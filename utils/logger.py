# -*- coding: utf-8 -*-
"""
日志管理模块

提供统一的日志配置和管理功能
"""

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(level: int = logging.INFO,
                 log_dir: Optional[Path] = None,
                 console: bool = True,
                 file_logging: bool = True) -> logging.Logger:
    """
    设置日志系统

    Args:
        level: 日志级别
        log_dir: 日志文件目录
        console: 是否输出到控制台
        file_logging: 是否输出到文件

    Returns:
        配置好的 logger
    """
    # 创建根 logger
    logger = logging.getLogger('pubminer')
    logger.setLevel(level)

    # 清除已有的处理器
    logger.handlers.clear()

    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # 控制台处理器
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件处理器
    if file_logging and log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # 按日期创建日志文件
        log_file = log_dir / f"pubminer_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 错误日志单独文件
        error_log_file = log_dir / f"pubminer_error_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

    return logger


def get_logger(name: str = 'pubminer') -> logging.Logger:
    """
    获取指定名称的 logger

    Args:
        name: logger 名称

    Returns:
        logger 实例
    """
    return logging.getLogger(name)


class LoggerMixin:
    """日志混入类，为其他类提供日志功能"""

    @property
    def logger(self):
        """获取 logger"""
        if not hasattr(self, '_logger'):
            class_name = self.__class__.__name__
            self._logger = get_logger(f'pubminer.{class_name}')
        return self._logger

# -*- coding: utf-8 -*-
"""
PubMiner核心功能模块
"""

# 延迟导入以避免依赖问题
def __getattr__(name):
    if name == 'ConfigManager':
        from .config_manager import ConfigManager
        return ConfigManager
    elif name == 'PubMedFetcher':
        from .pubmed_fetcher import PubMedFetcher
        return PubMedFetcher
    elif name == 'TextExtractor':
        from .text_extractor import TextExtractor
        return TextExtractor
    elif name == 'LLMAnalyzer':
        from .llm_analyzer import LLMAnalyzer
        return LLMAnalyzer
    elif name == 'DataProcessor':
        from .data_processor import DataProcessor
        return DataProcessor
    elif name == 'PDFDownloader':
        from .pdf_downloader import PDFDownloader
        return PDFDownloader
    elif name == 'SciHubDownloader':
        from .scihub_downloader import SciHubDownloader
        return SciHubDownloader
    else:
        raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    'ConfigManager',
    'PubMedFetcher', 
    'TextExtractor',
    'LLMAnalyzer',
    'DataProcessor',
    'PDFDownloader',
    'SciHubDownloader'
]
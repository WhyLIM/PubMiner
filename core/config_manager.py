# -*- coding: utf-8 -*-
"""
配置管理模块

基于新的模块化配置架构，提供统一的配置管理接口。
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from config.config_loader import get_config_loader

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器 - 基于新的模块化配置架构"""

    def __init__(self, config_dir: str = "config"):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = config_dir
        self.config_loader = get_config_loader(config_dir)
        self._config_cache = {}

        logger.info("✅ 使用新的模块化配置架构")

    def _get_config(self, config_name: str) -> Dict[str, Any]:
        """获取配置，使用缓存"""
        if config_name not in self._config_cache:
            self._config_cache[config_name] = self.config_loader.load_config(config_name)
        return self._config_cache[config_name]

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置（合并所有模块配置）"""
        return self.config_loader.load_all_configs()

    def get_pubmed_config(self) -> Dict[str, Any]:
        """获取 PubMed 配置"""
        pubmed_config = self._get_config('pubmed')
        pubmed_api = pubmed_config.get('pubmed_api', {})
        app_config = self._get_config('app')

        # 合并路径配置
        paths = app_config.get('paths', {})
        pubmed_api.update({
            'output_dir': paths.get('results_dir', './results'),
            'log_dir': paths.get('log_dir', './logs')
        })

        return pubmed_api

    def get_llm_config(self, provider: str) -> Dict[str, Any]:
        """获取指定 LLM 提供商的配置"""
        llm_config = self._get_config('llm')
        providers = llm_config.get('llm_providers', {})

        if provider not in providers:
            available = list(providers.keys())
            raise ValueError(f"不支持的 LLM 提供商：{provider}，可用提供商：{available}")

        return providers[provider]

    def get_extraction_config(self) -> Dict[str, Any]:
        """获取文本提取配置"""
        text_processing = self._get_config('text_processing')

        # 合并文本提取和提取配置
        extraction_config = text_processing.get('extraction', {}).copy()
        text_extraction_config = text_processing.get('text_extraction', {})
        extraction_config.update(text_extraction_config)

        return extraction_config

    def get_pdf_download_config(self) -> Dict[str, Any]:
        """获取 PDF 下载配置"""
        pdf_config = self._get_config('pdf')
        return pdf_config.get('pdf_downloader', {})

    def get_output_config(self) -> Dict[str, Any]:
        """获取输出配置"""
        output_config = self._get_config('output')
        csv_settings = output_config.get('csv_settings', {})
        export_settings = output_config.get('export_settings', {})

        # 合并输出配置
        merged_config = {**csv_settings, **export_settings}
        return merged_config

    def get_extraction_templates(self) -> Dict[str, Any]:
        """获取所有提取模板"""
        extraction_config = self._get_config('extraction_templates')
        return extraction_config.get('templates', {})

    def get_available_templates(self) -> Dict[str, Any]:
        """获取可用的提取模板（别名方法）"""
        return self.get_extraction_templates()

    def get_extraction_template(self, template_name: str) -> Dict[str, Any]:
        """获取指定的提取模板"""
        return self.config_loader.get_extraction_template(template_name)

    def load_custom_template(self, template_file: str) -> Dict[str, Any]:
        """加载自定义模板文件"""
        import json

        template_path = Path(template_file)
        if not template_path.exists():
            raise FileNotFoundError(f"自定义模板文件：{template_file} 不存在")

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                custom_template = json.load(f)
            logger.info(f"✅ 成功加载自定义模板：{template_file}")
            return custom_template
        except Exception as e:
            raise ValueError(f"加载自定义模板失败：{e}")

    def get_language_config(self) -> Dict[str, Any]:
        """获取语言配置"""
        processing_config = self._get_config('processing')
        return processing_config.get('language', {
            'default_output_language': 'English',
            'supported_languages': ['Chinese', 'English'],
            'language_mapping': {
                'zh': 'Chinese',
                'en': 'English'
            }
        })

    def get_default_language(self) -> str:
        """获取默认输出语言"""
        language_config = self.get_language_config()
        return language_config.get('default_output_language', 'English')

    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        language_config = self.get_language_config()
        return language_config.get('supported_languages', ['Chinese', 'English'])

    def normalize_language(self, language: str) -> str:
        """标准化语言名称"""
        language_config = self.get_language_config()
        language_mapping = language_config.get('language_mapping', {})

        # 直接匹配
        if language in self.get_supported_languages():
            return language

        # 通过映射匹配
        normalized = language_mapping.get(language.lower())
        if normalized and normalized in self.get_supported_languages():
            return normalized

        # 默认返回英文
        logger.warning(f"⚠️ 不支持的语言: {language}，使用默认语言: English")
        return self.get_default_language()

    def get_query_template(self, query_id: str) -> Dict[str, Any]:
        """获取查询模板"""
        return self.config_loader.get_query_template(query_id)

    def get_all_query_templates(self) -> List[Dict[str, Any]]:
        """获取所有查询模板"""
        return self.config_loader.get_all_query_templates()

    def validate_config(self) -> List[str]:
        """验证配置文件结构"""
        return self.config_loader.validate_config_structure()

    def clear_cache(self):
        """清除配置缓存"""
        self._config_cache.clear()
        self.config_loader.clear_cache()
        logger.info("配置缓存已清除")

    def get_config_status(self) -> Dict[str, Any]:
        """获取配置系统状态信息"""
        templates = self.get_extraction_templates()
        return {
            "config_dir": self.config_dir,
            "templates_count": len(templates),
            "cached_configs": list(self._config_cache.keys()),
            "validation_errors": self.validate_config()
        }

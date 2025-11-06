#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件加载器 - 支持新的模块化配置架构
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# 尝试导入 dotenv，如果不可用则跳过
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    logger.warning("python-dotenv 未安装，环境变量加载可能不完整")


class ConfigLoader:
    """新的配置文件加载器，支持模块化配置架构"""

    def __init__(self, config_dir: str = "config"):
        """
        初始化配置加载器

        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
        self._cache = {}

        # 尝试加载环境变量
        self._load_environment_variables()

    def _load_environment_variables(self):
        """加载环境变量文件"""
        if not DOTENV_AVAILABLE:
            return

        # 尝试多个可能的 .env 文件位置
        env_paths = [
            self.config_dir.parent / '.env',  # 项目根目录
            Path('.env'),  # 当前工作目录
            self.config_dir / '.env',  # 配置目录
        ]

        for env_path in env_paths:
            if env_path.exists():
                try:
                    load_dotenv(env_path, override=True)
                    logger.info(f"已加载环境变量文件: {env_path}")
                    break
                except Exception as e:
                    logger.warning(f"加载环境变量文件失败 {env_path}: {e}")
        else:
            logger.warning("未找到 .env 文件，环境变量可能未正确加载")

        # 配置文件映射
        self.config_files = {
            'app': 'core/app_config.json',
            'pubmed': 'core/pubmed_config.json',
            'llm': 'core/llm_config.json',
            'processing': 'core/processing_config.json',
            'extraction_templates': 'extraction/extraction_templates.json',
            'text_processing': 'extraction/text_processing_config.json',
            'query_templates': 'query/query_templates.json',
            'pdf': 'output/pdf_config.json',
            'output': 'output/output_config.json'
        }

    def load_config(self, config_name: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        加载指定配置文件

        Args:
            config_name: 配置名称
            use_cache: 是否使用缓存

        Returns:
            配置字典
        """
        if use_cache and config_name in self._cache:
            return self._cache[config_name]

        if config_name not in self.config_files:
            raise ValueError(f"Unknown config: {config_name}")

        config_path = self.config_dir / self.config_files[config_name]

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 处理环境变量替换
            config = self._resolve_env_vars(config)

            if use_cache:
                self._cache[config_name] = config

            logger.info(f"Loaded config: {config_name} from {config_path}")
            return config

        except Exception as e:
            logger.error(f"Failed to load config {config_name}: {e}")
            raise

    def load_all_configs(self) -> Dict[str, Any]:
        """
        加载所有配置文件

        Returns:
            所有配置的合并字典
        """
        all_configs = {}

        for config_name in self.config_files.keys():
            try:
                config = self.load_config(config_name)
                all_configs[config_name] = config
            except Exception as e:
                logger.warning(f"Failed to load config {config_name}: {e}")

        return all_configs

    def get_extraction_template(self, template_name: str) -> Dict[str, Any]:
        """
        获取指定的提取模板

        Args:
            template_name: 模板名称

        Returns:
            提取模板配置
        """
        extraction_config = self.load_config('extraction_templates')
        templates = extraction_config.get('templates', {})

        if template_name not in templates:
            raise ValueError(f"Extraction template not found: {template_name}")

        template = templates[template_name]

        # 处理模板继承
        if 'extends' in template:
            base_template = self.get_extraction_template(template['extends'])
            template = self._merge_templates(base_template, template)

        return template

    def get_query_template(self, query_id: str) -> Dict[str, Any]:
        """
        获取指定的查询模板

        Args:
            query_id: 查询ID

        Returns:
            查询模板配置
        """
        query_config = self.load_config('query_templates')
        query_tasks = query_config.get('query_tasks', [])

        for task in query_tasks:
            if task.get('id') == query_id:
                return task

        raise ValueError(f"Query template not found: {query_id}")

    def get_all_query_templates(self) -> List[Dict[str, Any]]:
        """
        获取所有查询模板

        Returns:
            查询模板列表
        """
        query_config = self.load_config('query_templates')
        return query_config.get('query_tasks', [])

    def _resolve_env_vars(self, config: Any) -> Any:
        """
        递归解析配置中的环境变量

        Args:
            config: 配置对象

        Returns:
            解析后的配置
        """
        if isinstance(config, dict):
            return {k: self._resolve_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._resolve_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith('${') and config.endswith('}'):
            env_var = config[2:-1]
            env_value = os.getenv(env_var)

            if env_value is not None:
                logger.debug(f"环境变量替换: {env_var} -> {env_value[:10]}{'...' if len(env_value) > 10 else ''}")
                return env_value
            else:
                logger.warning(f"环境变量未找到: {env_var}")
                return config
        else:
            return config

    def _merge_templates(self, base: Dict[str, Any], child: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并模板配置（支持继承）

        Args:
            base: 基础模板
            child: 子模板

        Returns:
            合并后的模板
        """
        merged = base.copy()

        for key, value in child.items():
            if key == 'extends':
                continue
            elif key == 'fields' and isinstance(value, dict) and isinstance(merged.get('fields'), dict):
                merged['fields'].update(value)
            else:
                merged[key] = value

        return merged

    def reload_config(self, config_name: str) -> Dict[str, Any]:
        """
        重新加载指定配置（清除缓存）

        Args:
            config_name: 配置名称

        Returns:
            重新加载的配置
        """
        if config_name in self._cache:
            del self._cache[config_name]

        return self.load_config(config_name, use_cache=True)

    def clear_cache(self):
        """清除所有配置缓存"""
        self._cache.clear()
        logger.info("Config cache cleared")

    def validate_config_structure(self) -> List[str]:
        """
        验证配置文件结构

        Returns:
            验证错误列表
        """
        errors = []

        # 检查配置文件是否存在
        for config_name, file_path in self.config_files.items():
            full_path = self.config_dir / file_path
            if not full_path.exists():
                errors.append(f"Missing config file: {file_path}")

        # 验证提取模板结构
        try:
            extraction_config = self.load_config('extraction_templates')
            templates = extraction_config.get('templates', {})

            for template_name, template in templates.items():
                if 'fields' not in template:
                    errors.append(f"Template '{template_name}' missing 'fields' section")

                # 检查必需字段
                required_fields = ['name', 'description', 'version', 'fields']
                for field in required_fields:
                    if field not in template:
                        errors.append(f"Template '{template_name}' missing required field: {field}")

        except Exception as e:
            errors.append(f"Failed to validate extraction templates: {e}")

        # 验证查询模板结构
        try:
            query_config = self.load_config('query_templates')
            query_tasks = query_config.get('query_tasks', [])

            for i, task in enumerate(query_tasks):
                if 'id' not in task:
                    errors.append(f"Query task {i} missing 'id' field")
                if 'query' not in task:
                    errors.append(f"Query task {i} missing 'query' field")

        except Exception as e:
            errors.append(f"Failed to validate query templates: {e}")

        return errors


# 全局配置加载器实例
_config_loader = None


def get_config_loader(config_dir: str = "config") -> ConfigLoader:
    """获取全局配置加载器实例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader


def load_config(config_name: str, config_dir: str = "config") -> Dict[str, Any]:
    """便捷函数：加载指定配置"""
    return get_config_loader(config_dir).load_config(config_name)


def get_extraction_template(template_name: str, config_dir: str = "config") -> Dict[str, Any]:
    """便捷函数：获取提取模板"""
    return get_config_loader(config_dir).get_extraction_template(template_name)


def get_query_template(query_id: str, config_dir: str = "config") -> Dict[str, Any]:
    """便捷函数：获取查询模板"""
    return get_config_loader(config_dir).get_query_template(query_id)
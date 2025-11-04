# -*- coding: utf-8 -*-
"""
配置管理模块

管理各种 API 配置、提取模板配置、输出格式配置等。
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "config/default_config.json"):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config = self._load_config()
        self.templates = self._load_templates()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载主配置文件"""
        # 加载环境变量
        load_dotenv()
        
        if not self.config_file.exists():
            logger.warning(f"配置文件：{self.config_file} 不存在，使用默认配置")
            return self._get_default_config()
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_text = f.read()
            
            # 替换环境变量占位符
            config_text = self._replace_env_variables(config_text)
            
            # 解析JSON
            config = json.loads(config_text)
            logger.info(f"✅ 成功加载配置文件：{self.config_file}")
            return config
        except Exception as e:
            logger.error(f"❌ 加载配置文件失败：{e}")
            return self._get_default_config()
    
    def _replace_env_variables(self, text: str) -> str:
        """替换配置文件中的环境变量占位符"""
        def replace_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                logger.warning(f"⚠️ 环境变量 {var_name} 未设置，使用空字符串")
                return ''
            return env_value
        
        # 替换 ${VAR_NAME} 格式的占位符（不添加额外引号，因为JSON中已有）
        return re.sub(r'\$\{([^}]+)\}', replace_var, text)
    
    def _load_templates(self) -> Dict[str, Any]:
        """Load extraction templates"""
        template_file = Path("config/extraction_templates.json")
        if not template_file.exists():
            logger.warning(f"模板文件：{template_file} 不存在，使用默认模板")
            return self._get_default_templates()
            
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                templates = json.load(f)
            logger.info(f"✅ 成功加载模板文件：{template_file}")
            return templates
        except Exception as e:
            logger.error(f"❌ 加载模板文件失败：{e}")
            return self._get_default_templates()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "pubmed": {
                "email": "",
                "api_key": "",
                "batch_size": 50,
                "max_retries": 5,
                "retry_wait_time": 5,
                "api_wait_time": 0.5
            },
            "llm_providers": {
                "deepseek": {
                    "api_base": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
                    "temperature": 0.1,
                    "max_tokens": 4000
                },
                "openai": {
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "",
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.1,
                    "max_tokens": 4000
                },
                "qwen": {
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": "",
                    "model": "qwen-turbo",
                    "temperature": 0.1,
                    "max_tokens": 4000
                },
                "volcengine": {
                    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
                    "api_key": "",
                    "model": "ep-20241013000000-xxxxx",
                    "temperature": 0.1,
                    "max_tokens": 4000
                }
            },
            "extraction": {
                "text_limit": -1,
                "section_filters": ["abstract", "introduction", "methods", "results", "discussion", "conclusion"],
                "exclude_sections": ["references", "acknowledgments", "funding", "figures", "tables"]
            },
            "output": {
                "csv_encoding": "utf-8-sig",
                "date_format": "%Y-%m-%d",
                "na_values": ["NA", "N/A", "Not mentioned", ""]
            }
        }
    
    def _get_default_templates(self) -> Dict[str, Any]:
        """获取默认提取模板"""
        return {
            "standard": {
                "name": "Standard Medical Literature Information Extraction",
                "description": "Extract standard structured information from medical literature",
                "fields": {
                    "research_background": {
                        "name": "Research Background",
                        "description": "Background, motivation and significance of the research",
                        "csv_header": "Research_Background"
                    },
                    "theoretical_framework": {
                        "name": "Theoretical Framework",
                        "description": "Theoretical framework or model used",
                        "csv_header": "Theoretical_Framework"
                    },
                    "existing_research": {
                        "name": "Existing Research",
                        "description": "Existing research achievements and their shortcomings",
                        "csv_header": "Existing_Research"
                    },
                    "research_objectives": {
                        "name": "Research Objectives",
                        "description": "Clear research objectives",
                        "csv_header": "Research_Objectives"
                    },
                    "research_questions": {
                        "name": "Research Questions",
                        "description": "Research questions or hypotheses",
                        "csv_header": "Research_Questions"
                    },
                    "sample_size": {
                        "name": "Sample Size",
                        "description": "Number of research samples",
                        "csv_header": "Sample_Size"
                    },
                    "study_region": {
                        "name": "Study Region",
                        "description": "Research location or region",
                        "csv_header": "Study_Region"
                    },
                    "methods_tools": {
                        "name": "Methods and Tools",
                        "description": "Methods, tools, statistical models or software used",
                        "csv_header": "Methods_Tools"
                    },
                    "key_findings": {
                        "name": "Key Findings",
                        "description": "Main research findings and conclusions",
                        "csv_header": "Key_Findings"
                    },
                    "limitations": {
                        "name": "Research Limitations",
                        "description": "Limitations and shortcomings of the research",
                        "csv_header": "Limitations"
                    }
                }
            },
            "custom_template_example": {
                "name": "Custom Template Example - Aging Biomarkers Research",
                "description": "A detailed custom template example for aging biomarkers research. Users can reference this format to create their own extraction templates",
                "fields": {
                    "biomarker_type": {
                        "name": "Biomarker Type",
                        "description": "What biomarkers are studied in the research",
                        "csv_header": "Biomarker_Type"
                    },
                    "biomarker_category": {
                        "name": "Biomarker Category",
                        "description": "Single biomarker or combined biomarkers",
                        "csv_header": "Biomarker_Category"
                    },
                    "molecular_type": {
                        "name": "Molecular Type",
                        "description": "What category (Protein/DNA/RNA/Metabolite etc.)",
                        "csv_header": "Molecular_Type"
                    },
                    "population_ethnicity": {
                        "name": "Population Ethnicity",
                        "description": "Ethnic background of study population",
                        "csv_header": "Population_Ethnicity"
                    },
                    "gender_ratio": {
                        "name": "Gender Ratio",
                        "description": "Male-female ratio of study samples",
                        "csv_header": "Gender_Ratio"
                    },
                    "age_range": {
                        "name": "Age Range",
                        "description": "Age range of study subjects",
                        "csv_header": "Age_Range"
                    },
                    "biomarker_description": {
                        "name": "Biomarker Description",
                        "description": "Specific description and function of the biomarkers",
                        "csv_header": "Biomarker_Description"
                    },
                    "detection_method": {
                        "name": "Detection Method",
                        "description": "Detection methods and techniques for biomarkers",
                        "csv_header": "Detection_Method"
                    },
                    "clinical_application": {
                        "name": "Clinical Application",
                        "description": "Clinical application value of biomarkers",
                        "csv_header": "Clinical_Application"
                    }
                }
            }
        }
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self.config
    
    def get_pubmed_config(self) -> Dict[str, Any]:
        """获取 PubMed 配置"""
        pubmed_config = self.config.get("pubmed", {}).copy()
        
        # 从环境变量读取邮箱和API密钥
        if not pubmed_config.get("email"):
            pubmed_config["email"] = os.getenv("PUBMED_EMAIL", "")
        if not pubmed_config.get("api_key"):
            pubmed_config["api_key"] = os.getenv("PUBMED_API_KEY", "")
            
        return pubmed_config
    
    def get_llm_config(self, provider: str) -> Dict[str, Any]:
        """获取指定 LLM 提供商的配置"""
        providers_config = self.config.get("llm_providers", {})
        if provider not in providers_config:
            raise ValueError(f"不支持的 LLM 提供商：{provider}")
        return providers_config[provider]
    
    def get_extraction_config(self) -> Dict[str, Any]:
        """获取文本提取配置"""
        # 合并 text_extraction 和 extraction 配置
        extraction_config = self.config.get("extraction", {}).copy()
        text_extraction_config = self.config.get("text_extraction", {})
        extraction_config.update(text_extraction_config)
        return extraction_config
    
    def get_pdf_download_config(self) -> Dict[str, Any]:
        """获取PDF下载配置"""
        return self.config.get('pdf_downloader', {
            'download_dir': './downloads/pdfs',
            'max_retries': 3,
            'retry_delay': 5,
            'timeout': 30,
            'max_workers': 4,
            'verify_pdf': True,
            'max_file_size': 104857600,
            'scihub_mirrors': [
                "https://sci-hub.se",
                "https://sci-hub.st",
                "https://sci-hub.ru"
            ],
            'user_agents': [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ],
            'doi_apis': {
                'crossref': {
                    'url': 'https://api.crossref.org/works',
                    'enabled': True,
                    'timeout': 15
                }
            }
        })
    
    def get_output_config(self) -> Dict[str, Any]:
        """获取输出配置"""
        return self.config.get("output", {})
    
    def get_extraction_templates(self) -> Dict[str, Any]:
        """
        获取提取模板
        
        Returns:
            Dict[str, Any]: 抽取模板词典
        """
        return self.templates
    
    def get_available_templates(self) -> Dict[str, Any]:
        """
        获取可用的提取模板（别名方法）
        
        Returns:
            Dict[str, Any]: 抽取模板词典
        """
        return self.templates
    
    def get_extraction_template(self, template_name: str) -> Dict[str, Any]:
        """
        获取指定的提取模板
        
        Args:
            template_name: 模板名称
            
        Returns:
            Dict[str, Any]: 模板配置，若不存在则为 None
        """
        if template_name not in self.templates:
            available = list(self.templates.keys())
            raise ValueError(f"未找到模板：{template_name}，可用模板：{available}")
        return self.templates[template_name]
    
    def load_custom_template(self, template_file: str) -> Dict[str, Any]:
        """加载自定义模板文件"""
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
    
    def set_api_key(self, provider: str, api_key: str):
        """Set API key"""
        if provider == "pubmed":
            self.config["pubmed"]["api_key"] = api_key
        elif provider in self.config["llm_providers"]:
            self.config["llm_providers"][provider]["api_key"] = api_key
        else:
            raise ValueError(f"未知的提供商：{provider}")
    
    def set_model(self, provider: str, model: str):
        """Set model name"""
        if provider in self.config["llm_providers"]:
            self.config["llm_providers"][provider]["model"] = model
        else:
            raise ValueError(f"未知的 LLM 提供商：{provider}")
    
    def validate_config(self) -> bool:
        """Validate configuration validity"""
        try:
            # Check required configuration sections
            required_sections = ["pubmed", "llm_providers", "extraction", "output"]
            for section in required_sections:
                if section not in self.config:
                    logger.error(f"缺少必需的配置部分：{section}")
                    return False
            
            # Check LLM provider configuration
            for provider, config in self.config["llm_providers"].items():
                required_fields = ["api_base", "model"]
                for field in required_fields:
                    if field not in config:
                        logger.error(f"LLM 提供商 {provider} 缺少必要的配置：{field}")
                        return False
            
            logger.info("✅ 配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ 配置验证失败：{e}")
            return False
    
    def save_config(self, config_file: Optional[str] = None):
        """将配置保存到文件中"""
        if config_file is None:
            config_file = self.config_file
        else:
            config_file = Path(config_file)
            
        try:
            # 确保目录存在
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ 配置已保存至：{config_file}")
            
        except Exception as e:
            logger.error(f"❌ 保存配置失败：{e}")
            raise
    
    def get_language_config(self) -> Dict[str, Any]:
        """
        获取语言配置
        
        Returns:
            语言配置字典
        """
        return self.config.get('language', {
            'default_output_language': 'English',
            'supported_languages': ['Chinese', 'English'],
            'language_mapping': {'zh': 'Chinese', 'en': 'English'}
        })
    
    def get_default_language(self) -> str:
        """
        获取默认输出语言
        
        Returns:
            默认语言名称
        """
        language_config = self.get_language_config()
        return language_config.get('default_output_language', 'English')
    
    def get_supported_languages(self) -> List[str]:
        """
        获取支持的语言列表
        
        Returns:
            支持的语言列表
        """
        language_config = self.get_language_config()
        return language_config.get('supported_languages', ['Chinese', 'English'])
    
    def normalize_language(self, language: str) -> str:
        """
        标准化语言名称
        
        Args:
            language: 输入的语言名称或代码
            
        Returns:
            标准化的语言名称
        """
        language_config = self.get_language_config()
        language_mapping = language_config.get('language_mapping', {})
        
        # 直接匹配
        if language in self.get_supported_languages():
            return language
        
        # 通过映射匹配
        normalized = language_mapping.get(language.lower())
        if normalized and normalized in self.get_supported_languages():
            return normalized
        
        # 默认返回中文
        logger.warning(f"⚠️ 不支持的语言: {language}，使用默认语言: English")
        return self.get_default_language()
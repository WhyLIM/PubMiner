# -*- coding: utf-8 -*-
"""
自定义信息提取器

支持用户自定义提取模板和字段的灵活提取器
"""

from typing import Dict, List, Any, Optional
import logging
from pathlib import Path

from .base_extractor import BaseExtractor
from core.llm_analyzer import LLMAnalyzer
from core.config_manager import ConfigManager
from utils.file_handler import FileHandler

logger = logging.getLogger(__name__)

class CustomExtractor(BaseExtractor):
    """自定义信息提取器"""
    
    def __init__(self, config: Dict[str, Any], 
                 template_name: str = 'aging_biomarker',
                 template_path: Optional[str] = None,
                 llm_provider: str = 'deepseek'):
        """
        初始化自定义提取器
        
        Args:
            config: 提取器配置
            template_name: 模板名称
            template_path: 自定义模板文件路径
            llm_provider: LLM提供商
        """
        super().__init__(config)
        
        self.template_name = template_name
        self.template_path = template_path
        self.llm_provider = llm_provider
        self.config_manager = ConfigManager()
        self.custom_template = None
        
        # 加载自定义模板
        self._load_custom_template()
        
        # 初始化LLM分析器
        llm_config = self.config_manager.get_llm_config(llm_provider)
        if llm_config:
            self.llm_analyzer = LLMAnalyzer(llm_config)
            self.logger.info(f"✅ 初始化LLM分析器: {llm_provider}")
        else:
            self.llm_analyzer = None
            self.logger.error(f"❌ 无法获取LLM配置: {llm_provider}")
    
    def _load_custom_template(self):
        """加载自定义模板"""
        try:
            if self.template_path:
                # 从文件加载模板
                template_file = Path(self.template_path)
                if template_file.exists():
                    self.custom_template = FileHandler.load_json(template_file)
                    self.logger.info(f"✅ 从文件加载自定义模板: {template_file}")
                else:
                    self.logger.error(f"❌ 自定义模板文件不存在: {template_file}")
            else:
                # 从配置加载模板
                templates = self.config_manager.get_extraction_templates()
                if self.template_name in templates:
                    self.custom_template = templates[self.template_name]
                    self.logger.info(f"✅ 加载预置模板: {self.template_name}")
                else:
                    self.logger.error(f"❌ 模板不存在: {self.template_name}")
                    
        except Exception as e:
            self.logger.error(f"❌ 加载自定义模板失败: {e}")
            self.custom_template = None
    
    def get_template(self) -> Dict[str, Any]:
        """
        获取自定义提取模板
        
        Returns:
            自定义提取模板
        """
        if self.custom_template:
            return self.custom_template
        else:
            # 返回空模板
            return {
                'name': 'Empty Template',
                'description': '空模板',
                'version': '1.0',
                'fields': {}
            }
    
    def validate_template(self, template: Dict[str, Any]) -> bool:
        """
        验证模板格式
        
        Args:
            template: 提取模板
            
        Returns:
            是否有效
        """
        required_keys = ['name', 'description', 'fields']
        
        for key in required_keys:
            if key not in template:
                self.logger.error(f"模板缺少必需字段: {key}")
                return False
        
        fields = template.get('fields', {})
        if not isinstance(fields, dict):
            self.logger.error("模板字段必须是字典格式")
            return False
        
        if not fields:
            self.logger.warning("模板没有定义任何字段")
            return True  # 允许空字段模板
        
        # 验证字段格式
        for field_key, field_info in fields.items():
            if not isinstance(field_info, dict):
                self.logger.error(f"字段 {field_key} 必须是字典格式")
                return False
            
            required_field_keys = ['name', 'csv_header']
            for field_attr in required_field_keys:
                if field_attr not in field_info:
                    self.logger.error(f"字段 {field_key} 缺少必需属性: {field_attr}")
                    return False
        
        return True
    
    def _extract_info(self, text: str, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM提取自定义信息
        
        Args:
            text: 预处理后的文本
            template: 提取模板
            
        Returns:
            提取的信息字典
        """
        if not self.llm_analyzer:
            self.logger.error("LLM分析器未初始化，无法提取信息")
            return {}
        
        if not text:
            self.logger.warning("文本为空，跳过提取")
            return {}
        
        try:
            # 构建临时文献记录
            temp_paper = {
                'full_text': text,
                'PMID': 'temp'
            }
            
            # 使用LLM分析器提取信息
            result = self.llm_analyzer.analyze_single_paper(temp_paper, template)
            
            # 过滤掉临时字段
            extracted_info = {}
            fields = template.get('fields', {})
            
            for field_key in fields.keys():
                if field_key in result:
                    extracted_info[field_key] = result[field_key]
            
            return extracted_info
            
        except Exception as e:
            self.logger.error(f"LLM信息提取失败: {e}")
            return {}
    
    def create_template_from_fields(self, field_definitions: List[Dict[str, Any]], 
                                  template_name: str = "Custom Template",
                                  template_description: str = "用户自定义模板") -> Dict[str, Any]:
        """
        从字段定义创建模板
        
        Args:
            field_definitions: 字段定义列表
            template_name: 模板名称
            template_description: 模板描述
            
        Returns:
            创建的模板
        """
        template = {
            'name': template_name,
            'description': template_description,
            'version': '1.0',
            'fields': {}
        }
        
        for field_def in field_definitions:
            field_key = field_def.get('key', '')
            if not field_key:
                continue
            
            template['fields'][field_key] = {
                'name': field_def.get('name', field_key),
                'description': field_def.get('description', ''),
                'csv_header': field_def.get('csv_header', field_key),
                'prompt_hint': field_def.get('prompt_hint', ''),
                'required': field_def.get('required', False)
            }
        
        self.custom_template = template
        self.logger.info(f"✅ 创建自定义模板: {template_name}，包含 {len(template['fields'])} 个字段")
        
        return template
    
    def save_template(self, output_path: Path) -> bool:
        """
        保存当前模板到文件
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否保存成功
        """
        if not self.custom_template:
            self.logger.error("没有可保存的模板")
            return False
        
        try:
            FileHandler.save_json(self.custom_template, output_path)
            self.logger.info(f"✅ 模板已保存: {output_path}")
            return True
        except Exception as e:
            self.logger.error(f"❌ 保存模板失败: {e}")
            return False
    
    def load_template_from_file(self, template_path: Path) -> bool:
        """
        从文件加载模板
        
        Args:
            template_path: 模板文件路径
            
        Returns:
            是否加载成功
        """
        try:
            if not template_path.exists():
                self.logger.error(f"模板文件不存在: {template_path}")
                return False
            
            template = FileHandler.load_json(template_path)
            
            if self.validate_template(template):
                self.custom_template = template
                self.logger.info(f"✅ 从文件加载模板成功: {template_path}")
                return True
            else:
                self.logger.error(f"模板格式验证失败: {template_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 加载模板文件失败: {e}")
            return False
    
    def extract_batch(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量提取信息（优化版本）
        
        Args:
            papers: 文献列表
            
        Returns:
            包含提取信息的文献列表
        """
        if not self.llm_analyzer:
            self.logger.error("LLM分析器未初始化，无法批量提取")
            return papers
        
        template = self.get_template()
        if not self.validate_template(template):
            self.logger.error("提取模板验证失败")
            return papers
        
        self.logger.info(f"🔍 使用自定义提取器批量提取信息，共 {len(papers)} 篇文献")
        self.logger.info(f"模板: {template.get('name', 'Unknown')}")
        
        # 过滤有全文的文献
        papers_with_text = [p for p in papers if p.get('full_text')]
        papers_without_text = [p for p in papers if not p.get('full_text')]
        
        if papers_without_text:
            self.logger.warning(f"⚠️ {len(papers_without_text)} 篇文献没有全文，将跳过提取")
        
        if not papers_with_text:
            self.logger.warning("没有可提取的文献（缺少全文）")
            return papers
        
        # 使用LLM分析器批量处理
        batch_config = self.config.get('processing', {})
        batch_size = batch_config.get('batch_size', 10)
        max_workers = batch_config.get('max_workers', 4)
        
        results = self.llm_analyzer.analyze_batch(
            papers_with_text, 
            template,
            batch_size=batch_size,
            max_workers=max_workers
        )
        
        # 合并结果（包括没有全文的文献）
        all_results = results + papers_without_text
        
        # 按原始顺序排序
        ordered_results = []
        for original_paper in papers:
            pmid = original_paper.get('PMID', '')
            
            # 查找对应的结果
            found = False
            for result_paper in all_results:
                if result_paper.get('PMID', '') == pmid:
                    ordered_results.append(result_paper)
                    found = True
                    break
            
            if not found:
                ordered_results.append(original_paper)
        
        successful = len([r for r in ordered_results if r.get('extraction_status') == 'success'])
        self.logger.info(f"✅ 自定义提取完成: {successful}/{len(papers)} 篇成功")
        
        return ordered_results
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取提取统计信息
        
        Returns:
            统计信息字典
        """
        base_stats = {
            'extractor_type': 'CustomExtractor',
            'template_name': self.template_name,
            'llm_provider': self.llm_provider,
            'template_loaded': self.custom_template is not None
        }
        
        if self.custom_template:
            base_stats['template_info'] = {
                'name': self.custom_template.get('name', 'Unknown'),
                'description': self.custom_template.get('description', ''),
                'fields_count': len(self.custom_template.get('fields', {}))
            }
        
        if self.llm_analyzer:
            llm_stats = self.llm_analyzer.get_statistics()
            base_stats.update(llm_stats)
        else:
            base_stats['status'] = 'not_initialized'
        
        return base_stats
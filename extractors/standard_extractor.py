# -*- coding: utf-8 -*-
"""
标准信息提取器

使用大语言模型提取标准的医学文献结构化信息
"""

from typing import Dict, List, Any, Optional
import logging

from .base_extractor import BaseExtractor
from core.llm_analyzer import LLMAnalyzer
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class StandardExtractor(BaseExtractor):
    """标准信息提取器"""
    
    def __init__(self, config: Dict[str, Any], llm_provider: str = 'deepseek'):
        """
        初始化标准提取器
        
        Args:
            config: 提取器配置
            llm_provider: LLM提供商
        """
        super().__init__(config)
        
        self.llm_provider = llm_provider
        self.config_manager = ConfigManager()
        self.template_name = 'standard'
        
        # 初始化LLM分析器
        llm_config = self.config_manager.get_llm_config(llm_provider)
        if llm_config:
            self.llm_analyzer = LLMAnalyzer(llm_config)
            self.logger.info(f"✅ 初始化LLM分析器: {llm_provider}")
        else:
            self.llm_analyzer = None
            self.logger.error(f"❌ 无法获取LLM配置: {llm_provider}")
    
    def get_template(self) -> Dict[str, Any]:
        """
        获取标准提取模板
        
        Returns:
            标准提取模板
        """
        templates = self.config_manager.get_extraction_templates()
        return templates.get(self.template_name, {})
    
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
        if not isinstance(fields, dict) or not fields:
            self.logger.error("模板字段格式错误或为空")
            return False
        
        # 验证字段格式
        for field_key, field_info in fields.items():
            required_field_keys = ['name', 'csv_header']
            for field_attr in required_field_keys:
                if field_attr not in field_info:
                    self.logger.error(f"字段 {field_key} 缺少必需属性: {field_attr}")
                    return False
        
        return True
    
    def _extract_info(self, text: str, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM提取信息
        
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
        
        self.logger.info(f"🔍 使用标准提取器批量提取信息，共 {len(papers)} 篇文献")
        
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
        self.logger.info(f"✅ 标准提取完成: {successful}/{len(papers)} 篇成功")
        
        return ordered_results
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取提取统计信息
        
        Returns:
            统计信息字典
        """
        if self.llm_analyzer:
            llm_stats = self.llm_analyzer.get_statistics()
            return {
                'extractor_type': 'StandardExtractor',
                'template_name': self.template_name,
                'llm_provider': self.llm_provider,
                **llm_stats
            }
        else:
            return {
                'extractor_type': 'StandardExtractor',
                'template_name': self.template_name,
                'llm_provider': self.llm_provider,
                'status': 'not_initialized'
            }
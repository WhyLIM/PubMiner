# -*- coding: utf-8 -*-
"""
基础信息提取器

定义信息提取的基础接口和通用功能
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging

from utils.logger import LoggerMixin

logger = logging.getLogger(__name__)

class BaseExtractor(LoggerMixin, ABC):
    """基础信息提取器抽象类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化基础提取器
        
        Args:
            config: 提取器配置
        """
        self.config = config
        self.name = self.__class__.__name__
        self.logger.info(f"初始化提取器: {self.name}")
    
    @abstractmethod
    def get_template(self) -> Dict[str, Any]:
        """
        获取提取模板
        
        Returns:
            提取模板字典
        """
        pass
    
    @abstractmethod
    def validate_template(self, template: Dict[str, Any]) -> bool:
        """
        验证模板格式
        
        Args:
            template: 提取模板
            
        Returns:
            是否有效
        """
        pass
    
    def preprocess_text(self, text: str) -> str:
        """
        预处理文本
        
        Args:
            text: 原始文本
            
        Returns:
            预处理后的文本
        """
        if not text:
            return ""
        
        # 基础清理
        text = text.strip()
        
        # 移除多余的空白字符
        import re
        text = re.sub(r'\s+', ' ', text)
        
        return text
    
    def postprocess_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        后处理提取结果
        
        Args:
            result: 原始提取结果
            
        Returns:
            后处理后的结果
        """
        processed_result = {}
        
        for key, value in result.items():
            if isinstance(value, str):
                # 清理字符串值
                value = value.strip()
                if value.lower() in ['na', 'n/a', 'null', 'none', '']:
                    value = '未提及'
            
            processed_result[key] = value
        
        return processed_result
    
    def extract_from_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """
        从单篇文献中提取信息
        
        Args:
            paper: 文献记录
            
        Returns:
            包含提取信息的文献记录
        """
        template = self.get_template()
        
        if not self.validate_template(template):
            self.logger.error(f"提取模板验证失败: {self.name}")
            return paper
        
        # 预处理文本
        full_text = paper.get('full_text', '')
        if full_text:
            full_text = self.preprocess_text(full_text)
        
        # 执行具体的提取逻辑（由子类实现）
        extracted_info = self._extract_info(full_text, template)
        
        # 后处理结果
        extracted_info = self.postprocess_result(extracted_info)
        
        # 合并结果
        result = paper.copy()
        result.update(extracted_info)
        
        return result
    
    @abstractmethod
    def _extract_info(self, text: str, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行具体的信息提取逻辑
        
        Args:
            text: 预处理后的文本
            template: 提取模板
            
        Returns:
            提取的信息字典
        """
        pass
    
    def extract_batch(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量提取信息
        
        Args:
            papers: 文献列表
            
        Returns:
            包含提取信息的文献列表
        """
        self.logger.info(f"🔍 使用 {self.name} 批量提取信息，共 {len(papers)} 篇文献")
        
        results = []
        for i, paper in enumerate(papers, 1):
            self.logger.debug(f"处理第 {i}/{len(papers)} 篇文献...")
            
            try:
                result = self.extract_from_paper(paper)
                results.append(result)
            except Exception as e:
                pmid = paper.get('PMID', 'Unknown')
                self.logger.error(f"❌ 提取文献 {pmid} 信息失败: {e}")
                
                # 添加错误记录
                error_result = paper.copy()
                error_result['extraction_error'] = str(e)
                results.append(error_result)
        
        successful = len([r for r in results if 'extraction_error' not in r])
        self.logger.info(f"✅ 批量提取完成: {successful}/{len(papers)} 篇成功")
        
        return results
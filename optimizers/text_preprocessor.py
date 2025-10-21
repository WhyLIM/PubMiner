# -*- coding: utf-8 -*-
"""
文本预处理器

负责文本清理、格式化和优化，为后续处理做准备
"""

import re
from typing import Dict, List, Any, Optional, Tuple
import logging

from utils.logger import LoggerMixin

logger = logging.getLogger(__name__)

class TextPreprocessor(LoggerMixin):
    """文本预处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化文本预处理器
        
        Args:
            config: 预处理配置
        """
        self.config = config
        self.min_section_length = config.get('min_section_length', 100)
        self.max_section_length = config.get('max_section_length', 3000)
        self.compression_ratio = config.get('compression_ratio', 0.7)
        
        # 预编译正则表达式
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化正则表达式模式"""
        # 章节标题模式
        self.section_patterns = {
            'abstract': re.compile(r'\b(?:abstract|摘要|summary)\b', re.IGNORECASE),
            'introduction': re.compile(r'\b(?:introduction|引言|前言|背景|background)\b', re.IGNORECASE),
            'methods': re.compile(r'\b(?:methods?|methodology|材料与方法|方法|materials?\s+and\s+methods?)\b', re.IGNORECASE),
            'results': re.compile(r'\b(?:results?|findings|结果|发现)\b', re.IGNORECASE),
            'discussion': re.compile(r'\b(?:discussion|讨论|分析)\b', re.IGNORECASE),
            'conclusion': re.compile(r'\b(?:conclusions?|结论|总结)\b', re.IGNORECASE),
            'references': re.compile(r'\b(?:references?|reference\s+list|bibliography|参考文献)\b', re.IGNORECASE),
            'acknowledgments': re.compile(r'\b(?:acknowledgments?|acknowledgements?|致谢)\b', re.IGNORECASE),
            'funding': re.compile(r'\b(?:funding|financial\s+support|资助|基金)\b', re.IGNORECASE)
        }
        
        # 清理模式
        self.cleanup_patterns = {
            'multiple_spaces': re.compile(r'\s+'),
            'multiple_newlines': re.compile(r'\n\s*\n\s*\n+'),
            'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'url': re.compile(r'https?://[^\s<>"{}|\\^`[\]]+'),
            'doi': re.compile(r'doi:\s*10\.\d+/[^\s]+', re.IGNORECASE),
            'figure_ref': re.compile(r'\b(?:fig(?:ure)?\s*\.?\s*\d+|图\s*\d+)\b', re.IGNORECASE),
            'table_ref': re.compile(r'\b(?:table\s*\.?\s*\d+|表\s*\d+)\b', re.IGNORECASE),
            'citation': re.compile(r'\[\d+(?:[-–—,]\d+)*\]|\(\d+(?:[-–—,]\d+)*\)'),
            'page_numbers': re.compile(r'\b(?:page|p\.)\s*\d+\b', re.IGNORECASE)
        }
    
    def clean_text(self, text: str, preserve_structure: bool = True) -> str:
        """
        清理文本内容
        
        Args:
            text: 原始文本
            preserve_structure: 是否保留结构
            
        Returns:
            清理后的文本
        """
        if not text:
            return ""
        
        cleaned_text = text
        
        # 移除URL和邮箱
        cleaned_text = self.cleanup_patterns['url'].sub('', cleaned_text)
        cleaned_text = self.cleanup_patterns['email'].sub('', cleaned_text)
        
        # 简化引用格式
        cleaned_text = self.cleanup_patterns['citation'].sub('[REF]', cleaned_text)
        cleaned_text = self.cleanup_patterns['figure_ref'].sub('[FIGURE]', cleaned_text)
        cleaned_text = self.cleanup_patterns['table_ref'].sub('[TABLE]', cleaned_text)
        
        # 移除页码
        cleaned_text = self.cleanup_patterns['page_numbers'].sub('', cleaned_text)
        
        # 标准化空白字符
        cleaned_text = self.cleanup_patterns['multiple_spaces'].sub(' ', cleaned_text)
        
        if preserve_structure:
            # 保留段落结构，但限制连续换行
            cleaned_text = self.cleanup_patterns['multiple_newlines'].sub('\n\n', cleaned_text)
        else:
            # 移除所有换行，转为单行
            cleaned_text = cleaned_text.replace('\n', ' ')
            cleaned_text = self.cleanup_patterns['multiple_spaces'].sub(' ', cleaned_text)
        
        return cleaned_text.strip()
    
    def identify_sections(self, text: str) -> Dict[str, Tuple[int, int]]:
        """
        识别文本中的章节位置
        
        Args:
            text: 文本内容
            
        Returns:
            章节位置字典 {章节名: (开始位置, 结束位置)}
        """
        sections = {}
        text_lower = text.lower()
        
        # 找到所有可能的章节开始位置
        section_positions = []
        
        for section_name, pattern in self.section_patterns.items():
            for match in pattern.finditer(text_lower):
                start_pos = match.start()
                
                # 检查是否在行首或前面是换行符
                if start_pos == 0 or text[start_pos-1] in '\n\r':
                    section_positions.append((start_pos, section_name))
        
        # 按位置排序
        section_positions.sort(key=lambda x: x[0])
        
        # 确定每个章节的结束位置
        for i, (start_pos, section_name) in enumerate(section_positions):
            if i + 1 < len(section_positions):
                end_pos = section_positions[i + 1][0]
            else:
                end_pos = len(text)
            
            # 检查章节长度
            section_length = end_pos - start_pos
            if section_length >= self.min_section_length:
                sections[section_name] = (start_pos, end_pos)
        
        return sections
    
    def extract_sections(self, text: str, 
                        target_sections: Optional[List[str]] = None) -> Dict[str, str]:
        """
        提取特定章节的文本
        
        Args:
            text: 原始文本
            target_sections: 目标章节列表，None表示所有章节
            
        Returns:
            章节文本字典
        """
        if not text:
            return {}
        
        # 识别章节位置
        section_positions = self.identify_sections(text)
        
        if not section_positions:
            # 如果没有识别到章节，返回整个文本
            return {'full_text': text}
        
        # 提取目标章节
        if target_sections is None:
            target_sections = list(section_positions.keys())
        
        extracted_sections = {}
        
        for section_name in target_sections:
            if section_name in section_positions:
                start_pos, end_pos = section_positions[section_name]
                section_text = text[start_pos:end_pos].strip()
                
                # 清理章节文本
                section_text = self.clean_text(section_text, preserve_structure=True)
                
                if len(section_text) >= self.min_section_length:
                    extracted_sections[section_name] = section_text
        
        return extracted_sections
    
    def compress_text(self, text: str, target_ratio: Optional[float] = None) -> str:
        """
        智能压缩文本
        
        Args:
            text: 原始文本
            target_ratio: 目标压缩比例
            
        Returns:
            压缩后的文本
        """
        if not text:
            return ""
        
        target_ratio = target_ratio or self.compression_ratio
        target_length = int(len(text) * target_ratio)
        
        if len(text) <= target_length:
            return text
        
        # 按句子分割
        sentences = self._split_sentences(text)
        
        if not sentences:
            # 如果无法分割句子，截取前部分
            return text[:target_length] + "..."
        
        # 计算句子重要性分数
        sentence_scores = self._score_sentences(sentences)
        
        # 按分数排序并选择重要句子
        scored_sentences = list(zip(sentences, sentence_scores, range(len(sentences))))
        scored_sentences.sort(key=lambda x: (-x[1], x[2]))  # 按分数降序，位置升序
        
        # 选择句子直到达到目标长度
        selected_sentences = []
        current_length = 0
        
        for sentence, score, original_index in scored_sentences:
            if current_length + len(sentence) <= target_length:
                selected_sentences.append((sentence, original_index))
                current_length += len(sentence)
            else:
                break
        
        # 按原始顺序排列选中的句子
        selected_sentences.sort(key=lambda x: x[1])
        compressed_text = ' '.join([sentence for sentence, _ in selected_sentences])
        
        return compressed_text
    
    def _split_sentences(self, text: str) -> List[str]:
        """
        分割句子
        
        Args:
            text: 文本
            
        Returns:
            句子列表
        """
        # 简单的句子分割（可以改进）
        sentence_pattern = re.compile(r'[.!?。！？]+\s+')
        sentences = sentence_pattern.split(text)
        
        # 过滤空句子和过短句子
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        return sentences
    
    def _score_sentences(self, sentences: List[str]) -> List[float]:
        """
        计算句子重要性分数
        
        Args:
            sentences: 句子列表
            
        Returns:
            分数列表
        """
        scores = []
        
        # 关键词权重
        important_keywords = [
            'method', 'result', 'conclusion', 'significant', 'important',
            '方法', '结果', '结论', '显著', '重要', '发现', '表明', '证明'
        ]
        
        for sentence in sentences:
            score = 0.0
            sentence_lower = sentence.lower()
            
            # 长度分数（中等长度句子得分更高）
            length_score = 1.0 - abs(len(sentence) - 100) / 200
            score += max(0, length_score) * 0.3
            
            # 关键词分数
            keyword_count = sum(1 for keyword in important_keywords 
                              if keyword in sentence_lower)
            score += keyword_count * 0.4
            
            # 数字分数（包含数字的句子可能更重要）
            if re.search(r'\d+', sentence):
                score += 0.2
            
            # 位置分数（开头和结尾的句子更重要）
            # 这个在调用函数中处理
            
            scores.append(score)
        
        return scores
    
    def optimize_for_llm(self, text: str, max_tokens: int = 4000) -> str:
        """
        为LLM优化文本
        
        Args:
            text: 原始文本
            max_tokens: 最大token数（粗略估计）
            
        Returns:
            优化后的文本
        """
        if not text:
            return ""
        
        # 粗略估计：1个token约等于4个字符（中英文混合）
        max_chars = max_tokens * 4
        
        if len(text) <= max_chars:
            return self.clean_text(text)
        
        self.logger.debug(f"文本过长（{len(text)}字符），开始优化...")
        
        # 提取关键章节
        key_sections = ['abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion']
        sections = self.extract_sections(text, key_sections)
        
        if not sections:
            # 如果没有识别到章节，直接压缩
            return self.compress_text(text, max_chars / len(text))
        
        # 按重要性分配字符配额
        section_quotas = {
            'abstract': 0.15,
            'introduction': 0.20,
            'methods': 0.25,
            'results': 0.25,
            'discussion': 0.15
        }
        
        optimized_sections = {}
        total_quota_used = 0
        
        for section_name, section_text in sections.items():
            quota = section_quotas.get(section_name, 0.1)
            section_max_chars = int(max_chars * quota)
            
            if len(section_text) > section_max_chars:
                optimized_text = self.compress_text(section_text, section_max_chars / len(section_text))
            else:
                optimized_text = self.clean_text(section_text)
            
            optimized_sections[section_name] = optimized_text
            total_quota_used += len(optimized_text)
        
        # 组合优化后的文本
        result_parts = []
        for section_name in key_sections:
            if section_name in optimized_sections:
                result_parts.append(f"=== {section_name.upper()} ===")
                result_parts.append(optimized_sections[section_name])
                result_parts.append("")
        
        optimized_text = "\n".join(result_parts).strip()
        
        self.logger.debug(f"文本优化完成：{len(text)} -> {len(optimized_text)} 字符")
        
        return optimized_text
    
    def preprocess_batch(self, papers: List[Dict[str, Any]], 
                        max_tokens: int = 4000) -> List[Dict[str, Any]]:
        """
        批量预处理文献文本
        
        Args:
            papers: 文献列表
            max_tokens: 最大token数
            
        Returns:
            预处理后的文献列表
        """
        self.logger.info(f"📝 开始批量预处理文本，共 {len(papers)} 篇文献")
        
        processed_papers = []
        
        for i, paper in enumerate(papers, 1):
            self.logger.debug(f"预处理第 {i}/{len(papers)} 篇文献...")
            
            full_text = paper.get('full_text', '')
            
            if full_text:
                try:
                    # 优化文本
                    optimized_text = self.optimize_for_llm(full_text, max_tokens)
                    
                    # 更新文献记录
                    processed_paper = paper.copy()
                    processed_paper['full_text'] = optimized_text
                    processed_paper['original_text_length'] = len(full_text)
                    processed_paper['optimized_text_length'] = len(optimized_text)
                    processed_paper['compression_ratio'] = len(optimized_text) / len(full_text) if full_text else 1.0
                    
                    processed_papers.append(processed_paper)
                    
                except Exception as e:
                    pmid = paper.get('PMID', 'Unknown')
                    self.logger.error(f"❌ 预处理文献 {pmid} 失败: {e}")
                    processed_papers.append(paper)  # 保留原始文献
            else:
                processed_papers.append(paper)  # 没有全文的文献保持不变
        
        # 统计结果
        optimized_count = sum(1 for p in processed_papers if 'compression_ratio' in p)
        avg_compression = sum(p.get('compression_ratio', 1.0) for p in processed_papers) / len(processed_papers)
        
        self.logger.info(f"✅ 批量预处理完成: {optimized_count}/{len(papers)} 篇优化")
        self.logger.info(f"📊 平均压缩比: {avg_compression:.2f}")
        
        return processed_papers
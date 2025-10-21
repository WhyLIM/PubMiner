# -*- coding: utf-8 -*-
"""
内容摘要器

使用多种算法对文献内容进行智能摘要，减少token消耗
"""

import re
import math
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional, Tuple
import logging

from utils.logger import LoggerMixin

logger = logging.getLogger(__name__)

class ContentSummarizer(LoggerMixin):
    """内容摘要器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化内容摘要器
        
        Args:
            config: 摘要配置
        """
        self.config = config
        self.compression_ratio = config.get('compression_ratio', 0.3)
        self.min_sentence_length = config.get('min_sentence_length', 20)
        self.max_sentence_length = config.get('max_sentence_length', 500)
        
        # 初始化停用词
        self._init_stopwords()
        
        # 初始化关键词权重
        self._init_keyword_weights()
    
    def _init_stopwords(self):
        """初始化停用词表"""
        # 英文停用词
        english_stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'among', 'this', 'that',
            'these', 'those', 'i', 'me', 'my', 'myself', 'we', 'our', 'ours',
            'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he',
            'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its',
            'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what',
            'which', 'who', 'whom', 'whose', 'this', 'that', 'these', 'those',
            'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
            'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'cannot'
        }
        
        # 中文停用词
        chinese_stopwords = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
            '看', '好', '自己', '这', '那', '里', '就是', '还', '把', '比', '或者',
            '因为', '所以', '但是', '如果', '虽然', '然而', '而且', '另外', '此外',
            '首先', '其次', '最后', '总之', '因此', '然后', '接着', '同时', '另一方面'
        }
        
        self.stopwords = english_stopwords | chinese_stopwords
    
    def _init_keyword_weights(self):
        """初始化关键词权重"""
        self.keyword_weights = {
            # 方法相关
            'method': 2.0, 'methodology': 2.0, 'approach': 1.5, 'technique': 1.5,
            'procedure': 1.5, 'protocol': 1.5, 'algorithm': 1.5,
            '方法': 2.0, '技术': 1.5, '算法': 1.5, '流程': 1.5,
            
            # 结果相关  
            'result': 2.0, 'finding': 2.0, 'outcome': 1.8, 'conclusion': 2.0,
            'significant': 1.8, 'correlation': 1.5, 'association': 1.5,
            '结果': 2.0, '发现': 2.0, '结论': 2.0, '显著': 1.8, '相关': 1.5,
            
            # 统计相关
            'statistical': 1.5, 'analysis': 1.5, 'regression': 1.5, 'model': 1.5,
            'p-value': 1.8, 'confidence': 1.5, 'interval': 1.5,
            '统计': 1.5, '分析': 1.5, '模型': 1.5, '回归': 1.5,
            
            # 医学相关
            'patient': 1.8, 'treatment': 1.8, 'diagnosis': 1.8, 'clinical': 1.8,
            'therapy': 1.5, 'disease': 1.5, 'symptom': 1.5, 'biomarker': 2.0,
            '患者': 1.8, '治疗': 1.8, '诊断': 1.8, '临床': 1.8, '疾病': 1.5,
            
            # 研究相关
            'study': 1.5, 'research': 1.5, 'investigation': 1.5, 'experiment': 1.5,
            'trial': 1.5, 'survey': 1.5, 'cohort': 1.5,
            '研究': 1.5, '实验': 1.5, '调查': 1.5, '试验': 1.5
        }
    
    def _tokenize_text(self, text: str) -> List[str]:
        """
        文本分词
        
        Args:
            text: 文本内容
            
        Returns:
            词汇列表
        """
        # 简单的分词实现
        # 处理英文单词
        english_words = re.findall(r'\b[A-Za-z]+\b', text.lower())
        
        # 处理中文单词（简单按字符分）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        chinese_words = []
        for chars in chinese_chars:
            # 简单的中文分词（可以改进）
            chinese_words.extend(list(chars))
        
        # 合并并过滤停用词
        all_words = english_words + chinese_words
        filtered_words = [word for word in all_words if word not in self.stopwords and len(word) > 1]
        
        return filtered_words
    
    def _split_sentences(self, text: str) -> List[str]:
        """
        分句
        
        Args:
            text: 文本内容
            
        Returns:
            句子列表
        """
        # 句子分隔符
        sentence_delimiters = r'[.!?。！？]+\s+'
        sentences = re.split(sentence_delimiters, text)
        
        # 过滤和清理句子
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            
            # 过滤长度
            if (self.min_sentence_length <= len(sentence) <= self.max_sentence_length and
                sentence and not sentence.isspace()):
                cleaned_sentences.append(sentence)
        
        return cleaned_sentences
    
    def _calculate_word_frequencies(self, sentences: List[str]) -> Dict[str, float]:
        """
        计算词频
        
        Args:
            sentences: 句子列表
            
        Returns:
            词频字典
        """
        word_freq = Counter()
        
        for sentence in sentences:
            words = self._tokenize_text(sentence)
            word_freq.update(words)
        
        # 归一化频率
        max_freq = max(word_freq.values()) if word_freq else 1
        normalized_freq = {word: freq / max_freq for word, freq in word_freq.items()}
        
        return normalized_freq
    
    def _score_sentences(self, sentences: List[str], 
                        word_frequencies: Dict[str, float]) -> List[float]:
        """
        计算句子得分
        
        Args:
            sentences: 句子列表
            word_frequencies: 词频字典
            
        Returns:
            句子得分列表
        """
        scores = []
        
        for i, sentence in enumerate(sentences):
            words = self._tokenize_text(sentence)
            
            if not words:
                scores.append(0.0)
                continue
            
            # 基础得分：词频加权平均
            freq_score = sum(word_frequencies.get(word, 0) for word in words) / len(words)
            
            # 关键词权重得分
            keyword_score = 0.0
            for word in words:
                if word.lower() in self.keyword_weights:
                    keyword_score += self.keyword_weights[word.lower()]
            keyword_score = keyword_score / len(words) if words else 0
            
            # 位置得分（开头和结尾的句子更重要）
            position_score = 0.0
            total_sentences = len(sentences)
            if i < total_sentences * 0.1:  # 前10%
                position_score = 0.3
            elif i > total_sentences * 0.9:  # 后10%
                position_score = 0.2
            
            # 长度得分（中等长度的句子更好）
            length_score = 1.0 - abs(len(sentence) - 100) / 200
            length_score = max(0, length_score) * 0.1
            
            # 数字得分（包含数字的句子可能更重要）
            number_score = 0.1 if re.search(r'\d+', sentence) else 0
            
            # 综合得分
            total_score = (freq_score * 0.4 + 
                          keyword_score * 0.3 + 
                          position_score + 
                          length_score + 
                          number_score)
            
            scores.append(total_score)
        
        return scores
    
    def extractive_summarize(self, text: str, 
                           target_ratio: Optional[float] = None) -> str:
        """
        抽取式摘要
        
        Args:
            text: 原始文本
            target_ratio: 目标压缩比例
            
        Returns:
            摘要文本
        """
        if not text:
            return ""
        
        target_ratio = target_ratio or self.compression_ratio
        
        # 分句
        sentences = self._split_sentences(text)
        
        if not sentences:
            return text
        
        # 如果句子数量很少，直接返回
        if len(sentences) <= 3:
            return text
        
        # 计算词频
        word_frequencies = self._calculate_word_frequencies(sentences)
        
        # 计算句子得分
        sentence_scores = self._score_sentences(sentences, word_frequencies)
        
        # 确定要选择的句子数量
        target_sentence_count = max(1, int(len(sentences) * target_ratio))
        
        # 选择得分最高的句子
        sentence_score_pairs = list(zip(sentences, sentence_scores, range(len(sentences))))
        sentence_score_pairs.sort(key=lambda x: (-x[1], x[2]))  # 按得分降序，位置升序
        
        selected_pairs = sentence_score_pairs[:target_sentence_count]
        
        # 按原始顺序重新排列
        selected_pairs.sort(key=lambda x: x[2])
        
        # 组合摘要
        summary_sentences = [pair[0] for pair in selected_pairs]
        summary = ' '.join(summary_sentences)
        
        return summary
    
    def keyword_based_summarize(self, text: str, 
                               keywords: List[str],
                               target_ratio: Optional[float] = None) -> str:
        """
        基于关键词的摘要
        
        Args:
            text: 原始文本
            keywords: 关键词列表
            target_ratio: 目标压缩比例
            
        Returns:
            摘要文本
        """
        if not text or not keywords:
            return self.extractive_summarize(text, target_ratio)
        
        target_ratio = target_ratio or self.compression_ratio
        
        # 分句
        sentences = self._split_sentences(text)
        
        if not sentences:
            return text
        
        # 计算句子与关键词的相关性
        keyword_scores = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            score = 0.0
            
            for keyword in keywords:
                keyword_lower = keyword.lower()
                # 精确匹配
                exact_matches = sentence_lower.count(keyword_lower)
                score += exact_matches * 2.0
                
                # 部分匹配
                if keyword_lower in sentence_lower:
                    score += 1.0
            
            keyword_scores.append(score)
        
        # 结合通用摘要得分
        word_frequencies = self._calculate_word_frequencies(sentences)
        general_scores = self._score_sentences(sentences, word_frequencies)
        
        # 综合得分
        combined_scores = []
        for i in range(len(sentences)):
            combined_score = keyword_scores[i] * 0.7 + general_scores[i] * 0.3
            combined_scores.append(combined_score)
        
        # 选择句子
        target_sentence_count = max(1, int(len(sentences) * target_ratio))
        
        sentence_score_pairs = list(zip(sentences, combined_scores, range(len(sentences))))
        sentence_score_pairs.sort(key=lambda x: (-x[1], x[2]))
        
        selected_pairs = sentence_score_pairs[:target_sentence_count]
        selected_pairs.sort(key=lambda x: x[2])
        
        summary_sentences = [pair[0] for pair in selected_pairs]
        summary = ' '.join(summary_sentences)
        
        return summary
    
    def section_aware_summarize(self, sections: Dict[str, str],
                               target_length: int = 10000) -> str:
        """
        章节感知的摘要
        
        Args:
            sections: 章节字典
            target_length: 目标长度
            
        Returns:
            摘要文本
        """
        if not sections:
            return ""
        
        # 计算当前总长度
        total_length = sum(len(content) for content in sections.values())
        
        if total_length <= target_length:
            # 重新组合所有章节
            return self._reconstruct_text(sections)
        
        # 章节重要性权重
        section_weights = {
            'abstract': 0.20,
            'introduction': 0.15,
            'methods': 0.20,
            'results': 0.25,
            'discussion': 0.15,
            'conclusion': 0.05
        }
        
        # 为每个章节分配长度配额
        summarized_sections = {}
        
        for section_name, content in sections.items():
            weight = section_weights.get(section_name, 0.1)
            allocated_length = int(target_length * weight)
            
            if len(content) <= allocated_length:
                # 不需要摘要
                summarized_sections[section_name] = content
            else:
                # 需要摘要
                compression_ratio = allocated_length / len(content)
                summarized_content = self.extractive_summarize(content, compression_ratio)
                summarized_sections[section_name] = summarized_content
        
        return self._reconstruct_text(summarized_sections)
    
    def _reconstruct_text(self, sections: Dict[str, str]) -> str:
        """
        重构文本
        
        Args:
            sections: 章节字典
            
        Returns:
            重构的文本
        """
        # 章节顺序
        section_order = ['abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion']
        
        text_parts = []
        
        # 按顺序添加章节
        for section_name in section_order:
            if section_name in sections:
                content = sections[section_name].strip()
                if content:
                    text_parts.append(f"=== {section_name.upper()} ===")
                    text_parts.append(content)
                    text_parts.append("")
        
        # 添加其他章节
        for section_name, content in sections.items():
            if section_name not in section_order:
                content = content.strip()
                if content:
                    text_parts.append(f"=== {section_name.upper()} ===")
                    text_parts.append(content)
                    text_parts.append("")
        
        return "\n".join(text_parts).strip()
    
    def adaptive_summarize(self, text: str, 
                          target_length: int,
                          extraction_type: str = 'standard') -> str:
        """
        自适应摘要
        
        Args:
            text: 原始文本
            target_length: 目标长度
            extraction_type: 提取类型
            
        Returns:
            摘要文本
        """
        if not text or len(text) <= target_length:
            return text
        
        self.logger.debug(f"开始自适应摘要: {len(text)} -> {target_length}")
        
        # 根据提取类型确定关键词
        type_keywords = {
            'standard': ['method', 'result', 'conclusion', '方法', '结果', '结论'],
            'biomarker': ['biomarker', 'marker', 'protein', 'gene', '生物标志物', '蛋白质', '基因'],
            'clinical': ['patient', 'clinical', 'treatment', 'diagnosis', '患者', '临床', '治疗', '诊断'],
            'methodology': ['method', 'approach', 'technique', 'protocol', '方法', '技术', '流程']
        }
        
        keywords = type_keywords.get(extraction_type, type_keywords['standard'])
        
        # 尝试基于关键词的摘要
        target_ratio = target_length / len(text)
        keyword_summary = self.keyword_based_summarize(text, keywords, target_ratio)
        
        if len(keyword_summary) <= target_length:
            return keyword_summary
        
        # 如果还是太长，使用抽取式摘要
        extractive_summary = self.extractive_summarize(keyword_summary, target_ratio * 0.8)
        
        if len(extractive_summary) <= target_length:
            return extractive_summary
        
        # 最后的截取
        return extractive_summary[:target_length-3] + '...'
    
    def get_summary_statistics(self, original_text: str, summary_text: str) -> Dict[str, Any]:
        """
        获取摘要统计信息
        
        Args:
            original_text: 原始文本
            summary_text: 摘要文本
            
        Returns:
            统计信息字典
        """
        original_sentences = self._split_sentences(original_text)
        summary_sentences = self._split_sentences(summary_text)
        
        return {
            'original_length': len(original_text),
            'summary_length': len(summary_text),
            'compression_ratio': len(summary_text) / len(original_text) if original_text else 0,
            'original_sentence_count': len(original_sentences),
            'summary_sentence_count': len(summary_sentences),
            'sentence_reduction_ratio': len(summary_sentences) / len(original_sentences) if original_sentences else 0
        }
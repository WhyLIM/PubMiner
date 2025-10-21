# -*- coding: utf-8 -*-
"""
章节过滤器

智能识别和筛选文献中的关键章节，提高信息提取效率
"""

import re
from typing import Dict, List, Any, Optional, Set
import logging

from utils.logger import LoggerMixin

logger = logging.getLogger(__name__)

class SectionFilter(LoggerMixin):
    """章节过滤器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化章节过滤器
        
        Args:
            config: 过滤配置
        """
        self.config = config
        self.section_filters = config.get('section_filters', [])
        self.exclude_sections = config.get('exclude_sections', [])
        self.key_section_ratio = config.get('key_section_ratio', {})
        
        # 预定义章节模式
        self._init_section_patterns()
    
    def _init_section_patterns(self):
        """初始化章节识别模式"""
        self.section_patterns = {
            # 英文章节模式
            'abstract': [
                r'\babstract\b',
                r'\bsummary\b',
                r'\bexecutive\s+summary\b'
            ],
            'introduction': [
                r'\bintroduction\b',
                r'\bbackground\b',
                r'\boverview\b',
                r'\bpreamble\b'
            ],
            'methods': [
                r'\bmethods?\b',
                r'\bmethodology\b',
                r'\bmaterials?\s+and\s+methods?\b',
                r'\bexperimental\s+(?:design|procedure|setup)\b',
                r'\bstudy\s+design\b'
            ],
            'results': [
                r'\bresults?\b',
                r'\bfindings?\b',
                r'\boutcomes?\b',
                r'\bobservations?\b'
            ],
            'discussion': [
                r'\bdiscussion\b',
                r'\banalysis\b',
                r'\binterpretation\b',
                r'\bimplications?\b'
            ],
            'conclusion': [
                r'\bconclusions?\b',
                r'\bconclusion\s+and\s+future\s+work\b',
                r'\bsummary\s+and\s+conclusions?\b',
                r'\bfinal\s+remarks?\b'
            ],
            
            # 中文章节模式
            'abstract_zh': [
                r'摘要',
                r'概要',
                r'内容提要',
                r'文章摘要'
            ],
            'introduction_zh': [
                r'引言',
                r'前言',
                r'背景',
                r'概述',
                r'绪论'
            ],
            'methods_zh': [
                r'方法',
                r'材料与方法',
                r'研究方法',
                r'实验方法',
                r'方法学'
            ],
            'results_zh': [
                r'结果',
                r'实验结果',
                r'研究结果',
                r'发现',
                r'观察结果'
            ],
            'discussion_zh': [
                r'讨论',
                r'分析',
                r'分析与讨论',
                r'结果分析'
            ],
            'conclusion_zh': [
                r'结论',
                r'总结',
                r'小结',
                r'结语',
                r'结论和建议'
            ],
            
            # 排除章节模式
            'references': [
                r'\breferences?\b',
                r'\bbibliography\b',
                r'\bworks?\s+cited\b',
                r'参考文献',
                r'文献引用'
            ],
            'acknowledgments': [
                r'\backnowledg?ments?\b',
                r'\backnowledg?ements?\b',
                r'\bthanks?\b',
                r'致谢',
                r'鸣谢'
            ],
            'funding': [
                r'\bfunding\b',
                r'\bfinancial\s+support\b',
                r'\bgrants?\b',
                r'资助',
                r'基金',
                r'资金支持'
            ],
            'appendix': [
                r'\bappendix\b',
                r'\bappendices\b',
                r'\bsupplementary\s+(?:material|information)\b',
                r'附录',
                r'补充材料'
            ],
            'author_info': [
                r'\bauthor\s+(?:information|contributions?|details?)\b',
                r'\bcompeting\s+interests?\b',
                r'\bconflicts?\s+of\s+interests?\b',
                r'作者信息',
                r'作者贡献',
                r'利益冲突'
            ]
        }
        
        # 编译正则表达式
        self.compiled_patterns = {}
        for section_type, patterns in self.section_patterns.items():
            self.compiled_patterns[section_type] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in patterns
            ]
    
    def identify_section_boundaries(self, text: str) -> List[Dict[str, Any]]:
        """
        识别文本中的章节边界
        
        Args:
            text: 文本内容
            
        Returns:
            章节边界列表，每个元素包含 {type, start, end, title}
        """
        boundaries = []
        
        # 查找所有可能的章节标题
        for section_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    start_pos = match.start()
                    
                    # 检查是否在行首或接近行首
                    line_start = text.rfind('\n', 0, start_pos) + 1
                    prefix = text[line_start:start_pos].strip()
                    
                    # 如果前面只有少量字符（如编号），认为是章节标题
                    if len(prefix) <= 10 and not any(c.isalpha() for c in prefix):
                        boundaries.append({
                            'type': section_type,
                            'start': start_pos,
                            'title': match.group(0),
                            'line_start': line_start
                        })
        
        # 按位置排序
        boundaries.sort(key=lambda x: x['start'])
        
        # 去重和合并相近的边界
        filtered_boundaries = []
        for boundary in boundaries:
            # 检查是否与已有边界重叠
            is_duplicate = False
            for existing in filtered_boundaries:
                if abs(boundary['start'] - existing['start']) < 50:
                    # 选择更精确的匹配
                    if len(boundary['title']) > len(existing['title']):
                        filtered_boundaries.remove(existing)
                        break
                    else:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                filtered_boundaries.append(boundary)
        
        # 计算结束位置
        for i, boundary in enumerate(filtered_boundaries):
            if i + 1 < len(filtered_boundaries):
                boundary['end'] = filtered_boundaries[i + 1]['line_start']
            else:
                boundary['end'] = len(text)
        
        return filtered_boundaries
    
    def extract_sections(self, text: str) -> Dict[str, str]:
        """
        提取文本中的各个章节
        
        Args:
            text: 原始文本
            
        Returns:
            章节字典 {章节类型: 章节内容}
        """
        if not text:
            return {}
        
        boundaries = self.identify_section_boundaries(text)
        
        if not boundaries:
            self.logger.debug("未识别到章节结构，返回完整文本")
            return {'full_text': text}
        
        sections = {}
        
        for boundary in boundaries:
            section_type = boundary['type']
            start_pos = boundary['start']
            end_pos = boundary['end']
            
            # 提取章节内容
            section_content = text[start_pos:end_pos].strip()
            
            # 过滤太短的章节
            if len(section_content) < 50:
                continue
            
            # 合并相同类型的章节（中英文）
            base_type = section_type.replace('_zh', '')
            if base_type in sections:
                sections[base_type] += '\n\n' + section_content
            else:
                sections[base_type] = section_content
        
        return sections
    
    def filter_relevant_sections(self, sections: Dict[str, str], 
                                extraction_type: str = 'standard') -> Dict[str, str]:
        """
        根据提取类型筛选相关章节
        
        Args:
            sections: 章节字典
            extraction_type: 提取类型
            
        Returns:
            筛选后的章节字典
        """
        if not sections:
            return {}
        
        # 定义不同提取类型的相关章节
        relevant_sections_map = {
            'standard': ['abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion'],
            'methodology': ['abstract', 'introduction', 'methods', 'materials'],
            'results_focused': ['abstract', 'methods', 'results', 'discussion'],
            'background_focused': ['abstract', 'introduction', 'background', 'literature_review'],
            'biomarker': ['abstract', 'introduction', 'methods', 'results', 'discussion'],
            'clinical': ['abstract', 'methods', 'results', 'clinical_implications', 'conclusion']
        }
        
        relevant_sections = relevant_sections_map.get(extraction_type, 
                                                    relevant_sections_map['standard'])
        
        # 筛选相关章节
        filtered_sections = {}
        for section_type in relevant_sections:
            if section_type in sections:
                filtered_sections[section_type] = sections[section_type]
        
        # 如果没有找到相关章节，返回所有非排除章节
        if not filtered_sections:
            exclude_types = {'references', 'acknowledgments', 'funding', 'appendix', 'author_info'}
            filtered_sections = {
                k: v for k, v in sections.items() 
                if k not in exclude_types
            }
        
        return filtered_sections
    
    def prioritize_sections(self, sections: Dict[str, str], 
                          max_total_length: int = 15000) -> Dict[str, str]:
        """
        根据重要性优先级筛选章节
        
        Args:
            sections: 章节字典
            max_total_length: 最大总长度
            
        Returns:
            优先级筛选后的章节字典
        """
        if not sections:
            return {}
        
        # 计算当前总长度
        total_length = sum(len(content) for content in sections.values())
        
        if total_length <= max_total_length:
            return sections
        
        # 章节优先级和权重
        section_priority = {
            'abstract': 1.0,
            'introduction': 0.8,
            'methods': 0.9,
            'results': 1.0,
            'discussion': 0.8,
            'conclusion': 0.7,
            'background': 0.6,
            'literature_review': 0.5,
            'limitations': 0.6,
            'future_work': 0.4
        }
        
        # 计算每个章节的分配长度
        prioritized_sections = {}
        remaining_length = max_total_length
        
        # 按优先级排序
        sorted_sections = sorted(
            sections.items(),
            key=lambda x: section_priority.get(x[0], 0.3),
            reverse=True
        )
        
        for section_type, content in sorted_sections:
            if remaining_length <= 0:
                break
            
            priority = section_priority.get(section_type, 0.3)
            
            # 计算该章节应分配的长度
            if len(content) <= remaining_length * priority:
                # 完整保留
                prioritized_sections[section_type] = content
                remaining_length -= len(content)
            else:
                # 部分保留
                allocated_length = max(int(remaining_length * priority), 500)
                if allocated_length < len(content):
                    truncated_content = content[:allocated_length-3] + '...'
                    prioritized_sections[section_type] = truncated_content
                    remaining_length -= allocated_length
                else:
                    prioritized_sections[section_type] = content
                    remaining_length -= len(content)
        
        final_length = sum(len(content) for content in prioritized_sections.values())
        self.logger.debug(f"章节优先级筛选: {total_length} -> {final_length} 字符")
        
        return prioritized_sections
    
    def smart_section_selection(self, text: str, 
                              extraction_type: str = 'standard',
                              max_length: int = 15000) -> str:
        """
        智能章节选择和组合
        
        Args:
            text: 原始文本
            extraction_type: 提取类型
            max_length: 最大长度
            
        Returns:
            优化后的文本
        """
        if not text or len(text) <= max_length:
            return text
        
        self.logger.debug(f"开始智能章节选择: {len(text)} -> {max_length}")
        
        # 提取章节
        sections = self.extract_sections(text)
        
        if not sections or 'full_text' in sections:
            # 没有识别到章节结构，使用简单截取
            return text[:max_length-3] + '...'
        
        # 过滤相关章节
        relevant_sections = self.filter_relevant_sections(sections, extraction_type)
        
        # 优先级筛选
        prioritized_sections = self.prioritize_sections(relevant_sections, max_length)
        
        # 重新组合文本
        if not prioritized_sections:
            return text[:max_length-3] + '...'
        
        # 按逻辑顺序排列章节
        section_order = ['abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion']
        
        result_parts = []
        for section_type in section_order:
            if section_type in prioritized_sections:
                content = prioritized_sections[section_type]
                result_parts.append(f"=== {section_type.upper()} ===")
                result_parts.append(content)
                result_parts.append("")
        
        # 添加其他章节
        for section_type, content in prioritized_sections.items():
            if section_type not in section_order:
                result_parts.append(f"=== {section_type.upper()} ===")
                result_parts.append(content)
                result_parts.append("")
        
        result_text = "\n".join(result_parts).strip()
        
        # 最终长度检查
        if len(result_text) > max_length:
            result_text = result_text[:max_length-3] + '...'
        
        self.logger.debug(f"智能章节选择完成: {len(result_text)} 字符")
        
        return result_text
    
    def analyze_section_distribution(self, text: str) -> Dict[str, Any]:
        """
        分析文本的章节分布
        
        Args:
            text: 文本内容
            
        Returns:
            章节分布分析结果
        """
        sections = self.extract_sections(text)
        
        if not sections:
            return {
                'total_sections': 0,
                'has_structure': False,
                'section_types': [],
                'section_lengths': {},
                'coverage': {}
            }
        
        # 统计信息
        section_lengths = {k: len(v) for k, v in sections.items()}
        total_length = sum(section_lengths.values())
        
        # 覆盖率分析
        important_sections = ['abstract', 'introduction', 'methods', 'results', 'discussion']
        coverage = {}
        
        for section_type in important_sections:
            if section_type in sections:
                coverage[section_type] = {
                    'present': True,
                    'length': section_lengths[section_type],
                    'ratio': section_lengths[section_type] / total_length if total_length > 0 else 0
                }
            else:
                coverage[section_type] = {'present': False, 'length': 0, 'ratio': 0}
        
        return {
            'total_sections': len(sections),
            'has_structure': len(sections) > 1,
            'section_types': list(sections.keys()),
            'section_lengths': section_lengths,
            'total_length': total_length,
            'coverage': coverage,
            'structure_quality': self._assess_structure_quality(coverage)
        }
    
    def _assess_structure_quality(self, coverage: Dict[str, Any]) -> str:
        """
        评估文本结构质量
        
        Args:
            coverage: 章节覆盖情况
            
        Returns:
            质量评级 (excellent/good/fair/poor)
        """
        present_count = sum(1 for info in coverage.values() if info['present'])
        
        # 检查关键章节
        key_sections = ['abstract', 'methods', 'results']
        key_present = sum(1 for section in key_sections if coverage.get(section, {}).get('present', False))
        
        if present_count >= 4 and key_present >= 2:
            return 'excellent'
        elif present_count >= 3 and key_present >= 2:
            return 'good'
        elif present_count >= 2:
            return 'fair'
        else:
            return 'poor'
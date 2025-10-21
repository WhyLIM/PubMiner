# -*- coding: utf-8 -*-
"""
文本提取模块

负责从PMC全文和PDF文件中提取文本内容
包含智能章节筛选和文本优化功能
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re

from utils.logger import LoggerMixin
from utils.file_handler import FileHandler
from utils.api_manager import api_manager

logger = logging.getLogger(__name__)

class TextExtractor(LoggerMixin):
    """文本提取器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化文本提取器
        
        Args:
            config: 提取配置
        """
        self.config = config
        self.text_limit = config.get('text_limit', 15000)
        self.section_filters = config.get('section_filters', [])
        self.exclude_sections = config.get('exclude_sections', [])
        self.key_section_ratio = config.get('key_section_ratio', {})
        
        # 延迟导入重量级库
        self._fitz = None
        self._pdf2image = None
        self._pytesseract = None
        self._PIL_Image = None
    
    def _import_pdf_libraries(self):
        """延迟导入PDF处理库"""
        if self._fitz is None:
            try:
                import fitz
                self._fitz = fitz
                self.logger.debug("✅ 成功导入PyMuPDF库")
            except ImportError:
                self.logger.warning("⚠️ PyMuPDF库未安装，PDF处理功能将受限")
        
        if self._pdf2image is None:
            try:
                from pdf2image import convert_from_path
                self._pdf2image = convert_from_path
                self.logger.debug("✅ 成功导入pdf2image库")
            except ImportError:
                self.logger.warning("⚠️ pdf2image库未安装，OCR功能将受限")
        
        if self._pytesseract is None:
            try:
                import pytesseract
                self._pytesseract = pytesseract
                self.logger.debug("✅ 成功导入pytesseract库")
            except ImportError:
                self.logger.warning("⚠️ pytesseract库未安装，OCR功能将受限")
        
        if self._PIL_Image is None:
            try:
                from PIL import Image
                self._PIL_Image = Image
                self.logger.debug("✅ 成功导入PIL库")
            except ImportError:
                self.logger.warning("⚠️ PIL库未安装，图像处理功能将受限")
    
    def fetch_bioc_document(self, pmid: str, format_type: str = "json", 
                           encoding: str = "unicode") -> Optional[Dict[str, Any]]:
        """
        从NCBI BioC API获取生物医学文献数据
        
        Args:
            pmid: 文献PMID
            format_type: 返回格式，'xml' 或 'json'
            encoding: 编码格式，'unicode' 或 'ascii'
            
        Returns:
            BioC文档的JSON对象，失败返回None
        """
        url = f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_{format_type}/{pmid}/{encoding}"
        
        try:
            self.logger.debug(f"正在获取PMID {pmid} 的BioC数据...")
            
            response = api_manager.get(
                url,
                timeout=30,
                api_name='pubmed_no_key'  # BioC API没有key限制，使用较宽松的限流
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    self.logger.debug(f"✅ 成功获取PMID {pmid} 的BioC数据")
                    return data[0]
                else:
                    self.logger.warning(f"⚠️ PMID {pmid} 的BioC数据格式异常")
                    return None
            else:
                self.logger.warning(f"⚠️ 获取PMID {pmid} 的BioC数据失败，状态码: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.warning(f"⚠️ 获取PMID {pmid} 的BioC数据时出错: {e}")
            return None
    
    def extract_meta_info(self, bioc_document: Dict[str, Any]) -> str:
        """
        从BioC文档中提取元数据信息
        
        Args:
            bioc_document: BioC文档JSON
            
        Returns:
            格式化的元数据字符串
        """
        try:
            for passage in bioc_document["documents"][0]["passages"]:
                if passage["infons"]["section_type"] == "TITLE":
                    metadata = passage["infons"]
                    
                    # 处理关键词
                    keywords = metadata.get('kwd', 'N/A')
                    
                    # 处理作者信息
                    authors = [value for key, value in metadata.items() if key.startswith('name_')]
                    formatted_authors = []
                    for author in authors:
                        parts = author.split(';')
                        surname = parts[0].split(':')[1] if ':' in parts[0] else parts[0]
                        if len(parts) > 1 and ':' in parts[1]:
                            given_names = parts[1].split(':')[1]
                            formatted_name = f"{given_names} {surname}"
                        else:
                            formatted_name = surname
                        formatted_authors.append(formatted_name)
                    
                    # 获取其他元数据字段
                    doi = metadata.get('article-id_doi', 'N/A')
                    pmid = metadata.get('article-id_pmid', 'N/A')
                    pmcid = metadata.get('article-id_pmc', 'N/A')
                    year = metadata.get('year', 'N/A')
                    source = metadata.get('source', 'N/A')
                    volume = metadata.get('volume', 'N/A')
                    issue = metadata.get('issue', 'N/A')
                    
                    # 格式化元数据文本
                    meta_text = f"""标题: {passage['text']}
DOI: {doi}
PMID: {pmid}
PMCID: PMC{pmcid}
年份: {year}
期刊: {source}, 卷号 {volume}, 期号 {issue}
关键词: {keywords}
作者: {', '.join(formatted_authors)}"""
                    
                    return meta_text
                    
        except Exception as e:
            self.logger.warning(f"提取元数据信息时出错: {e}")
        
        return "元数据提取失败"
    
    def extract_full_text_from_bioc(self, bioc_document: Dict[str, Any]) -> str:
        """
        从BioC文档中提取全文内容
        
        Args:
            bioc_document: BioC文档JSON
            
        Returns:
            全文内容字符串
        """
        try:
            # 获取所有章节类型
            section_types = []
            for passage in bioc_document["documents"][0]["passages"]:
                section_type = passage["infons"]["section_type"]
                if (section_type not in section_types and 
                    section_type not in self.exclude_sections):
                    section_types.append(section_type)
            
            self.logger.debug(f"提取章节类型: {section_types}")
            
            # 按章节提取文本
            full_text = ""
            section_texts = {}
            
            for section_type in section_types:
                section_text = ""
                for passage in bioc_document["documents"][0]["passages"]:
                    if passage["infons"]["section_type"] == section_type:
                        section_text += passage["text"] + "\n\n"
                
                if section_text.strip():
                    section_texts[section_type] = section_text
                    full_text += f"\n\n===== {section_type} =====\n{section_text}"
            
            return full_text.strip()
            
        except Exception as e:
            self.logger.error(f"从BioC文档提取全文时出错: {e}")
            return ""
    
    def extract_from_pdf(self, pdf_path: Union[str, Path], min_chars: int = 1000) -> str:
        """
        从PDF文件提取文本
        
        Args:
            pdf_path: PDF文件路径
            min_chars: 最小字符数阈值
            
        Returns:
            提取的文本内容
        """
        self._import_pdf_libraries()
        
        if self._fitz is None:
            self.logger.error("❌ PyMuPDF库未安装，无法处理PDF文件")
            return ""
        
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            self.logger.error(f"❌ PDF文件不存在: {pdf_path}")
            return ""
        
        try:
            self.logger.debug(f"🔍 尝试直接提取PDF文本: {pdf_path.name}")
            
            # 尝试直接提取文本
            doc = self._fitz.open(str(pdf_path))
            text = "\n".join([page.get_text() for page in doc])
            doc.close()
            
            effective_chars = len(''.join(text.split()))
            zh_count = sum('\u4e00' <= c <= '\u9fff' for c in text)
            en_count = sum(c.isalpha() for c in text)
            
            self.logger.debug(f"提取到 {len(text)} 个字符（有效: {effective_chars}, 中文: {zh_count}, 英文: {en_count}）")
            
            # 判断提取质量
            if (effective_chars >= min_chars or 
                (effective_chars > 500 and (zh_count > 100 or en_count > 300))):
                self.logger.debug(f"✅ PDF文本提取成功")
                return text
            
            # 如果文本质量不够，尝试OCR
            self.logger.debug(f"⚠️ 提取文本质量不足，尝试OCR...")
            return self._ocr_from_pdf(pdf_path)
            
        except Exception as e:
            self.logger.error(f"❌ PDF文本提取失败: {e}")
            return ""
    
    def _ocr_from_pdf(self, pdf_path: Path) -> str:
        """
        使用OCR从PDF提取文本
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            OCR识别的文本
        """
        if (self._pdf2image is None or self._pytesseract is None or 
            self._PIL_Image is None):
            self.logger.warning("⚠️ OCR相关库未安装，跳过OCR处理")
            return ""
        
        try:
            self.logger.debug(f"🔍 开始OCR识别: {pdf_path.name}")
            
            # 转换PDF为图像
            images = self._pdf2image(str(pdf_path), dpi=200)
            text_all = ""
            
            for idx, img in enumerate(images, 1):
                self.logger.debug(f"正在识别第 {idx}/{len(images)} 页...")
                try:
                    # 使用中英文混合识别
                    text = self._pytesseract.image_to_string(img, lang='chi_sim+eng')
                    text_all += f"\n---- 第{idx}页 ----\n{text}\n"
                except Exception as e:
                    self.logger.warning(f"第{idx}页OCR识别失败: {e}")
                    continue
            
            self.logger.debug(f"✅ OCR识别完成，提取了 {len(text_all)} 个字符")
            return text_all
            
        except Exception as e:
            self.logger.error(f"❌ OCR识别失败: {e}")
            return ""
    
    def _identify_key_sections(self, text: str) -> Dict[str, str]:
        """
        识别文本中的关键章节
        
        Args:
            text: 原始文本
            
        Returns:
            章节字典 {章节名: 章节内容}
        """
        sections = {}
        
        # 定义章节关键词模式
        section_patterns = {
            'abstract': [r'abstract', r'摘要', r'summary'],
            'introduction': [r'introduction', r'引言', r'前言', r'背景'],
            'methods': [r'methods?', r'methodology', r'材料与方法', r'方法'],
            'results': [r'results?', r'findings', r'结果'],
            'discussion': [r'discussion', r'讨论', r'分析'],
            'conclusion': [r'conclusions?', r'结论', r'总结']
        }
        
        text_lower = text.lower()
        
        for section_name, patterns in section_patterns.items():
            for pattern in patterns:
                # 查找章节标题
                matches = re.finditer(rf'\b{pattern}\b', text_lower, re.IGNORECASE)
                
                for match in matches:
                    start_pos = match.start()
                    
                    # 确保是章节标题（前面有换行或开头）
                    if start_pos > 0 and text[start_pos-1] not in '\n\r':
                        continue
                    
                    # 查找章节结束位置
                    end_pos = len(text)
                    for other_section, other_patterns in section_patterns.items():
                        if other_section == section_name:
                            continue
                        for other_pattern in other_patterns:
                            other_matches = re.finditer(rf'\b{other_pattern}\b', 
                                                      text_lower[start_pos+100:], 
                                                      re.IGNORECASE)
                            for other_match in other_matches:
                                candidate_end = start_pos + 100 + other_match.start()
                                if candidate_end < end_pos:
                                    end_pos = candidate_end
                                break
                    
                    # 提取章节内容
                    section_content = text[start_pos:end_pos].strip()
                    if len(section_content) > 100:  # 最小章节长度
                        sections[section_name] = section_content
                        break
                
                if section_name in sections:
                    break
        
        return sections
    
    def filter_and_optimize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """
        智能筛选和优化文本内容
        
        Args:
            text: 原始文本
            max_length: 最大长度限制
            
        Returns:
            优化后的文本
        """
        if not text or not text.strip():
            return ""
        
        max_length = max_length or self.text_limit
        
        if len(text) <= max_length:
            return text
        
        self.logger.debug(f"文本过长（{len(text)}字符），开始智能优化...")
        
        # 识别关键章节
        key_sections = self._identify_key_sections(text)
        
        if not key_sections:
            # 如果没有识别到章节，使用头尾截取
            head_length = min(max_length // 3, 5000)
            tail_length = min(max_length - head_length, 3000)
            
            optimized_text = (text[:head_length] + 
                            "\n\n[... 中间部分已省略 ...]\n\n" + 
                            text[-tail_length:])
            
            self.logger.debug(f"使用头尾截取，保留 {len(optimized_text)} 字符")
            return optimized_text
        
        # 按优先级选择章节
        section_priority = ['abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion']
        selected_sections = []
        used_length = 0
        
        for section_name in section_priority:
            if section_name in key_sections:
                section_content = key_sections[section_name]
                if used_length + len(section_content) <= max_length:
                    selected_sections.append((section_name, section_content))
                    used_length += len(section_content)
                else:
                    # 部分截取
                    remaining_length = max_length - used_length
                    if remaining_length > 500:  # 至少保留500字符
                        truncated_content = section_content[:remaining_length-50] + "..."
                        selected_sections.append((section_name, truncated_content))
                    break
        
        # 组合优化后的文本
        optimized_text = ""
        for section_name, section_content in selected_sections:
            optimized_text += f"\n\n===== {section_name.upper()} =====\n{section_content}"
        
        self.logger.debug(f"智能优化完成，保留 {len(optimized_text)} 字符")
        return optimized_text.strip()
    
    def extract_text_from_paper(self, paper: Dict[str, Any], text_limit: Optional[int] = None) -> Dict[str, Any]:
        """
        从单篇文献中提取文本
        
        Args:
            paper: 文献记录
            text_limit: 文本长度限制
            
        Returns:
            包含全文的文献记录
        """
        pmid = paper.get('PMID', '')
        title = paper.get('Title', 'Unknown')
        
        self.logger.debug(f"🔍 提取文献文本: {pmid} - {title[:50]}...")
        
        full_text = ""
        text_source = "none"
        
        # 优先尝试从PMC获取全文
        if pmid:
            bioc_doc = self.fetch_bioc_document(pmid)
            if bioc_doc:
                meta_info = self.extract_meta_info(bioc_doc)
                full_text = self.extract_full_text_from_bioc(bioc_doc)
                if full_text:
                    full_text = meta_info + "\n\n" + full_text
                    text_source = "pmc"
                    self.logger.debug(f"✅ 从PMC获取全文成功: {len(full_text)} 字符")
        
        # 如果PMC没有全文，尝试从PDF获取（如果提供了PDF路径）
        if not full_text and 'pdf_path' in paper:
            pdf_path = paper['pdf_path']
            if pdf_path and Path(pdf_path).exists():
                full_text = self.extract_from_pdf(pdf_path)
                if full_text:
                    text_source = "pdf"
                    self.logger.debug(f"✅ 从PDF获取全文成功: {len(full_text)} 字符")
        
        # 如果都没有全文，使用摘要
        if not full_text:
            abstract = paper.get('Abstract', '')
            if abstract and abstract != 'NA':
                full_text = f"标题: {title}\n\n摘要: {abstract}"
                text_source = "abstract"
                self.logger.debug(f"✅ 使用摘要作为文本: {len(full_text)} 字符")
        
        # 优化文本长度
        if full_text:
            full_text = self.filter_and_optimize_text(full_text, text_limit or self.text_limit)
        
        # 更新文献记录
        paper_with_text = paper.copy()
        paper_with_text.update({
            'full_text': full_text,
            'text_source': text_source,
            'text_length': len(full_text) if full_text else 0
        })
        
        return paper_with_text
    
    def extract_batch(self, papers: List[Dict[str, Any]], 
                     max_workers: int = 4, 
                     text_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        批量提取文献文本
        
        Args:
            papers: 文献列表
            max_workers: 最大并发数
            text_limit: 文本长度限制
            
        Returns:
            包含全文的文献列表
        """
        self.logger.info(f"📄 开始批量提取文本，共 {len(papers)} 篇文献")
        
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交任务
            future_to_paper = {
                executor.submit(self.extract_text_from_paper, paper, text_limit): paper
                for paper in papers
            }
            
            # 收集结果
            for future in as_completed(future_to_paper):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    paper = future_to_paper[future]
                    pmid = paper.get('PMID', 'Unknown')
                    self.logger.error(f"❌ 提取文献 {pmid} 的文本失败: {e}")
                    # 添加失败记录
                    paper_with_error = paper.copy()
                    paper_with_error.update({
                        'full_text': '',
                        'text_source': 'error',
                        'text_length': 0,
                        'extraction_error': str(e)
                    })
                    results.append(paper_with_error)
        
        # 统计结果
        successful = len([r for r in results if r.get('full_text')])
        self.logger.info(f"✅ 文本提取完成: {successful}/{len(papers)} 篇成功")
        
        return results
# -*- coding: utf-8 -*-
"""
文本提取模块

负责从 PMC 全文和 PDF 文件中提取文本内容
包含智能章节筛选和文本优化功能
"""

import os
import json
import time
import requests
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
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
        self.text_limit = config.get('text_limit', -1)
        self.section_filters = config.get('section_filters', [])
        self.exclude_sections = config.get('exclude_sections', [])
        self.key_section_ratio = config.get('key_section_ratio', {})

        # BioC API 缓存配置
        self.enable_bioc_cache = config.get('enable_bioc_cache', True)
        self.cache_dir = Path(config.get('cache_dir', 'cache/bioc'))
        self.cache_ttl = config.get('cache_ttl', 86400)  # 24 小时

        # 确保缓存目录存在
        if self.enable_bioc_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 延迟导入重量级库
        self._fitz = None
        self._pdf2image = None
        self._pytesseract = None
        self._PIL_Image = None

    def _get_bioc_cache_path(self, pmid: str, format_type: str = "json") -> Path:
        """
        获取 BioC 文档缓存路径

        Args:
            pmid: 文献 PMID
            format_type: 文档格式

        Returns:
            缓存文件路径
        """
        # 使用 PMID 和格式类型生成唯一的缓存文件名
        cache_key = f"{pmid}_{format_type}"
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
        return self.cache_dir / f"bioc_{cache_hash}.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """
        检查缓存文件是否有效

        Args:
            cache_path: 缓存文件路径

        Returns:
            是否有效
        """
        if not cache_path.exists():
            return False

        # 检查文件修改时间
        file_age = time.time() - cache_path.stat().st_mtime
        return file_age < self.cache_ttl

    def _load_cached_bioc_document(self, pmid: str, format_type: str = "json") -> Optional[Dict[str, Any]]:
        """
        从缓存加载 BioC 文档

        Args:
            pmid: 文献 PMID
            format_type: 文档格式

        Returns:
            BioC 文档或 None
        """
        if not self.enable_bioc_cache:
            return None

        cache_path = self._get_bioc_cache_path(pmid, format_type)

        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    document = json.load(f)
                self.logger.debug(f"从缓存加载 BioC 文档: PMID {pmid}")
                return document
            except Exception as e:
                self.logger.warning(f"加载缓存文档失败: {e}")
                # 删除损坏的缓存文件
                try:
                    cache_path.unlink()
                except:
                    pass

        return None

    def _cache_bioc_document(self, pmid: str, document: Dict[str, Any], format_type: str = "json") -> None:
        """
        缓存 BioC 文档

        Args:
            pmid: 文献 PMID
            document: BioC 文档
            format_type: 文档格式
        """
        if not self.enable_bioc_cache:
            return

        try:
            cache_path = self._get_bioc_cache_path(pmid, format_type)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(document, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"BioC 文档已缓存: PMID {pmid}")
        except Exception as e:
            self.logger.warning(f"缓存 BioC 文档失败: {e}")

    def _validate_bioc_document(self, document: Dict[str, Any]) -> bool:
        """
        验证 BioC 文档结构

        Args:
            document: BioC 文档

        Returns:
            是否有效
        """
        try:
            # 检查基本结构
            if not isinstance(document, dict):
                return False

            if "documents" not in document or not isinstance(document["documents"], list):
                return False

            if len(document["documents"]) == 0:
                return False

            doc = document["documents"][0]
            if "passages" not in doc or not isinstance(doc["passages"], list):
                return False

            # 检查是否有必要的章节
            has_title = any(passage.get("infons", {}).get("section_type") == "TITLE" for passage in doc["passages"])

            return True

        except Exception:
            return False

    def _import_pdf_libraries(self):
        """延迟导入 PDF 处理库"""
        if self._fitz is None:
            try:
                import fitz
                self._fitz = fitz
                self.logger.debug("✅ 成功导入 PyMuPDF 库")
            except ImportError:
                self.logger.warning("⚠️ PyMuPDF 库未安装， PDF 处理功能将受限")

        if self._pdf2image is None:
            try:
                from pdf2image import convert_from_path
                self._pdf2image = convert_from_path
                self.logger.debug("✅ 成功导入 pdf2image 库")
            except ImportError:
                self.logger.warning("⚠️ pdf2image 库未安装， OCR 功能将受限")

        if self._pytesseract is None:
            try:
                import pytesseract
                self._pytesseract = pytesseract
                self.logger.debug("✅ 成功导入 pytesseract 库")
            except ImportError:
                self.logger.warning("⚠️ pytesseract 库未安装， OCR 功能将受限")

        if self._PIL_Image is None:
            try:
                from PIL import Image
                self._PIL_Image = Image
                self.logger.debug("✅ 成功导入 PIL 库")
            except ImportError:
                self.logger.warning("⚠️ PIL 库未安装，图像处理功能将受限")

    def fetch_bioc_document(self,
                            pmid: str,
                            format_type: str = "json",
                            encoding: str = "unicode",
                            max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        从 NCBI BioC API 获取生物医学文献数据

        Args:
            pmid: 文献 PMID
            format_type: 返回格式，'xml' 或'json'
            encoding: 编码格式，'unicode' 或'ascii'
            max_retries: 最大重试次数

        Returns:
            BioC 文档的 JSON 对象，失败返回 None
        """
        # 首先尝试从缓存加载
        cached_doc = self._load_cached_bioc_document(pmid, format_type)
        if cached_doc and self._validate_bioc_document(cached_doc):
            return cached_doc

        url = f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_{format_type}/{pmid}/{encoding}"

        for attempt in range(max_retries):
            try:
                self.logger.debug(f"正在获取 PMID {pmid} 的 BioC 数据 ... (尝试 {attempt + 1}/{max_retries})")

                response = api_manager.get(
                    url,
                    timeout=30,
                    api_name='pubmed_no_key'  # BioC API 没有 key 限制，使用较宽松的限流
                )

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        document = data[0]

                        # 验证文档结构
                        if self._validate_bioc_document(document):
                            # 缓存有效文档
                            self._cache_bioc_document(pmid, document, format_type)
                            self.logger.debug(f"✅ 成功获取并验证 PMID {pmid} 的 BioC 数据")
                            return document
                        else:
                            self.logger.warning(f"⚠️ PMID {pmid} 的 BioC 文档结构验证失败")
                            return None
                    else:
                        self.logger.warning(f"⚠️ PMID {pmid} 的 BioC 数据格式异常")
                        return None
                else:
                    # 处理特定的 HTTP 状态码
                    if response.status_code == 404:
                        self.logger.info(f"📄 PMID {pmid} 无可用 PMC 全文")
                        return None
                    elif response.status_code == 429:
                        self.logger.warning(f"⚠️ API 请求频率限制，等待后重试 ...")
                        if attempt < max_retries - 1:
                            time.sleep(2**attempt)  # 指数退避
                            continue
                    elif response.status_code >= 500:
                        self.logger.warning(f"⚠️ 服务器错误，状态码: {response.status_code}")
                        if attempt < max_retries - 1:
                            time.sleep(2**attempt)
                            continue
                    else:
                        self.logger.warning(f"⚠️ 获取 PMID {pmid} 的 BioC 数据失败，状态码: {response.status_code}")
                        return None

            except requests.exceptions.Timeout:
                self.logger.warning(f"⚠️ 获取 PMID {pmid} 的 BioC 数据超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"⚠️ 网络连接错误 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
            except Exception as e:
                self.logger.warning(f"⚠️ 获取 PMID {pmid} 的 BioC 数据时出错: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

        self.logger.error(f"❌ 获取 PMID {pmid} 的 BioC 数据最终失败")
        return None

    def extract_meta_info(self, bioc_document: Dict[str, Any]) -> str:
        """
        从 BioC 文档中提取元数据信息

        Args:
            bioc_document: BioC 文档 JSON

        Returns:
            格式化的元数据字符串
        """
        try:
            # 验证文档结构
            if not self._validate_bioc_document(bioc_document):
                return "文档结构验证失败"

            doc = bioc_document["documents"][0]
            title_passage = None

            # 查找标题章节
            for passage in doc["passages"]:
                if passage.get("infons", {}).get("section_type") == "TITLE":
                    title_passage = passage
                    break

            if not title_passage:
                return "未找到标题章节"

            metadata = title_passage["infons"]
            title_text = title_passage.get("text", "无标题").strip()

            # 安全获取关键词
            keywords = self._safe_get_metadata_field(metadata, 'kwd', 'N/A')
            if isinstance(keywords, list):
                keywords = ';'.join(str(k) for k in keywords)

            # 处理作者信息
            authors = self._extract_authors_from_metadata(metadata)

            # 获取其他元数据字段
            doi = self._safe_get_metadata_field(metadata, 'article-id_doi', 'N/A')
            pmid = self._safe_get_metadata_field(metadata, 'article-id_pmid', 'N/A')
            pmcid = self._safe_get_metadata_field(metadata, 'article-id_pmc', 'N/A')
            year = self._safe_get_metadata_field(metadata, 'year', 'N/A')
            source = self._safe_get_metadata_field(metadata, 'source', 'N/A')
            volume = self._safe_get_metadata_field(metadata, 'volume', 'N/A')
            issue = self._safe_get_metadata_field(metadata, 'issue', 'N/A')

            # 格式化元数据文本
            meta_text = f"""标题: {title_text}
                            DOI: {doi}
                            PMID: {pmid}
                            PMCID: PMC{pmcid}
                            年份: {year}
                            期刊: {source}, 卷号 {volume}, 期号 {issue}
                            关键词: {keywords}
                            作者: {','.join(authors) if authors else 'N/A'}"""

            return meta_text

        except Exception as e:
            self.logger.warning(f"提取元数据信息时出错: {e}")
            return f"元数据提取失败: {str(e)}"

    def _safe_get_metadata_field(self, metadata: Dict[str, Any], field: str, default: str = 'N/A') -> str:
        """
        安全获取元数据字段

        Args:
            metadata: 元数据字典
            field: 字段名
            default: 默认值

        Returns:
            字段值或默认值
        """
        try:
            value = metadata.get(field, default)
            if value is None or value == '':
                return default
            return str(value).strip()
        except Exception:
            return default

    def _extract_authors_from_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """
        从元数据中提取作者信息

        Args:
            metadata: 元数据字典

        Returns:
            格式化的作者列表
        """
        authors = []

        try:
            # 查找所有作者字段
            author_fields = {key: value for key, value in metadata.items() if key.startswith('name_')}

            # 按编号排序
            sorted_fields = sorted(author_fields.items(), key=lambda x: x[0])

            for key, value in sorted_fields:
                if not value:
                    continue

                # 解析作者信息格式：surname:given_name;initials
                parts = value.split(';')
                surname = parts[0].split(':')[1] if ':' in parts[0] else parts[0]
                surname = surname.strip()

                if len(parts) > 1 and ':' in parts[1]:
                    given_names = parts[1].split(':')[1].strip()
                    formatted_name = f"{given_names} {surname}"
                else:
                    formatted_name = surname

                authors.append(formatted_name)

        except Exception as e:
            self.logger.warning(f"解析作者信息时出错: {e}")

        return authors

    def extract_full_text_from_bioc(self, bioc_document: Dict[str, Any]) -> str:
        """
        从 BioC 文档中提取全文内容

        Args:
            bioc_document: BioC 文档 JSON

        Returns:
            全文内容字符串
        """
        try:
            # 验证文档结构
            if not self._validate_bioc_document(bioc_document):
                self.logger.warning("BioC 文档结构验证失败，无法提取全文")
                return ""

            doc = bioc_document["documents"][0]
            passages = doc.get("passages", [])

            if not passages:
                self.logger.warning("文档中没有找到任何章节")
                return ""

            # 获取所有章节类型并排序
            section_types = self._get_ordered_section_types(passages)
            self.logger.debug(f"提取章节类型: {section_types}")

            # 按章节提取文本
            section_texts = {}
            total_chars = 0

            for section_type in section_types:
                section_text = self._extract_section_text(passages, section_type)
                if section_text.strip():
                    section_texts[section_type] = section_text
                    total_chars += len(section_text)

                    # 检查文本长度限制
                    if self.text_limit > 0 and total_chars > self.text_limit:
                        self.logger.debug(f"达到文本长度限制 ({self.text_limit})，停止提取")
                        break

            # 组装全文内容
            full_text = self._assemble_full_text(section_texts)

            self.logger.info(f"成功提取全文，共 {len(full_text)} 字符，{len(section_texts)} 个章节")
            return full_text.strip()

        except Exception as e:
            self.logger.error(f"从 BioC 文档提取全文时出错: {e}")
            return ""

    def _get_ordered_section_types(self, passages: List[Dict[str, Any]]) -> List[str]:
        """
        获取按优先级排序的章节类型

        Args:
            passages: BioC 章节列表

        Returns:
            排序后的章节类型列表
        """
        section_types = []
        seen_types = set()

        # 定义章节优先级顺序
        section_priority = [
            "TITLE", "ABSTRACT", "INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL", "ACK_FUND", "REF", "FIG", "TABLE", "SUPPL"
        ]

        # 收集所有章节类型
        for passage in passages:
            section_type = passage.get("infons", {}).get("section_type", "")
            if (section_type and section_type not in seen_types and section_type not in self.exclude_sections):
                section_types.append(section_type)
                seen_types.add(section_type)

        # 按优先级排序
        def get_priority(section_type):
            section_type_upper = section_type.upper()
            for i, priority in enumerate(section_priority):
                if priority in section_type_upper:
                    return i
            return len(section_priority)  # 未定义优先级的章节放在最后

        return sorted(section_types, key=get_priority)

    def _extract_section_text(self, passages: List[Dict[str, Any]], section_type: str) -> str:
        """
        提取特定章节的文本

        Args:
            passages: BioC 章节列表
            section_type: 章节类型

        Returns:
            章节文本
        """
        section_text = ""

        for passage in passages:
            if passage.get("infons", {}).get("section_type") == section_type:
                text = passage.get("text", "").strip()
                if text:
                    section_text += text + "\n\n"

        return section_text.strip()

    def _assemble_full_text(self, section_texts: Dict[str, str]) -> str:
        """
        组装全文内容

        Args:
            section_texts: 章节文本字典

        Returns:
            组装后的全文
        """
        full_text_parts = []

        for section_type, text in section_texts.items():
            # 格式化章节标题
            section_title = self._format_section_title(section_type)
            full_text_parts.append(f"\n\n{section_title}\n{text}")

        return "".join(full_text_parts)

    def _format_section_title(self, section_type: str) -> str:
        """
        格式化章节标题

        Args:
            section_type: 章节类型

        Returns:
            格式化的章节标题
        """
        # 章节类型映射到中文显示名称
        section_names = {
            "ABSTRACT": "ABSTRACT",
            "TITLE": "TITLE",
            "INTRO": "INTRODUCTION",
            "INTRODUCTION": "INTRODUCTION",
            "METHODS": "METHODS",
            "METHOD": "METHODS",
            "RESULTS": "RESULTS",
            "DISCUSS": "DISCUSSION",
            "DISCUSSION": "DISCUSSION",
            "CONCL": "CONCLUSION",
            "CONCLUSION": "CONCLUSION",
            "ACK": "ACKNOWLEDGMENTS",
            "ACK_FUND": "ACKNOWLEDGMENTS",
            "ACKNOWLEDGMENTS": "ACKNOWLEDGMENTS",
            "REF": "REFERENCES",
            "REFERENCES": "REFERENCES",
            "FIG": "FIGURES",
            "FIGURES": "FIGURES",
            "TAB": "TABLE",
            "TABLE": "TABLE",
            "SUPPL": "SUPPLEMENTARY",
            "SUPPLEMENTARY": "SUPPLEMENTARY"
        }

        # 获取章节显示名称，默认使用原文
        display_name = section_names.get(section_type.upper(), section_type)

        return f"===== {display_name} ====="

    def extract_from_pdf(self, pdf_path: Union[str, Path], min_chars: int = 1000) -> str:
        """
        从 PDF 文件提取文本

        Args:
            pdf_path: PDF 文件路径
            min_chars: 最小字符数阈值

        Returns:
            提取的文本内容
        """
        self._import_pdf_libraries()

        if self._fitz is None:
            self.logger.error("❌ PyMuPDF 库未安装，无法处理 PDF 文件")
            return ""

        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            self.logger.error(f"❌ PDF 文件不存在 : {pdf_path}")
            return ""

        try:
            self.logger.debug(f"🔍 尝试直接提取 PDF 文本 : {pdf_path.name}")

            # 尝试直接提取文本
            doc = self._fitz.open(str(pdf_path))
            text = "\n".join([page.get_text() for page in doc])
            doc.close()

            effective_chars = len(''.join(text.split()))
            zh_count = sum('\u4e00' <= c <= '\u9fff' for c in text)
            en_count = sum(c.isalpha() for c in text)

            self.logger.debug(f"提取到 {len(text)} 个字符（有效 : {effective_chars}, 中文 : {zh_count}, 英文 : {en_count}）")

            # 判断提取质量
            if (effective_chars >= min_chars or (effective_chars > 500 and (zh_count > 100 or en_count > 300))):
                self.logger.debug(f"✅ PDF 文本提取成功")
                return text

            # 如果文本质量不够，尝试 OCR
            self.logger.debug(f"⚠️ 提取文本质量不足，尝试 OCR...")
            return self._ocr_from_pdf(pdf_path)

        except Exception as e:
            self.logger.error(f"❌ PDF 文本提取失败 : {e}")
            return ""

    def _ocr_from_pdf(self, pdf_path: Path) -> str:
        """
        使用 OCR 从 PDF 提取文本

        Args:
            pdf_path: PDF 文件路径

        Returns:
            OCR 识别的文本
        """
        if (self._pdf2image is None or self._pytesseract is None or self._PIL_Image is None):
            self.logger.warning("⚠️ OCR 相关库未安装，跳过 OCR 处理")
            return ""

        try:
            self.logger.debug(f"🔍 开始 OCR 识别 : {pdf_path.name}")

            # 转换 PDF 为图像
            images = self._pdf2image(str(pdf_path), dpi=200)
            text_all = ""

            for idx, img in enumerate(images, 1):
                self.logger.debug(f"正在识别第 {idx}/{len(images)} 页 ...")
                try:
                    # 使用中英文混合识别
                    text = self._pytesseract.image_to_string(img, lang='chi_sim+eng')
                    text_all += f"\n---- 第 {idx} 页 ----\n{text}\n"
                except Exception as e:
                    self.logger.warning(f"第 {idx} 页 OCR 识别失败 : {e}")
                    continue

            self.logger.debug(f"✅ OCR 识别完成，提取了 {len(text_all)} 个字符")
            return text_all

        except Exception as e:
            self.logger.error(f"❌ OCR 识别失败 : {e}")
            return ""

    def _identify_key_sections(self, text: str) -> Dict[str, str]:
        """
        识别文本中的关键章节

        Args:
            text: 原始文本 (string)

        Returns:
            章节字典 Dict[str, str]: {section_name: section_content}
        """
        # === 1. 标准化文本 ===
        text = re.sub(r'\r', '\n', text)  # 标准化换行符
        text = re.sub(r'\n{2,}', '\n\n', text)  # 折叠多余的空行
        text_lower = text.lower()

        # === 2. 定义部分关键词模式 ===
        section_patterns = {
            "abstract": [r"abstract", r"summary"],
            "introduction": [r"introduction", r"background", r"objective[s]?", r"aim[s]?"],
            "methods": [r"materials and methods", r"methods?", r"methodology", r"study design", r"experimental procedures"],
            "results": [r"results?", r"findings", r"outcomes", r"observations"],
            "discussion": [r"discussion", r"interpretation", r"analysis"],
            "conclusion": [r"conclusion[s]?", r"summary", r"final remarks"],
            "acknowledgments": [r"acknowledg?ments?", r"funding", r"support"],
            "references": [r"references", r"bibliography"],
        }

        # === 3. 定位所有章节标题 ===
        matches: List[Tuple[str, int]] = []
        for name, patterns in section_patterns.items():
            for pat in patterns:
                # 匹配标题如 "Introduction", "Introduction:"，或行首
                regex = rf"(^|\n)\s*{pat}\s*[:.]?\s*(\n|$)"
                for m in re.finditer(regex, text_lower):
                    matches.append((name, m.start()))

        if not matches:
            return {}

        # === 4. 按位置排序 ===
        matches.sort(key=lambda x: x[1])

        # === 5. 提取章节 ===
        sections: Dict[str, str] = {}
        for i, (name, start_pos) in enumerate(matches):
            end_pos = matches[i + 1][1] if i + 1 < len(matches) else len(text)
            section_text = text[start_pos:end_pos].strip()
            # 过滤误报的最小内容长度（降低阈值以提高兼容性）
            if len(section_text) > 20:  # 从 100 降低到 20 ，提高兼容性
                sections[name] = section_text

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

        self.logger.debug(f"文本过长（{len(text)} 字符），开始智能优化 ...")

        # 识别关键章节
        key_sections = self._identify_key_sections(text)

        if not key_sections:
            # 如果没有识别到章节，使用头尾截取
            head_length = min(max_length // 3, 5000)
            tail_length = min(max_length - head_length, 3000)

            optimized_text = (text[:head_length] + "\n\n[... 中间部分已省略 ...]\n\n" + text[-tail_length:])

            self.logger.debug(f"使用头尾截取，保留 {len(optimized_text)} 字符")
            return optimized_text

        # 按优先级选择章节
        section_priority = ['abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion']
        selected_sections = []
        used_length = 0

        for section_name in section_priority:
            if section_name in key_sections:
                section_content = key_sections[section_name]
                # 计算添加分隔符后的总长度（包括换行符）
                separator_length = len("\\n\\n=====" + section_name.upper() + "=====\\n")
                total_section_length = len(section_content) + separator_length

                if used_length + total_section_length <= max_length:
                    selected_sections.append((section_name, section_content))
                    used_length += total_section_length
                else:
                    # 部分截取
                    remaining_length = max_length - used_length - separator_length
                    if remaining_length > 100:  # 至少保留 100 字符
                        truncated_content = section_content[:remaining_length - 3] + "..."
                        selected_sections.append((section_name, truncated_content))
                        used_length += len(truncated_content) + separator_length
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

        self.logger.debug(f"🔍 提取文献文本 : {pmid} - {title[:50]}...")

        full_text = ""
        text_source = "none"

        # 优先尝试从 PMC 获取全文
        if pmid:
            bioc_doc = self.fetch_bioc_document(pmid)
            if bioc_doc:
                meta_info = self.extract_meta_info(bioc_doc)
                full_text = self.extract_full_text_from_bioc(bioc_doc)
                if full_text:
                    full_text = meta_info + "\n\n" + full_text
                    text_source = "pmc"
                    self.logger.debug(f"✅ 从 PMC 获取全文成功 : {len(full_text)} 字符")

        # 如果 PMC 没有全文，尝试从 PDF 获取（如果提供了 PDF 路径）
        if not full_text and 'pdf_path' in paper:
            pdf_path = paper['pdf_path']
            if pdf_path and Path(pdf_path).exists():
                full_text = self.extract_from_pdf(pdf_path)
                if full_text:
                    text_source = "pdf"
                    self.logger.debug(f"✅ 从 PDF 获取全文成功 : {len(full_text)} 字符")

        # 如果都没有全文，使用摘要
        if not full_text:
            abstract = paper.get('Abstract', '')
            if abstract and abstract != 'NA':
                full_text = f"标题 : {title}\n\n 摘要 : {abstract}"
                text_source = "abstract"
                self.logger.debug(f"✅ 使用摘要作为文本 : {len(full_text)} 字符")

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

    def extract_batch(self,
                      papers: List[Dict[str, Any]],
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
            future_to_paper = {executor.submit(self.extract_text_from_paper, paper, text_limit): paper for paper in papers}

            # 收集结果
            for future in as_completed(future_to_paper):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    paper = future_to_paper[future]
                    pmid = paper.get('PMID', 'Unknown')
                    self.logger.error(f"❌ 提取文献 {pmid} 的文本失败 : {e}")
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
        self.logger.info(f"✅ 文本提取完成 : {successful}/{len(papers)} 篇成功")

        return results

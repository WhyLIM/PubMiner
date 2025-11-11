# -*- coding: utf-8 -*-
"""
PDF 下载模块

负责从多个源下载文献 PDF 文件，包括 DOI 查询、SciHub 下载、文件管理等功能
基于 RecursiveScholarCrawler 项目的下载功能进行优化和集成
"""

import os
import re
import time
import random
import hashlib
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup
import urllib.parse

from utils.logger import LoggerMixin
from utils.file_handler import FileHandler
from utils.api_manager import api_manager
from .scihub_downloader import SciHubDownloader

logger = logging.getLogger(__name__)


class PDFDownloader(LoggerMixin):
    """PDF 下载器 - 支持多源下载、DOI 查询、文件管理"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 PDF 下载器

        Args:
            config: 下载配置
        """
        self.config = config
        self.download_dir = Path(config.get('download_dir', './results/pdfs'))
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)
        self.timeout = config.get('timeout', 30)
        self.max_workers = config.get('max_workers', 4)
        self.verify_pdf = config.get('verify_pdf', True)
        self.max_file_size = config.get('max_file_size', 100 * 1024 * 1024)  # 100MB

        # SciHub 镜像配置
        self.scihub_mirrors = config.get('scihub_mirrors', [
            "https://sci-hub.se", "https://sci-hub.st", "https://sci-hub.ru", "https://www.sci-hub.ren",
            "https://www.sci-hub.ee"
        ])

        # 用户代理配置
        self.user_agents = config.get('user_agents', [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ])

        # DOI API 配置
        self.doi_apis = config.get('doi_apis',
                                   {'crossref': {
                                       'url': 'https://api.crossref.org/works',
                                       'enabled': True,
                                       'timeout': 15
                                   }})

        # 创建下载目录
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # 初始化会话
        self.session = requests.Session()
        self._setup_session()

        # 初始化 SciHub 下载器
        self.scihub = SciHubDownloader(mirrors=self.scihub_mirrors,
                                       user_agents=self.user_agents,
                                       timeout=self.timeout,
                                       max_retries=self.max_retries)

        # PMC 和开放获取仓库配置
        self.oa_repositories = {
            'pmc': {
                'base_url': 'https://www.ncbi.nlm.nih.gov/pmc/articles/',
                'pdf_patterns': ['/pdf', '/pdf/{pmc_id}.pdf'],
                'api_url': 'https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/',
                'enabled': True
            },
            'europepmc': {
                'base_url': 'https://europepmc.org/articles/',
                'pdf_patterns': ['?pdf=render', '/backend/ptpmcrender.fcgi?accid={pmc_id}&blobtype=pdf'],
                'enabled': True
            },
            'crossref': {
                'api_url': 'https://api.crossref.org/works/',
                'enabled': True
            }
        }

        # 统计信息
        self.stats = {'total_downloads': 0, 'successful_downloads': 0, 'failed_downloads': 0, 'retries': 0, 'total_size': 0}

        self.logger.info(f"✅ PDF 下载器初始化完成，下载目录: {self.download_dir}")

    def _setup_session(self):
        """设置 HTTP 会话"""
        self.session.headers.update({
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://www.google.com/'
        })

    def _get_random_user_agent(self) -> str:
        """获取随机用户代理"""
        return random.choice(self.user_agents)

    def _get_random_mirrors(self, exclude: Optional[List[str]] = None, count: Optional[int] = None) -> List[str]:
        """
        获取随机排序的镜像列表

        Args:
            exclude: 排除的镜像列表
            count: 返回的镜像数量

        Returns:
            镜像列表
        """
        available = list(set(self.scihub_mirrors))  # 去重
        if exclude:
            available = [m for m in available if m not in exclude]
        random.shuffle(available)
        if count and count < len(available):
            return available[:count]
        return available

    def _clean_filename(self, title: str, doi: Optional[str] = None, pmid: Optional[str] = None) -> str:
        """
        清理文件名

        Args:
            title: 论文标题
            doi: DOI 标识符
            pmid: PMID 标识符

        Returns:
            清理后的文件名
        """
        if title:
            # 移除特殊字符，截断长度
            cleaned = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:100].replace("", "_")
        else:
            cleaned = "unknown_paper"

        # 添加标识符
        if doi:
            cleaned_doi = doi.replace("/", "_").replace(".", "-")
            return f"{cleaned}_{cleaned_doi}.pdf"
        elif pmid:
            return f"{cleaned}_PMID{pmid}.pdf"
        else:
            return f"{cleaned}.pdf"

    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        计算文件 MD5 哈希值

        Args:
            file_path: 文件路径

        Returns:
            MD5 哈希值
        """
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.warning(f"计算文件哈希值失败: {e}")
            return ""

    def _extract_pdf_url_from_html(self, html_content: str, pmc_id: str) -> Optional[str]:
        """
        从 PMC HTML 页面中提取 PDF 下载链接
        基于 test.py 的成功方案，使用多级回退策略

        Args:
            html_content: HTML 页面内容
            pmc_id: PMC ID

        Returns:
            PDF 下载 URL，如果未找到则返回 None
        """
        try:
            import re
            from bs4 import BeautifulSoup

            # 解析 HTML 页面
            soup = BeautifulSoup(html_content, 'html.parser')
            host = "pmc.ncbi.nlm.nih.gov"
            base_article_url = f"https://{host}/articles/PMC{pmc_id}/"
            base_pdf_url = f"https://{host}/articles/PMC{pmc_id}/pdf"

            # 策略 1：基于 test.py 的 CSS 精确定位
            # 1) 优先：CSS 精确定位正文 PDF 按钮
            pdf_links = []

            # 查找以 /pdf/ 结尾的链接
            pdf_end_links = soup.find_all('a', href=re.compile(r'/pdf/$'))
            if pdf_end_links:
                pdf_links.extend(pdf_end_links)
                self.logger.debug(f"策略 1a: 找到 {len(pdf_end_links)} 个以 / pdf / 结尾的链接")

            # 查找以 /pdf 结尾的链接（不带斜杠）
            pdf_links.extend(soup.find_all('a', href=re.compile(r'/pdf$')))
            self.logger.debug(f"策略 1b: 找到 {len(soup.find_all('a', href=re.compile(r'/pdf$')))} 个以 / pdf 结尾的链接")

            # 如果找到链接，选择第一个
            if pdf_links:
                first_link = pdf_links[0]
                href = first_link.get('href', '')
                if href:
                    pdf_url = self._build_full_url(href, host, pmc_id)
                    if pdf_url:
                        self.logger.info(f"策略 1 成功: 通过 CSS 精确定位找到 PDF 链接: {pdf_url}")
                        return pdf_url

            # 策略 2：ARIA 名称以 PDF 开头的链接（排除补充材料的文件名）
            aria_links = []
            for link in soup.find_all('a', attrs={"aria-label": True}):
                aria_label = link.get('aria-label', '')
                if re.match(r'^PDF\b', aria_label, re.I):
                    aria_links.append(link)

            if aria_links:
                aria_link = aria_links[0]
                href = aria_link.get('href', '')
                if href:
                    pdf_url = self._build_full_url(href, host, pmc_id)
                    if pdf_url:
                        self.logger.info(f"策略 2 成功: 通过 ARIA 标签找到 PDF 链接: {pdf_url}")
                        return pdf_url

            # 策略 3：文本包含 "Download PDF"
            download_text_links = []
            for link in soup.find_all('a'):
                text = link.get_text(strip=True)
                if re.search(r'Download PDF', text, re.I):
                    download_text_links.append(link)

            if download_text_links:
                download_link = download_text_links[0]
                href = download_link.get('href', '')
                if href:
                    pdf_url = self._build_full_url(href, host, pmc_id)
                    if pdf_url:
                        self.logger.info(f"策略 3 成功: 通过'Download PDF'文本找到 PDF 链接: {pdf_url}")
                        return pdf_url

            # 策略 4：查找特定 class 的下载链接（原有方法作为备用）
            class_links = soup.find_all('a', class_='usa-link display-flex usa-tooltip')
            self.logger.debug(f"策略 4: 找到 {len(class_links)} 个 usa-link display-flex usa-tooltip 链接")

            if len(class_links) >= 2:
                # 获取第二个链接（通常包含 PDF 下载链接）
                second_link = class_links[1]
                href = second_link.get('href', '')
                if href:
                    pdf_url = self._build_full_url(href, host, pmc_id)
                    if pdf_url:
                        self.logger.info(f"策略 4 成功: 通过 tooltip class 找到 PDF 链接: {pdf_url}")
                        return pdf_url

            # 策略 5：查找包含 PDF 的所有链接
            all_pdf_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').lower()
                text = link.get_text(strip=True).lower()
                # 查找链接地址或文本中包含 pdf 的链接
                if 'pdf' in href or 'pdf' in text:
                    # 排除明显的非正文 PDF 链接（如补充材料）
                    if not any(exclude in href for exclude in ['supplementary', 'supplement', 'appendix']):
                        all_pdf_links.append(link)

            if all_pdf_links:
                # 选择最有可能的 PDF 链接
                for link in all_pdf_links[:3]:  # 只检查前 3 个
                    href = link.get('href', '')
                    if href:
                        pdf_url = self._build_full_url(href, host, pmc_id)
                        if pdf_url:
                            self.logger.info(f"策略 5 成功: 通过 PDF 关键词找到 PDF 链接: {pdf_url}")
                            return pdf_url

            # 策略 6：直接 PDF URL 尝试
            direct_urls = [
                f"https://{host}/articles/{pmc_id}/pdf",
                f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf",
                f"https://{host}/articles/{pmc_id}/pdf/{pmc_id}.pdf",
            ]

            # 快速验证直接 URL
            for test_url in direct_urls:
                try:
                    import requests
                    head_response = requests.head(test_url, timeout=5, allow_redirects=True)
                    if head_response.status_code == 200:
                        content_type = head_response.headers.get('Content-Type', '').lower()
                        if 'pdf' in content_type:
                            self.logger.info(f"策略 6 成功: 直接 PDF URL 验证成功: {test_url}")
                            return test_url
                except:
                    continue

            self.logger.warning(f"所有策略都未能提取到 PMC{pmc_id} 的 PDF 链接")
            return None

        except ImportError:
            self.logger.warning("缺少 BeautifulSoup 库，无法解析 HTML 页面")
            return None
        except Exception as e:
            self.logger.error(f"解析 HTML 页面提取 PDF 链接失败: {e}")
            return None

    def _build_full_url(self, href: str, host: str, pmc_id: str) -> Optional[str]:
        """
        构建完整的 PDF URL

        Args:
            href: 相对或绝对 URL
            host: 主机名
            pmc_id: PMC ID

        Returns:
            完整的 URL 或 None
        """
        try:
            if not href:
                return None

            href = href.strip()

            if href.startswith('http'):
                return href
            elif href.startswith('//'):
                return f"https:{href}"
            elif href.startswith('/'):
                return f"https://{host}{href}"
            else:
                # 相对路径，构建完整 URL
                return f"https://{host}/articles/PMC{pmc_id}/{href}"
        except Exception as e:
            self.logger.debug(f"构建完整 URL 失败: {e}")
            return None

    def _validate_pdf_url(self, pdf_url: str, article_url: str = None, timeout: int = 10) -> Tuple[bool, str]:
        """
        验证 PDF URL 是否有效，处理 PMC 的异步准备页面

        Args:
            pdf_url: PDF URL
            article_url: 文章页面 URL（用于 Referer）
            timeout: 请求超时时间

        Returns:
            (是否有效, 详细信息)
        """
        try:
            headers = {
                'User-Agent': self._get_random_user_agent(),
                'Referer': article_url or 'https://www.ncbi.nlm.nih.gov/pmc/',
                'Accept': 'application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }

            # 第一次请求
            response = self.session.head(pdf_url, timeout=timeout, headers=headers, allow_redirects=True)

            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                content_length = response.headers.get('Content-Length', '0')

                self.logger.debug(f"PDF URL 验证 - Status: {response.status_code}, Type: {content_type}, Size: {content_length}")

                if 'pdf' in content_type:
                    return True, f"有效的 PDF 链接: {content_type}, 大小: {content_length} bytes"
                elif 'html' in content_type:
                    # 可能是准备页面，进行 GET 请求进一步验证
                    get_response = self.session.get(pdf_url, timeout=timeout, headers=headers)
                    if get_response.status_code == 200:
                        get_content_type = get_response.headers.get('Content-Type', '').lower()
                        if 'pdf' in get_content_type:
                            return True, f"有效的 PDF 链接（GET 请求）: {get_content_type}, 大小: {content_length} bytes"
                        else:
                            # 检查是否包含准备页面的关键词
                            response_text = get_response.text[:1000].lower()
                            if any(keyword in response_text for keyword in ['preparing', 'download', 'pdf', 'loading']):
                                return True, f"PMC 准备页面，可能需要等待: {get_content_type}"
                            else:
                                return False, f"HTML 页面不是准备页面: {get_content_type}"
                    else:
                        return False, f"GET 请求失败: HTTP {get_response.status_code}"
                else:
                    return False, f"未知的 Content-Type: {content_type}"
            else:
                return False, f"HTTP 请求失败: {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "请求超时"
        except Exception as e:
            return False, f"验证过程出错: {str(e)}"

    def _validate_pdf_file(self, file_path: Path) -> bool:
        """
        验证 PDF 文件有效性

        Args:
            file_path: PDF 文件路径

        Returns:
            是否为有效的 PDF 文件
        """
        if not file_path.exists():
            return False

        try:
            # 检查文件大小
            file_size = file_path.stat().st_size
            if file_size < 1024:  # 小于 1KB 可能不是有效 PDF
                self.logger.warning(f"PDF 文件过小: {file_size} bytes")
                return False

            if file_size > self.max_file_size:
                self.logger.warning(f"PDF 文件过大: {file_size} bytes")
                return False

            # 检查 PDF 文件头
            with open(file_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF'):
                    self.logger.warning("文件不是有效的 PDF 格式")
                    return False

            # 如果启用了 PDF 验证，使用 PyMuPDF 验证
            if self.verify_pdf:
                try:
                    import fitz  # PyMuPDF
                    with fitz.open(str(file_path)) as doc:
                        if doc.page_count > 0:
                            self.logger.debug(f"✅ PDF 验证成功: {doc.page_count} 页")
                            return True
                        else:
                            self.logger.warning("PDF 文件没有页面内容")
                            return False
                except ImportError:
                    self.logger.warning("PyMuPDF 未安装，跳过 PDF 结构验证")
                    return True  # 只进行基本验证
                except Exception as e:
                    self.logger.warning(f"PDF 结构验证失败: {e}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"PDF 文件验证出错: {e}")
            return False

    def _find_pdf_link_in_html(self, html_content: str, base_url: str) -> Optional[str]:
        """
        从 HTML 内容中查找 PDF 下载链接

        Args:
            html_content: HTML 内容
            base_url: 基础 URL

        Returns:
            PDF 下载链接或 None
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # 查找 embed 和 iframe 标签
            for tag in soup.find_all(['embed', 'iframe']):
                src = tag.get('src')
                if src:
                    if src.startswith('//'):
                        return f"https:{src}"
                    if not src.startswith('http'):
                        return urljoin(base_url, src)
                    return src

            # 查找 PDF 下载链接
            for link in soup.find_all('a', href=True):
                href = link['href']
                if ('pdf' in href.lower() or link.get('id') == 'download' or 'download' in link.get('class', [])):
                    if href.startswith('//'):
                        return f"https:{href}"
                    if not href.startswith('http'):
                        return urljoin(base_url, href)
                    return href

            return None

        except Exception as e:
            self.logger.error(f"解析 HTML 查找 PDF 链接时出错: {e}")
            return None

    def _download_and_save_pdf(self,
                               url: str = None,
                               response: requests.Response = None,
                               output_path: Path = None,
                               timeout: Optional[int] = None,
                               expected_size: int = None) -> Tuple[bool, Optional[str]]:
        """
        统一的 PDF 下载和保存函数

        Args:
            url: 下载 URL（如果不提供 response 则必需）
            response: 已有的 HTTP 响应对象（可选）
            output_path: 输出路径
            timeout: 超时时间
            expected_size: 期望的文件大小

        Returns:
            (是否成功, 错误信息)
        """
        try:
            timeout = timeout or self.timeout

            # 如果没有提供响应对象，则下载
            if response is None:
                if not url:
                    return False, "缺少 URL 或响应对象"

                # 下载文件
                response = self.session.get(url, timeout=timeout, stream=True)
                response.raise_for_status()

            # 确保输出路径存在
            if output_path is None:
                return False, "缺少输出路径"

            # 保存文件
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # 验证下载的文件
            if self._validate_pdf_file(output_path, expected_size):
                file_size = output_path.stat().st_size
                self.stats['total_size'] += file_size
                self.logger.info(f"✅ PDF 保存成功: {output_path.name} ({file_size/1024:.1f}KB)")
                return True, None
            else:
                # 删除无效文件
                if output_path.exists():
                    output_path.unlink()
                return False, "保存的文件验证失败，不是有效的 PDF"

        except requests.exceptions.Timeout:
            return False, f"下载超时 ({timeout} 秒)"
        except requests.exceptions.RequestException as e:
            return False, f"网络请求错误: {e}"
        except IOError as e:
            self.logger.error(f"文件写入失败: {e}")
            if output_path and output_path.exists():
                output_path.unlink(missing_ok=True)
            return False, f"文件写入失败: {e}"
        except Exception as e:
            self.logger.error(f"下载过程出错: {e}")
            if output_path and output_path.exists():
                output_path.unlink(missing_ok=True)
            return False, f"下载过程出错: {e}"

    def get_download_stats(self) -> Dict[str, Any]:
        """
        获取下载统计信息

        Returns:
            统计信息字典
        """
        success_rate = 0
        if self.stats['total_downloads'] > 0:
            success_rate = (self.stats['successful_downloads'] / self.stats['total_downloads']) * 100

        return {
            **self.stats, 'success_rate':
            round(success_rate, 2),
            'average_file_size':
            (self.stats['total_size'] / self.stats['successful_downloads'] if self.stats['successful_downloads'] > 0 else 0)
        }

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {'total_downloads': 0, 'successful_downloads': 0, 'failed_downloads': 0, 'retries': 0, 'total_size': 0}
        self.logger.info("📊 下载统计信息已重置")

    def _create_download_directory(self) -> bool:
        """创建下载目录"""
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"创建下载目录失败: {e}")
            return False

    def _sanitize_doi(self, doi: str) -> str:
        """将 DOI 转换为安全的文件名部分"""
        if not doi:
            return "unknown"
        safe_doi = doi.replace('/', '_').replace('\\', '_')
        safe_doi = ''.join(c for c in safe_doi if c.isalnum() or c in '._-')
        return safe_doi

    def _generate_filename(self, doi: str, source: str = "download", title: str = None) -> str:
        """
        生成统一的文件名格式

        Args:
            doi: DOI 标识符
            source: 下载源标识 (默认为 "download")
            title: 论文标题 (可选)

        Returns:
            统一格式的文件名，如 {doi}_{source}.pdf
        """
        safe_doi = self._sanitize_doi(doi)
        suffix = (source or "download").lower()

        if title:
            # 如果有标题，添加到文件名中
            safe_title = ''.join(c for c in title if c.isalnum() or c in '._-')
            safe_title = safe_title.replace('_', '_')[:50]  # 限制长度
            return f"{safe_doi}_{suffix}_{safe_title}.pdf"
        else:
            return f"{safe_doi}_{suffix}.pdf"

    def download_from_scihub(self, doi: str) -> Tuple[bool, Optional[Path], Optional[str]]:
        """从 SciHub 下载 PDF，返回 (成功, 路径, 错误)"""
        try:
            self.logger.info(f"尝试从 SciHub 下载: {doi}")
            filename = f"{self._sanitize_doi(doi)}_SciHub.pdf"
            output_path = self.download_dir / filename

            success, error_msg = self.scihub.download_by_doi(doi, output_path)
            if success:
                if self._validate_pdf_file(output_path):
                    file_size = output_path.stat().st_size
                    self.logger.info(f"✅ SciHub 下载成功: {filename} ({file_size} bytes)")
                    return True, output_path, None
                else:
                    output_path.unlink(missing_ok=True)
                    return False, None, "下载的 PDF 验证失败"
            else:
                return False, None, error_msg or "SciHub 下载失败"
        except Exception as e:
            return False, None, str(e)

    def download_with_retry(self,
                            download_callable,
                            *args,
                            max_retries: Optional[int] = None,
                            retry_delay: Optional[int] = None,
                            **kwargs) -> Tuple[bool, Optional[Path], Optional[str]]:
        """通用重试包装器，接受一个返回 (成功, 路径, 错误) 的下载函数"""
        retries = max_retries if max_retries is not None else self.max_retries
        delay = retry_delay if retry_delay is not None else self.retry_delay
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                success, path, error = download_callable(*args, **kwargs)
                if success:
                    return True, path, None
                last_error = error
                self.logger.info(f"重试 {attempt}/{retries} 失败: {error}. 等待 {delay} 秒...")
                time.sleep(delay)
            except Exception as e:
                last_error = str(e)
                self.logger.info(f"重试 {attempt}/{retries} 异常: {e}. 等待 {delay} 秒...")
                time.sleep(delay)
        return False, None, last_error or "重试后仍失败"

    def _handle_duplicate_file(self, file_path: Path) -> Path:
        """处理重复文件名"""
        if not file_path.exists():
            return file_path

        # 生成新的文件名
        base_path = file_path.parent
        base_name = file_path.stem
        extension = file_path.suffix

        counter = 1
        while True:
            new_name = f"{base_name}_{counter}{extension}"
            new_path = base_path / new_name
            if not new_path.exists():
                return new_path
            counter += 1

            # 防止无限循环
            if counter > 1000:
                import time
                timestamp = int(time.time())
                new_name = f"{base_name}_{timestamp}{extension}"
                return base_path / new_name

    def _normalize_title(self, title: str) -> str:
        """
        标准化论文标题以提高匹配准确性

        Args:
            title: 原始标题

        Returns:
            标准化后的标题
        """
        # 移除特殊字符，转换为小写，合并空白字符
        clean_title = re.sub(r'[^\w\s]', ' ', title)
        clean_title = ' '.join(clean_title.lower().split())
        return clean_title

    def _calculate_similarity_score(self, title1: str, title2: str) -> float:
        """
        计算两个标题的相似度分数

        Args:
            title1: 标题 1
            title2: 标题 2

        Returns:
            相似度分数 (0-1)
        """
        try:
            from difflib import SequenceMatcher
            normalized1 = self._normalize_title(title1)
            normalized2 = self._normalize_title(title2)
            return SequenceMatcher(None, normalized1, normalized2).ratio()
        except ImportError:
            # 如果没有 difflib，使用简单的字符串匹配
            normalized1 = self._normalize_title(title1)
            normalized2 = self._normalize_title(title2)
            if normalized1 == normalized2:
                return 1.0
            elif normalized1 in normalized2 or normalized2 in normalized1:
                return 0.8
            else:
                return 0.0

    def check_open_access_status(self, doi: str) -> Dict[str, Any]:
        """
        检查文章的开放获取状态

        Args:
            doi: DOI 标识符

        Returns:
            开放获取状态信息
        """
        self.logger.info(f"检查开放获取状态: {doi}")

        result = {
            'doi': doi,
            'is_open_access': False,
            'license': None,
            'pmc_id': None,
            'oa_locations': [],
            'pdf_urls': [],
            'source': None
        }

        try:
            # 查询 Crossref API
            crossref_url = f"https://api.crossref.org/works/{doi}"
            response = self.session.get(crossref_url, timeout=15)

            if response.status_code == 200:
                data = response.json()
                work = data.get('message', {})

                # 检查许可证信息
                licenses = work.get('license', [])
                if licenses:
                    result['license'] = licenses[0].get('URL', '')
                    if any(lic in result['license'].lower() for lic in ['cc-by', 'creative-commons']):
                        result['is_open_access'] = True

                # 检查开放获取标记
                if work.get('is-referenced-by-count', 0) > 0:
                    result['is_open_access'] = True

                # 查找 PMC ID
                for link in work.get('link', []):
                    url = link.get('URL', '')
                    if 'pmc' in url.lower():
                        pmc_match = re.search(r'PMC(\d+)', url)
                        if pmc_match:
                            result['pmc_id'] = pmc_match.group(1)
                            result['is_open_access'] = True

                # 查找 PDF 链接
                for link in work.get('link', []):
                    if link.get('content-type') == 'application/pdf':
                        result['pdf_urls'].append(link.get('URL'))

                result['source'] = 'crossref'
                self.logger.info(f"Crossref 查询完成: OA={result['is_open_access']}, PMC={result['pmc_id']}")

        except Exception as e:
            self.logger.warning(f"Crossref 查询失败: {e}")

        # 如果没有找到 PMC ID，尝试 PMC ID 转换 API
        if not result['pmc_id']:
            try:
                pmc_api_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?tool=pubminer&email=user@example.com&ids={doi}&format=json"
                response = self.session.get(pmc_api_url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    records = data.get('records', [])
                    if records and 'pmcid' in records[0]:
                        pmc_id = records[0]['pmcid'].replace('PMC', '')
                        result['pmc_id'] = pmc_id
                        result['is_open_access'] = True
                        self.logger.info(f"PMC ID 转换成功: PMC{pmc_id}")

            except Exception as e:
                self.logger.warning(f"PMC ID 转换失败: {e}")

        return result

    def download_from_pmc(self, pmc_id: str, doi: str = None) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        从 PMC 下载 PDF（带重试机制），优先使用基于 test.py 的增强策略

        Args:
            pmc_id: PMC ID
            doi: DOI (可选，用于文件命名)

        Returns:
            (成功标志, 文件路径, 错误信息)
        """
        self.logger.info(f"尝试从 PMC 下载: PMC{pmc_id}")

        # 策略顺序：EuropePMC 首选 -> Playwright 备选 -> 传统方法兜底
        # 策略 1：优先使用 EuropePMC（已验证成功率高）
        self.logger.info("策略 1: 尝试 EuropePMC（首选，已验证成功）...")
        try:
            europepmc_urls = [
                f"https://europepmc.org/backend/ptpmcrender.fcgi?accid=PMC{pmc_id}&blobtype=pdf",
                f"https://europepmc.org/articles/PMC{pmc_id}?pdf=render"
            ]

            for i, url in enumerate(europepmc_urls):
                self.logger.info(f"尝试 EuropePMC URL {i+1}/{len(europepmc_urls)}: {url}")

                # 使用更长的超时时间和重试
                success, file_path, error = self.download_with_retry(urls=[url],
                                                                     output_dir=self.download_dir,
                                                                     max_retries=3,
                                                                     use_scihub_fallback=False)

                if success and file_path and file_path.exists():
                    self.logger.info(f"✅ EuropePMC 首选策略成功: {file_path.name}")
                    return True, file_path, None
                else:
                    self.logger.debug(f"EuropePMC URL {i+1} 失败: {error}")

        except Exception as e:
            self.logger.warning(f"EuropePMC 首选策略失败: {e}")

        # 策略 2：使用 Playwright 作为备选策略
        self.logger.info("策略 2: 尝试 Playwright 策略（备选方案）...")
        try:
            playwright_success, playwright_path = self._download_with_playwright(pmc_id, doi)
            if playwright_success:
                self.logger.info("✅ Playwright 备选策略成功")
                return True, playwright_path, None
            else:
                self.logger.warning("Playwright 备选策略未成功")
        except ImportError as e:
            self.logger.warning(f"Playwright 不可用: {e}")
        except Exception as e:
            self.logger.warning(f"Playwright 备选策略失败: {e}")

        # 策略 3：传统方法作为最后兜底
        self.logger.info("策略 3: 尝试传统 PMC 解析方法（兜底）...")
        try:
            article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
            headers = {'User-Agent': self._get_random_user_agent(), 'Referer': 'https://www.google.com/'}
            response = self.session.get(article_url, timeout=30, headers=headers)

            if response.status_code == 200 and 'html' in response.headers.get('Content-Type', '').lower():
                self.logger.info("成功获取 PMC 文章页面，开始解析 PDF 链接...")
                pdf_url = self._extract_pdf_url_from_html(response.text, pmc_id)

                if pdf_url:
                    filename = self._generate_filename(doi, "PMC")
                    output_path = self.download_dir / filename
                    self.logger.info(f"尝试传统下载: {pdf_url}")

                    # 简化的下载逻辑
                    resp = self.session.get(pdf_url, timeout=30, stream=True)
                    if resp.status_code == 200 and 'pdf' in resp.headers.get('Content-Type', '').lower():
                        success, _ = self._download_and_save_pdf(response=resp, output_path=output_path)
                        if success:
                            self.logger.info("✅ 传统方法兜底成功")
                            return True, output_path, None
        except Exception as e:
            self.logger.warning(f"传统方法兜底失败: {e}")

        return False, None, "所有 PMC 下载策略均失败"

    def query_doi_by_title(self, title: str, api: str = 'crossref') -> Dict[str, Any]:
        """
        通过标题查询 DOI 信息

        Args:
            title: 论文标题
            api: 使用的 API 服务 ('crossref')

        Returns:
            DOI 查询结果字典
        """
        self.logger.info(f"🔍 查询 DOI: {title[:50]}...")

        if api not in self.doi_apis or not self.doi_apis[api].get('enabled'):
            return {"doi": None, "error": f"API 服务 {api} 未启用"}

        api_config = self.doi_apis[api]

        try:
            if api == 'crossref':
                return self._query_crossref(title, api_config)
            else:
                return {"doi": None, "error": f"不支持的 API: {api}"}

        except Exception as e:
            self.logger.error(f"DOI 查询出错: {e}")
            return {"doi": None, "error": str(e)}

    def _query_crossref(self, title: str, api_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用 CrossRef API 查询 DOI

        Args:
            title: 论文标题
            api_config: API 配置

        Returns:
            查询结果
        """
        url = api_config['url']
        timeout = api_config.get('timeout', 15)

        headers = {
            'User-Agent': 'PubMiner/1.0 (https://github.com/pubminer; mailto:contact@example.com)',
            'Accept': 'application/json'
        }

        params = {"query.bibliographic": title, "rows": 5, "sort": "score", "order": "desc"}

        try:
            # 使用 API 管理器进行限流
            response = api_manager.get(url, headers=headers, params=params, timeout=timeout, api_name='crossref')

            response.raise_for_status()
            data = response.json()

            items = data.get("message", {}).get("items", [])
            if not items:
                self.logger.warning(f"CrossRef API 未找到结果: {title}")
                return {"doi": None, "error": "未找到结果"}

            # 查找最佳匹配
            best_match = None
            best_score = 0

            for item in items:
                item_title_list = item.get("title")
                if not item_title_list:
                    continue

                item_title = item_title_list[0]
                score = self._calculate_similarity_score(title, item_title)

                # 使用较严格的阈值确保匹配质量
                if score > best_score and score > 0.8:
                    best_score = score
                    best_match = {
                        "doi":
                        item.get("DOI", ""),
                        "title":
                        item_title,
                        "score":
                        score,
                        "publisher":
                        item.get("publisher", ""),
                        "type":
                        item.get("type", ""),
                        "journal": (item.get("container-title") or [""])[0],
                        "authors":
                        item.get("author", []),
                        "published":
                        item.get("published-print", {}).get("date-parts", [[]])[0] if item.get("published-print") else [],
                        "url":
                        item.get("URL", "")
                    }

            if best_match:
                self.logger.info(f"✅ 找到最佳 DOI 匹配: {best_match['doi']} (相似度: {best_score:.2f})")
                return best_match
            else:
                self.logger.warning(f"未找到高置信度的 DOI 匹配: {title}")
                return {"doi": None, "error": "未找到高置信度匹配"}

        except requests.exceptions.RequestException as e:
            self.logger.error(f"CrossRef API 网络错误: {e}")
            return {"doi": None, "error": f"网络错误: {e}"}
        except Exception as e:
            self.logger.error(f"CrossRef API 查询异常: {e}")
            return {"doi": None, "error": f"查询异常: {e}"}

    def query_doi_batch(self, titles: List[str], max_workers: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        批量查询 DOI

        Args:
            titles: 标题列表
            max_workers: 最大并发数

        Returns:
            DOI 查询结果列表
        """
        max_workers = max_workers or min(self.max_workers, len(titles))

        self.logger.info(f"📚 开始批量 DOI 查询，共 {len(titles)} 个标题")

        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交任务
            future_to_title = {executor.submit(self.query_doi_by_title, title): title for title in titles}

            # 收集结果
            for future in as_completed(future_to_title):
                title = future_to_title[future]
                try:
                    result = future.result()
                    result['query_title'] = title
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"批量 DOI 查询失败: {title} - {e}")
                    results.append({"doi": None, "error": str(e), "query_title": title})

        successful = len([r for r in results if r.get('doi')])
        self.logger.info(f"✅ 批量 DOI 查询完成: {successful}/{len(titles)} 成功")

        return results

    def download_by_doi(self, doi: str, title: Optional[str] = None, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        通过 DOI 下载 PDF 文件

        Args:
            doi: DOI 标识符
            title: 论文标题（用于文件命名）
            output_dir: 输出目录

        Returns:
            下载结果字典
        """
        self.stats['total_downloads'] += 1

        output_dir = output_dir or self.download_dir
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 检查文件是否已存在（检查 PMC 和 SciHub 两种命名）
        safe_doi = doi.replace('/', '_').replace('\\', '_')
        pmc_filename = f"{safe_doi}_PMC.pdf"
        scihub_filename = f"{safe_doi}_SciHub.pdf"

        pmc_path = output_dir / pmc_filename
        scihub_path = output_dir / scihub_filename

        # SciHub 下载使用的文件路径
        output_path = scihub_path

        if pmc_path.exists() and self._validate_pdf_file(pmc_path):
            file_size = pmc_path.stat().st_size
            self.logger.info(f"✅ PMC 文件已存在: {pmc_filename} ({file_size} bytes)")
            return {
                'success': True,
                'doi': doi,
                'title': title,
                'local_path': str(pmc_path),
                'file_size': file_size,
                'status': 'already_exists',
                'source': 'PMC',
                'error': None
            }

        if scihub_path.exists() and self._validate_pdf_file(scihub_path):
            file_size = scihub_path.stat().st_size
            self.logger.info(f"✅ SciHub 文件已存在: {scihub_filename} ({file_size} bytes)")
            return {
                'success': True,
                'doi': doi,
                'title': title,
                'local_path': str(scihub_path),
                'file_size': file_size,
                'status': 'already_exists',
                'source': 'SciHub',
                'error': None
            }

        # 首先检查开放获取状态
        self.logger.info(f"检查开放获取状态: {doi}")
        oa_status = self.check_open_access_status(doi)

        # 如果有 PMC ID，优先尝试 PMC 下载（只尝试一次）
        if oa_status.get('pmc_id'):
            self.logger.info(f"发现 PMC ID: PMC{oa_status['pmc_id']}，尝试 PMC 下载")
            pmc_success, pmc_path, pmc_error = self.download_from_pmc(oa_status['pmc_id'], doi)

            if pmc_success and pmc_path:
                file_size = pmc_path.stat().st_size
                self.stats['successful_downloads'] += 1

                return {
                    'success': True,
                    'doi': doi,
                    'title': title,
                    'local_path': str(pmc_path),
                    'file_size': file_size,
                    'status': 'downloaded_from_pmc',
                    'source': 'PMC',
                    'pmc_id': oa_status['pmc_id'],
                    'is_open_access': oa_status['is_open_access'],
                    'error': None
                }
            else:
                self.logger.warning(f"PMC 下载失败: {pmc_error}")
                self.logger.info("转为 SciHub 下载策略")

        # 尝试 SciHub 下载（带重试）
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"📥 SciHub 下载 (尝试 {attempt + 1}/{self.max_retries}): {doi}")

                # 使用 SciHub 下载
                success, error = self.scihub.download_by_doi(doi, output_path, delay=self.retry_delay)

                if success and self._validate_pdf_file(output_path):
                    file_size = output_path.stat().st_size
                    self.stats['successful_downloads'] += 1

                    return {
                        'success': True,
                        'doi': doi,
                        'title': title,
                        'local_path': str(output_path),
                        'file_size': file_size,
                        'status': 'downloaded_from_scihub',
                        'source': 'SciHub',
                        'is_open_access': oa_status['is_open_access'],
                        'pmc_id': oa_status.get('pmc_id'),
                        'error': None,
                        'attempts': attempt + 1
                    }
                else:
                    self.logger.warning(f"下载失败 (尝试 {attempt + 1}): {error}")
                    self.stats['retries'] += 1

                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))  # 指数退避

            except Exception as e:
                self.logger.error(f"下载异常 (尝试 {attempt + 1}): {e}")
                self.stats['retries'] += 1

                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))

        # 所有尝试都失败
        self.stats['failed_downloads'] += 1

        return {
            'success': False,
            'doi': doi,
            'title': title,
            'local_path': None,
            'file_size': 0,
            'status': 'failed',
            'error': f"在 {self.max_retries} 次尝试后下载失败",
            'attempts': self.max_retries
        }

    def download_by_pmid(self, pmid: str, title: Optional[str] = None, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        通过 PMID 下载 PDF 文件（先查询 DOI 再下载）

        Args:
            pmid: PMID 标识符
            title: 论文标题
            output_dir: 输出目录

        Returns:
            下载结果字典
        """
        # 如果没有提供标题，尝试从其他地方获取
        if not title:
            title = f"PMID_{pmid}"

        # 首先查询 DOI
        doi_result = self.query_doi_by_title(title)

        if doi_result.get('doi'):
            doi = doi_result['doi']
            self.logger.info(f"✅ 通过标题找到 DOI: {doi}")

            # 使用找到的 DOI 下载
            result = self.download_by_doi(doi, title, output_dir)
            result['pmid'] = pmid
            result['doi_source'] = 'title_query'
            return result
        else:
            # 如果没有找到 DOI，尝试直接使用 PMID 构造文件名
            self.logger.warning(f"未找到 DOI，尝试其他方式: PMID {pmid}")

            output_dir = output_dir or self.download_dir
            filename = self._clean_filename(title, pmid=pmid)

            return {
                'success': False,
                'pmid': pmid,
                'doi': None,
                'title': title,
                'local_path': None,
                'file_size': 0,
                'status': 'no_doi_found',
                'error': f"无法找到 PMID {pmid} 对应的 DOI",
                'doi_query_error': doi_result.get('error')
            }

    def download_with_fallback(self, doi: Optional[str], title: str, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        带回退机制的下载（参考 RecursiveScholarCrawler 的逻辑）

        Args:
            doi: DOI 标识符（可选）
            title: 论文标题
            output_dir: 输出目录

        Returns:
            下载结果字典
        """
        # 步骤 1：如果提供了 DOI，先尝试使用它
        if doi:
            self.logger.info(f"🎯 使用提供的 DOI 下载: {doi}")
            result = self.download_by_doi(doi, title, output_dir)
            if result['success']:
                result['download_method'] = 'provided_doi'
                return result
            else:
                self.logger.warning(f"提供的 DOI 下载失败: {result.get('error')}")

        # 步骤 2：如果没有 DOI 或 DOI 下载失败，通过标题查询新的 DOI
        if not title:
            return {
                'success': False,
                'doi': doi,
                'title': title,
                'local_path': None,
                'file_size': 0,
                'status': 'no_title_for_doi_search',
                'error': "没有 DOI 且没有标题，无法继续",
                'download_method': 'failed'
            }

        self.logger.info(f"🔍 通过标题查询新的 DOI: {title[:70]}...")
        doi_result = self.query_doi_by_title(title)

        new_doi = doi_result.get("doi")
        if not new_doi:
            error_msg = f"无法找到标题对应的 DOI: {doi_result.get('error')}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'doi': doi,
                'title': title,
                'local_path': None,
                'file_size': 0,
                'status': 'doi_not_found',
                'error': error_msg,
                'download_method': 'failed'
            }

        # 避免重复下载相同的 DOI
        if new_doi == doi:
            error_msg = f"查询到的 DOI 与失败的 DOI 相同: {new_doi}"
            self.logger.warning(error_msg)
            return {
                'success': False,
                'doi': doi,
                'title': title,
                'local_path': None,
                'file_size': 0,
                'status': 'same_doi_failed',
                'error': error_msg,
                'download_method': 'failed'
            }

        # 步骤 3：使用新找到的 DOI 下载
        self.logger.info(f"✨ 找到新的 DOI，开始下载: {new_doi}")
        result = self.download_by_doi(new_doi, title, output_dir)

        if result['success']:
            result['download_method'] = 'title_resolved_doi'
            result['original_doi'] = doi
            result['resolved_doi'] = new_doi
        else:
            result['download_method'] = 'all_methods_failed'
            result['doi_query_result'] = doi_result

        return result

    def batch_download(self,
                       items: List[Dict[str, Any]],
                       max_workers: Optional[int] = None,
                       output_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        批量下载 PDF 文件

        Args:
            items: 下载项目列表，每项包含'doi', 'title', 'pmid' 等字段
            max_workers: 最大并发数
            output_dir: 输出目录

        Returns:
            下载结果列表
        """
        max_workers = max_workers or min(self.max_workers, len(items))
        output_dir = output_dir or self.download_dir

        self.logger.info(f"📦 开始批量下载，共 {len(items)} 项，并发数: {max_workers}")

        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交下载任务
            future_to_item = {}

            for item in items:
                doi = item.get('doi')
                title = item.get('title', item.get('Title', ''))
                pmid = item.get('pmid', item.get('PMID', ''))

                # 选择下载方法
                if doi and title:
                    future = executor.submit(self.download_with_fallback, doi, title, output_dir)
                elif pmid and title:
                    future = executor.submit(self.download_by_pmid, pmid, title, output_dir)
                elif doi:
                    future = executor.submit(self.download_by_doi, doi, title, output_dir)
                else:
                    # 无法下载的项目
                    results.append({
                        'success': False,
                        'doi': doi,
                        'pmid': pmid,
                        'title': title,
                        'local_path': None,
                        'file_size': 0,
                        'status': 'insufficient_info',
                        'error': '缺少 DOI、PMID 或标题信息'
                    })
                    continue

                future_to_item[future] = item

            # 收集结果
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    result = future.result()
                    result['original_item'] = item
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"批量下载任务异常: {e}")
                    results.append({
                        'success': False,
                        'doi': item.get('doi'),
                        'pmid': item.get('pmid'),
                        'title': item.get('title'),
                        'local_path': None,
                        'file_size': 0,
                        'status': 'exception',
                        'error': str(e),
                        'original_item': item
                    })

        # 统计结果
        successful = len([r for r in results if r.get('success')])
        self.logger.info(f"✅ 批量下载完成: {successful}/{len(results)} 成功")

        return results

    def retry_failed_downloads(self,
                               failed_results: List[Dict[str, Any]],
                               max_retries: Optional[int] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        重试失败的下载

        Args:
            failed_results: 失败的下载结果列表
            max_retries: 最大重试次数

        Returns:
            (仍然失败的结果, 重试成功的结果)
        """
        max_retries = max_retries or self.max_retries

        if not failed_results:
            self.logger.info("没有失败的下载需要重试")
            return [], []

        self.logger.info(f"🔄 开始重试 {len(failed_results)} 个失败的下载")

        still_failed = []
        newly_successful = []

        for i, result in enumerate(failed_results):
            doi = result.get('doi')
            title = result.get('title')
            pmid = result.get('pmid')

            retry_count = result.get('retry_count', 0) + 1

            if retry_count > max_retries:
                self.logger.warning(f"超过最大重试次数，跳过: {title or doi or pmid}")
                result['retry_count'] = retry_count
                still_failed.append(result)
                continue

            self.logger.info(f"重试 {retry_count}/{max_retries} [{i+1}/{len(failed_results)}]: {title or doi or pmid}")

            # 选择重试方法
            if doi and title:
                retry_result = self.download_with_fallback(doi, title)
            elif pmid and title:
                retry_result = self.download_by_pmid(pmid, title)
            elif doi:
                retry_result = self.download_by_doi(doi, title)
            else:
                retry_result = {'success': False, 'error': '缺少重试所需的信息'}

            # 更新结果
            retry_result.update({
                'retry_count': retry_count,
                'retry_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'original_error': result.get('error')
            })

            if retry_result['success']:
                self.logger.info(f"✅ 重试成功: {title or doi or pmid}")
                newly_successful.append(retry_result)
            else:
                self.logger.warning(f"❌ 重试仍然失败: {retry_result.get('error')}")
                still_failed.append(retry_result)

            # 重试间隔
            if i < len(failed_results) - 1:
                time.sleep(self.retry_delay)

        self.logger.info(f"🔄 重试完成: {len(newly_successful)} 成功, {len(still_failed)} 仍然失败")

        return still_failed, newly_successful

    def _download_with_playwright(self, pmc_id: str, doi: str = None) -> Tuple[bool, Optional[Path]]:
        """
        使用 Playwright 下载 PDF

        Args:
            pmc_id: PMC ID
            doi: DOI (可选，用于文件命名)

        Returns:
            (成功标志, 文件路径)
        """
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            import re
        except ImportError:
            self.logger.debug("Playwright 未安装，跳过 Playwright 策略")
            raise ImportError("Playwright not available")

        pmcid = f"PMC{pmc_id}"
        host = "pmc.ncbi.nlm.nih.gov"
        article_url = f"https://{host}/articles/{pmcid}/"
        pdf_url = f"https://{host}/articles/{pmcid}/pdf"

        # 生成文件名
        if doi:
            safe_doi = doi.replace('/', '_').replace('\\', '_')
            filename = f"{safe_doi}_PMC_Playwright.pdf"
        else:
            filename = f"pmc_{pmc_id}_PMC_Playwright.pdf"

        output_path = self.download_dir / filename

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context()
                page = ctx.new_page()

                # 进入文章页
                page.goto(article_url, wait_until="domcontentloaded")

                # --- 1) 优先：CSS 精确定位正文 PDF 按钮 ---
                pdf_link = page.locator("a[href$='/pdf/']").first
                if not pdf_link.count():
                    pdf_link = page.locator("a[href$='/pdf']").first

                # --- 2) 回退：ARIA 名称以 PDF 开头的链接（排除补充材料的文件名）---
                if not pdf_link.count():
                    # 例如 "PDF (2.4 MB)"
                    pdf_link = page.get_by_role("link", name=re.compile(r"^PDF\\b", re.I)).first

                # --- 3) 兜底：直接查找包含 PDF 的链接，排除 tooltip ---
                if not pdf_link.count():
                    # 查找所有包含 "PDF" 的可见链接
                    pdf_links = page.locator("a:has-text('PDF')").filter(has_not_text="tooltip").first
                    if pdf_links.count() > 0:
                        pdf_link = pdf_links

                if not pdf_link.count():
                    # 最后尝试：查找实际的链接元素，排除 tooltip span
                    all_links = page.locator("a[href*='pdf'], a[href$='pdf/'], a[href$='.pdf']").first
                    if all_links.count() > 0:
                        pdf_link = all_links

                if not pdf_link.count():
                    self.logger.warning("找不到正文 PDF 按钮；页面结构可能变化。")
                    return False, None

                # 有些站点把 PDF 链接设为 target=_blank，这里同时监听可能的 popup
                popup = None
                try:
                    with page.expect_popup(timeout=2000) as pop_ctx:
                        pdf_link.click(timeout=10000)
                    popup = pop_ctx.value
                except PWTimeout:
                    # 没有新标签，就在当前页
                    pdf_link.click(timeout=10000)

                # 等校验脚本跑完（给得稍微宽裕一点）
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)

                # 用与页面同一会话的 request 客户端获取 PDF
                # 不直接用 popup 的 content，因为有时是中间页 / 准备页
                resp = ctx.request.get(pdf_url)
                if resp.ok and resp.headers.get("content-type", "").startswith("application/pdf"):
                    with open(output_path, "wb") as f:
                        f.write(resp.body())
                    # 更新统计信息
                    file_size = output_path.stat().st_size
                    self.stats['total_size'] += file_size
                    self.logger.info(f"✅ Playwright 下载成功: 通过 ctx.request ({file_size/1024:.1f}KB)")
                    return True, output_path
                else:
                    # 再尝试直接从当前 DOM 读 href（有时带 query 的真实 pdf 地址）
                    try:
                        href = pdf_link.get_attribute("href")
                        if href and not href.startswith("http"):
                            href = f"https://{host}{href}"
                        if href:
                            r2 = ctx.request.get(href)
                            if r2.ok and r2.headers.get("content-type", "").startswith("application/pdf"):
                                with open(output_path, "wb") as f:
                                    f.write(r2.body())
                                # 更新统计信息
                                file_size = output_path.stat().st_size
                                self.stats['total_size'] += file_size
                                self.logger.info(f"✅ Playwright 下载成功: 通过 DOM href ({file_size/1024:.1f}KB)")
                                return True, output_path
                            else:
                                self.logger.warning("Playwright: DOM href not PDF")
                        else:
                            self.logger.warning("Playwright: no href")
                    except Exception as e:
                        self.logger.warning(f"Playwright: exception reading href: {e}")

                return False, None

            finally:
                browser.close()

    def __del__(self):
        """析构函数，关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()

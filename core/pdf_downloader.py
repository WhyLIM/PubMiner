# -*- coding: utf-8 -*-
"""
PDF下载模块

负责从多个源下载文献PDF文件，包括DOI查询、SciHub下载、文件管理等功能
基于RecursiveScholarCrawler项目的下载功能进行优化和集成
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
    """PDF下载器 - 支持多源下载、DOI查询、文件管理"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化PDF下载器
        
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
        
        # SciHub镜像配置
        self.scihub_mirrors = config.get('scihub_mirrors', [
            "https://sci-hub.se",
            "https://sci-hub.st", 
            "https://sci-hub.ru",
            "https://www.sci-hub.ren",
            "https://www.sci-hub.ee"
        ])
        
        # 用户代理配置
        self.user_agents = config.get('user_agents', [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ])
        
        # DOI API配置
        self.doi_apis = config.get('doi_apis', {
            'crossref': {
                'url': 'https://api.crossref.org/works',
                'enabled': True,
                'timeout': 15
            }
        })
        
        # 创建下载目录
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化会话
        self.session = requests.Session()
        self._setup_session()
        
        # 初始化SciHub下载器
        self.scihub = SciHubDownloader(
            mirrors=self.scihub_mirrors,
            user_agents=self.user_agents,
            timeout=self.timeout,
            max_retries=self.max_retries
        )
        
        # 统计信息
        self.stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'retries': 0,
            'total_size': 0
        }
        
        self.logger.info(f"✅ PDF 下载器初始化完成，下载目录: {self.download_dir}")
    
    def _setup_session(self):
        """设置HTTP会话"""
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
            cleaned = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:100].replace(" ", "_")
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
            
            # 检查PDF文件头
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
                            self.logger.debug(f"✅ PDF验证成功: {doc.page_count} 页")
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
                if ('pdf' in href.lower() or 
                    link.get('id') == 'download' or
                    'download' in link.get('class', [])):
                    if href.startswith('//'):
                        return f"https:{href}"
                    if not href.startswith('http'):
                        return urljoin(base_url, href)
                    return href
            
            return None
            
        except Exception as e:
            self.logger.error(f"解析 HTML 查找 PDF 链接时出错: {e}")
            return None
    
    def _download_file_with_progress(self, url: str, output_path: Path, 
                                   timeout: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        下载文件并显示进度
        
        Args:
            url: 下载 URL
            output_path: 输出路径
            timeout: 超时时间
            
        Returns:
            (是否成功, 错误信息)
        """
        try:
            timeout = timeout or self.timeout
            
            # 发送HEAD请求获取文件大小
            head_response = self.session.head(url, timeout=timeout)
            total_size = int(head_response.headers.get('content-length', 0))
            
            # 下载文件
            response = self.session.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            downloaded_size = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
            
            # 验证下载的文件
            if self._validate_pdf_file(output_path):
                file_size = output_path.stat().st_size
                self.stats['total_size'] += file_size
                self.logger.info(f"✅ 下载成功: {output_path.name} ({file_size} bytes)")
                return True, None
            else:
                # 删除无效文件
                if output_path.exists():
                    output_path.unlink()
                return False, "下载的文件不是有效的 PDF"
                
        except requests.exceptions.Timeout:
            return False, f"下载超时 ({timeout} 秒)"
        except requests.exceptions.RequestException as e:
            return False, f"网络请求错误: {e}"
        except Exception as e:
            return False, f"下载过程错误: {e}"
    
    def get_download_stats(self) -> Dict[str, Any]:
        """
        获取下载统计信息
        
        Returns:
            统计信息字典
        """
        success_rate = 0
        if self.stats['total_downloads'] > 0:
            success_rate = (self.stats['successful_downloads'] / 
                          self.stats['total_downloads']) * 100
        
        return {
            **self.stats,
            'success_rate': round(success_rate, 2),
            'average_file_size': (self.stats['total_size'] / 
                                self.stats['successful_downloads'] 
                                if self.stats['successful_downloads'] > 0 else 0)
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'retries': 0,
            'total_size': 0
        }
        self.logger.info("📊 下载统计信息已重置")
    
    def _create_download_directory(self) -> bool:
        """创建下载目录"""
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"创建下载目录失败: {e}")
            return False
    
    def _generate_safe_filename(self, doi: str, title: str = None) -> str:
        """生成安全的文件名"""
        # 清理 DOI 作为基础文件名
        safe_doi = doi.replace('/', '_').replace('\\', '_')
        safe_doi = ''.join(c for c in safe_doi if c.isalnum() or c in '._-')
        
        # 如果有标题，添加到文件名中
        if title:
            # 清理标题
            safe_title = ''.join(c for c in title if c.isalnum() or c in ' ._-')
            safe_title = safe_title.replace(' ', '_')[:50]  # 限制长度
            filename = f"{safe_doi}_{safe_title}.pdf"
        else:
            filename = f"{safe_doi}.pdf"
        
        return filename
    
    def _check_file_integrity(self, file_path: Path, expected_size: int = None) -> bool:
        """检查文件完整性"""
        try:
            if not file_path.exists():
                return False
            
            # 检查文件大小
            file_size = file_path.stat().st_size
            if file_size == 0:
                return False
            
            # 如果提供了期望大小，进行比较
            if expected_size and abs(file_size - expected_size) > 1024:  # 允许1KB差异
                self.logger.warning(f"文件大小不匹配: 期望 {expected_size}, 实际 {file_size}")
            
            # 验证 PDF 格式
            with open(file_path, 'rb') as f:
                content = f.read(1024)  # 读取前 1KB 进行快速验证
                if not content.startswith(b'%PDF-'):
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"检查文件完整性失败: {e}")
            return False
    
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
            title1: 标题1
            title2: 标题2
            
        Returns:
            相似度分数 (0-1)
        """
        try:
            from difflib import SequenceMatcher
            normalized1 = self._normalize_title(title1)
            normalized2 = self._normalize_title(title2)
            return SequenceMatcher(None, normalized1, normalized2).ratio()
        except ImportError:
            # 如果没有difflib，使用简单的字符串匹配
            normalized1 = self._normalize_title(title1)
            normalized2 = self._normalize_title(title2)
            if normalized1 == normalized2:
                return 1.0
            elif normalized1 in normalized2 or normalized2 in normalized1:
                return 0.8
            else:
                return 0.0
    
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
        
        params = {
            "query.bibliographic": title,
            "rows": 5,
            "sort": "score",
            "order": "desc"
        }
        
        try:
            # 使用 API 管理器进行限流
            response = api_manager.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
                api_name='crossref'
            )
            
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
                        "doi": item.get("DOI", ""),
                        "title": item_title,
                        "score": score,
                        "publisher": item.get("publisher", ""),
                        "type": item.get("type", ""),
                        "journal": (item.get("container-title") or [""])[0],
                        "authors": item.get("author", []),
                        "published": item.get("published-print", {}).get("date-parts", [[]])[0] if item.get("published-print") else [],
                        "url": item.get("URL", "")
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
        批量查询DOI
        
        Args:
            titles: 标题列表
            max_workers: 最大并发数
            
        Returns:
            DOI查询结果列表
        """
        max_workers = max_workers or min(self.max_workers, len(titles))
        
        self.logger.info(f"📚 开始批量 DOI 查询，共 {len(titles)} 个标题")
        
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交任务
            future_to_title = {
                executor.submit(self.query_doi_by_title, title): title
                for title in titles
            }
            
            # 收集结果
            for future in as_completed(future_to_title):
                title = future_to_title[future]
                try:
                    result = future.result()
                    result['query_title'] = title
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"批量 DOI 查询失败: {title} - {e}")
                    results.append({
                        "doi": None,
                        "error": str(e),
                        "query_title": title
                    })
        
        successful = len([r for r in results if r.get('doi')])
        self.logger.info(f"✅ 批量 DOI 查询完成: {successful}/{len(titles)} 成功")
        
        return results
    
    def download_by_doi(self, doi: str, title: Optional[str] = None, 
                       output_dir: Optional[Path] = None) -> Dict[str, Any]:
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
        
        # 生成文件名
        filename = self._clean_filename(title or "unknown", doi=doi)
        output_path = output_dir / filename
        
        # 检查文件是否已存在
        if output_path.exists() and self._validate_pdf_file(output_path):
            file_size = output_path.stat().st_size
            self.logger.info(f"✅ 文件已存在: {filename} ({file_size} bytes)")
            return {
                'success': True,
                'doi': doi,
                'title': title,
                'local_path': str(output_path),
                'file_size': file_size,
                'status': 'already_exists',
                'error': None
            }
        
        # 尝试下载
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"📥 开始下载 (尝试 {attempt + 1}/{self.max_retries}): {doi}")
                
                # 使用SciHub下载
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
                        'status': 'downloaded',
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
    
    def download_by_pmid(self, pmid: str, title: Optional[str] = None,
                        output_dir: Optional[Path] = None) -> Dict[str, Any]:
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
        
        # 首先查询DOI
        doi_result = self.query_doi_by_title(title)
        
        if doi_result.get('doi'):
            doi = doi_result['doi']
            self.logger.info(f"✅ 通过标题找到 DOI: {doi}")
            
            # 使用找到的DOI下载
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
    
    def download_with_fallback(self, doi: Optional[str], title: str,
                              output_dir: Optional[Path] = None) -> Dict[str, Any]:
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
        
        # 避免重复下载相同的DOI
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
        
        # 步骤3：使用新找到的DOI下载
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
    
    def batch_download(self, items: List[Dict[str, Any]], 
                      max_workers: Optional[int] = None,
                      output_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        批量下载 PDF 文件
        
        Args:
            items: 下载项目列表，每项包含 'doi', 'title', 'pmid' 等字段
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
    
    def retry_failed_downloads(self, failed_results: List[Dict[str, Any]],
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
                retry_result = {
                    'success': False,
                    'error': '缺少重试所需的信息'
                }
            
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

    def __del__(self):
        """析构函数，关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()
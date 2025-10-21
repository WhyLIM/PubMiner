# -*- coding: utf-8 -*-
"""
SciHub下载器模块

专门负责从SciHub镜像站点下载PDF文件
支持多镜像切换、智能重试和下载优化
"""

import time
import random
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import logging

from utils.logger import LoggerMixin

logger = logging.getLogger(__name__)

class SciHubDownloader(LoggerMixin):
    """SciHub下载器"""
    
    def __init__(self, mirrors: List[str], user_agents: List[str], 
                 timeout: int = 30, max_retries: int = 3):
        """
        初始化SciHub下载器
        
        Args:
            mirrors: 镜像站点列表
            user_agents: 用户代理列表
            timeout: 请求超时时间
            max_retries: 最大重试次数
        """
        self.mirrors = mirrors
        self.user_agents = user_agents
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 镜像状态跟踪
        self.mirror_status = {mirror: {'active': True, 'last_success': None, 'failures': 0} 
                             for mirror in mirrors}
        
        # 创建会话
        self.session = requests.Session()
        self._setup_session()
    
    def _setup_session(self):
        """设置HTTP会话"""
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def _get_random_user_agent(self) -> str:
        """获取随机用户代理"""
        return random.choice(self.user_agents)
    
    def _get_active_mirrors(self, exclude: Optional[List[str]] = None) -> List[str]:
        """
        获取活跃镜像列表
        
        Args:
            exclude: 排除的镜像列表
            
        Returns:
            活跃镜像列表
        """
        active_mirrors = [mirror for mirror, status in self.mirror_status.items() 
                         if status['active'] and status['failures'] < 3]
        
        if exclude:
            active_mirrors = [m for m in active_mirrors if m not in exclude]
        
        # 按成功率排序
        active_mirrors.sort(key=lambda m: self.mirror_status[m]['failures'])
        
        return active_mirrors
    
    def _update_mirror_status(self, mirror: str, success: bool):
        """
        更新镜像状态
        
        Args:
            mirror: 镜像地址
            success: 是否成功
        """
        if mirror not in self.mirror_status:
            return
        
        status = self.mirror_status[mirror]
        
        if success:
            status['last_success'] = time.time()
            status['failures'] = 0
            status['active'] = True
        else:
            status['failures'] += 1
            if status['failures'] >= 3:
                status['active'] = False
                self.logger.warning(f"镜像 {mirror} 已被标记为不可用")
    
    def _find_pdf_link(self, html_content: str, base_url: str) -> Optional[str]:
        """
        从HTML内容中查找PDF下载链接
        
        Args:
            html_content: HTML内容
            base_url: 基础URL
            
        Returns:
            PDF下载链接或None
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找embed和iframe标签
            for tag in soup.find_all(['embed', 'iframe']):
                src = tag.get('src')
                if src:
                    if src.startswith('//'):
                        return f"https:{src}"
                    elif not src.startswith('http'):
                        return f"{base_url.rstrip('/')}/{src.lstrip('/')}"
                    return src
            
            # 查找下载链接
            for link in soup.find_all('a', href=True):
                href = link['href']
                if ('pdf' in href.lower() or 
                    link.get('id') == 'download' or
                    'download' in link.get('class', []) or
                    'download' in link.text.lower()):
                    if href.startswith('//'):
                        return f"https:{href}"
                    elif not href.startswith('http'):
                        return f"{base_url.rstrip('/')}/{href.lstrip('/')}"
                    return href
            
            return None
            
        except Exception as e:
            self.logger.error(f"解析HTML查找PDF链接时出错: {e}")
            return None
    
    def download_by_doi(self, doi: str, output_path: Path, 
                       delay: float = 3.0) -> Tuple[bool, Optional[str]]:
        """
        通过DOI从SciHub下载PDF
        
        Args:
            doi: DOI标识符
            output_path: 输出文件路径
            delay: 请求间隔延迟
            
        Returns:
            (是否成功, 错误信息)
        """
        if not doi:
            return False, "DOI为空"
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        active_mirrors = self._get_active_mirrors()
        if not active_mirrors:
            return False, "没有可用的SciHub镜像"
        
        # 随机打乱镜像顺序
        random.shuffle(active_mirrors)
        
        for mirror in active_mirrors:
            try:
                self.logger.info(f"尝试从 {mirror} 下载 DOI: {doi}")
                
                # 设置随机用户代理
                self.session.headers['User-Agent'] = self._get_random_user_agent()
                
                # 构建请求URL
                url = f"{mirror}/{quote_plus(doi)}"
                
                # 获取页面内容
                response = self.session.get(url, timeout=self.timeout)
                
                if response.status_code != 200:
                    self.logger.warning(f"访问 {mirror} 失败，状态码: {response.status_code}")
                    self._update_mirror_status(mirror, False)
                    time.sleep(1)
                    continue
                
                # 查找PDF下载链接
                pdf_link = self._find_pdf_link(response.text, mirror)
                if not pdf_link:
                    self.logger.warning(f"在 {mirror} 未找到PDF下载链接")
                    self._update_mirror_status(mirror, False)
                    time.sleep(1)
                    continue
                
                self.logger.info(f"找到PDF链接: {pdf_link}")
                
                # 下载PDF文件
                pdf_response = self.session.get(pdf_link, timeout=60, stream=True)
                pdf_response.raise_for_status()
                
                # 保存文件
                with open(output_path, 'wb') as f:
                    for chunk in pdf_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # 更新镜像状态
                self._update_mirror_status(mirror, True)
                
                file_size = output_path.stat().st_size
                self.logger.info(f"✅ 从 {mirror} 成功下载PDF ({file_size} bytes)")
                
                return True, None
                
            except requests.exceptions.Timeout:
                self.logger.warning(f"从 {mirror} 下载超时")
                self._update_mirror_status(mirror, False)
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"从 {mirror} 下载网络错误: {e}")
                self._update_mirror_status(mirror, False)
            except Exception as e:
                self.logger.error(f"从 {mirror} 下载出错: {e}")
                self._update_mirror_status(mirror, False)
            
            # 请求间隔
            time.sleep(delay)
        
        return False, "所有SciHub镜像都下载失败"
    
    def get_mirror_stats(self) -> Dict[str, Any]:
        """
        获取镜像统计信息
        
        Returns:
            镜像统计信息
        """
        active_count = sum(1 for status in self.mirror_status.values() if status['active'])
        total_count = len(self.mirror_status)
        
        return {
            'total_mirrors': total_count,
            'active_mirrors': active_count,
            'inactive_mirrors': total_count - active_count,
            'mirror_details': self.mirror_status
        }
    
    def reset_mirror_status(self):
        """重置所有镜像状态"""
        for mirror in self.mirror_status:
            self.mirror_status[mirror] = {
                'active': True, 
                'last_success': None, 
                'failures': 0
            }
        self.logger.info("🔄 镜像状态已重置")
    
    def __del__(self):
        """析构函数，关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()
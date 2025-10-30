# -*- coding: utf-8 -*-
"""
PubMed 文献基本信息获取模块

基于 PubEx 项目，提供高效的文献信息爬取功能
包含断点续传、批量处理、引用关系分析等特性
"""

import sys
import pandas as pd
from Bio import Entrez, Medline
import time
from urllib.error import HTTPError
import re
import ssl
import urllib3
from datetime import datetime
from tqdm import tqdm
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import logging

from utils.logger import LoggerMixin
from utils.file_handler import FileHandler
from utils.api_manager import api_manager

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger(__name__)

class PubMedFetcher(LoggerMixin):
    """PubMed 文献信息获取器 """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 PubMed 获取器
        
        Args:
            config: PubMed 配置
        """
        self.config = config
        self.email = config.get('email', '')
        self.api_key = config.get('api_key', '')
        self.batch_size = config.get('batch_size', 50)
        self.max_retries = config.get('max_retries', 5)
        self.retry_wait_time = config.get('retry_wait_time', 5)
        self.output_dir = Path(config.get('output_dir', './results'))
        self.log_dir = Path(config.get('log_dir', './logs'))
        
        # 引用详情配置
        citation_config = config.get('citation_details', {})
        self.fetch_detailed_pmid_lists = citation_config.get('fetch_detailed_pmid_lists', True)
        
        # 根据是否有 api_key 设置 API 等待时间
        cfg_wait = config.get('api_wait_time', None)
        if cfg_wait is None:
            self.api_wait_time = 0.1 if self.api_key else 0.4
        else:
            self.api_wait_time = float(cfg_wait)
        
        # 设置 Entrez 参数
        if self.email:
            Entrez.email = self.email
        if self.api_key:
            Entrez.api_key = self.api_key
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 提取日期的正则表达式
        self.date_pattern = re.compile(r'\b\d{4}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b')
        
        # 设置 API 限流
        api_name = 'pubmed_with_key' if self.api_key else 'pubmed_no_key'
        self.api_name = api_name
        
        # 统计信息
        self.stats = {
            "total_articles": 0,
            "fetched_articles": 0,
            "retries": 0,
            "start_time": datetime.now(),
        }
    
    @api_manager.with_retry(max_retries=5, retry_delay=2.0)
    def _fetch_with_retry(self, fetch_function, *args, **kwargs):
        """
        带重试的 API 请求
        
        Args:
            fetch_function: Entrez 函数
            *args, **kwargs: 函数参数
            
        Returns:
            API 响应结果
        """
        try:
            # 应用限流
            if self.api_name in api_manager.rate_limiters:
                api_manager.rate_limiters[self.api_name].wait_if_needed()
            
            result = fetch_function(*args, **kwargs)
            return result
            
        except HTTPError as e:
            self.logger.warning(f"HTTP 错误 : {e.code} - {e.reason}")
            self.stats["retries"] += 1
            raise
        except Exception as e:
            self.logger.warning(f"API 调用错误 : {e}")
            self.stats["retries"] += 1
            raise
    
    def extract_publication_date(self, record: Dict[str, Any]) -> str:
        """
        从记录中提取出版日期
        
        Args:
            record: 文献记录
            
        Returns:
            格式化的出版日期
        """
        if 'DP' in record:
            match = self.date_pattern.search(record['DP'])
            if match:
                return match.group()
        
        if 'SO' in record:
            match = self.date_pattern.search(record['SO'])
            if match:
                return match.group()
        
        return 'NA'
    
    def fetch_citation_data_batch(self, pmid_list: List[str]) -> Dict[str, tuple]:
        """
        批量获取引用信息
        
        Args:
            pmid_list: PMID 列表
            
        Returns:
            引用信息字典 {PMID: (cited_by_list, references_list)}
        """
        citation_dict = {}
        
        if not pmid_list:
            return citation_dict
        
        # 如果不需要详细 PMID 列表，只获取数量
        if not self.fetch_detailed_pmid_lists:
            self.logger.debug(f" 只获取引用数量，不获取详细 PMID 列表 ")
            return self._fetch_citation_counts_only(pmid_list)
        
        # 获取详细的 PMID 列表
        self.logger.debug(f" 获取详细的引用 PMID 列表 ")
        
        # 使用重试机制批量获取引用信息
        for attempt in range(self.max_retries):
            try:
                # 批量获取引用信息
                handle_elink = Entrez.elink(
                    db="pubmed",
                    id=pmid_list,
                    linkname="pubmed_pubmed_citedin,pubmed_pubmed_refs",
                    retmode="xml",
                    cmd="neighbor"
                )
                records_elink = Entrez.read(handle_elink)
                handle_elink.close()
                
                # 处理每个 PMID 的结果
                for i, record in enumerate(records_elink):
                    pmid = pmid_list[i] if i < len(pmid_list) else None
                    if not pmid:
                        continue
                        
                    linked = []
                    references = []
                    
                    if "LinkSetDb" in record:
                        for linkset in record["LinkSetDb"]:
                            if linkset["LinkName"] == "pubmed_pubmed_citedin" and "Link" in linkset:
                                linked.extend(link["Id"] for link in linkset["Link"] if link.get("Id"))
                            elif linkset["LinkName"] == "pubmed_pubmed_refs" and "Link" in linkset:
                                references.extend(link["Id"] for link in linkset["Link"] if link.get("Id"))
                    
                    citation_dict[pmid] = (linked, references)
                
                break
                
            except HTTPError as e:
                if e.code in [429, 500, 502, 503, 504]:
                    wait_time = self.retry_wait_time * (attempt + 1)
                    self.logger.warning(f" 批量获取引用信息 HTTP 错误 {e.code}，等待 {wait_time} 秒后重试 ( 尝试 {attempt + 1}/{self.max_retries})...")
                    self.stats["retries"] += 1
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f" 批量获取引用信息 HTTP 错误 : {e}")
                    break
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['eof', 'connection', 'closed', 'timeout', 'read failed']):
                    wait_time = self.retry_wait_time * (attempt + 1)
                    self.logger.warning(f" 批量获取引用信息网络错误，等待 {wait_time} 秒后重试 ( 尝试 {attempt + 1}/{self.max_retries}): {e}")
                    self.stats["retries"] += 1
                    time.sleep(wait_time)
                    if attempt < self.max_retries - 1:
                        continue
                else:
                    self.logger.warning(f" 批量获取引用信息失败 : {e}")
                    if attempt < self.max_retries - 1:
                        self.stats["retries"] += 1
                        time.sleep(self.retry_wait_time)
                        continue
                break
        
        return citation_dict
    
    def _fetch_citation_counts_only(self, pmid_list: List[str]) -> Dict[str, tuple]:
        """
        只获取引用数量，不获取详细的 PMID 列表
        
        Args:
            pmid_list: PMID 列表
            
        Returns:
            引用信息字典 {PMID: (cited_count, references_count)}
        """
        citation_dict = {}
        
        # 使用重试机制批量获取引用数量
        for attempt in range(self.max_retries):
            try:
                # 批量获取引用信息（只获取数量）
                handle_elink = Entrez.elink(
                    db="pubmed",
                    id=pmid_list,
                    linkname="pubmed_pubmed_citedin,pubmed_pubmed_refs",
                    retmode="xml",
                    cmd="neighbor"
                )
                records_elink = Entrez.read(handle_elink)
                handle_elink.close()
                
                # 处理每个 PMID 的结果，只计算数量
                for i, record in enumerate(records_elink):
                    pmid = pmid_list[i] if i < len(pmid_list) else None
                    if not pmid:
                        continue
                        
                    cited_count = 0
                    references_count = 0
                    
                    if "LinkSetDb" in record:
                        for linkset in record["LinkSetDb"]:
                            if linkset["LinkName"] == "pubmed_pubmed_citedin" and "Link" in linkset:
                                cited_count = len(linkset["Link"])
                            elif linkset["LinkName"] == "pubmed_pubmed_refs" and "Link" in linkset:
                                references_count = len(linkset["Link"])
                    
                    # 使用 COUNT_ONLY 标记传递数量信息
                    citation_dict[pmid] = (
                        [f"COUNT_ONLY:{cited_count}"],  # 特殊标记表示只有数量
                        [f"COUNT_ONLY:{references_count}"]
                    )
                
                break
                
            except HTTPError as e:
                if e.code in [429, 500, 502, 503, 504]:
                    wait_time = self.retry_wait_time * (attempt + 1)
                    self.logger.warning(f" 批量获取引用数量 HTTP 错误 {e.code}，等待 {wait_time} 秒后重试 ( 尝试 {attempt + 1}/{self.max_retries})...")
                    self.stats["retries"] += 1
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f" 批量获取引用数量 HTTP 错误 : {e}")
                    break
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['eof', 'connection', 'closed', 'timeout', 'read failed']):
                    wait_time = self.retry_wait_time * (attempt + 1)
                    self.logger.warning(f" 批量获取引用数量网络错误，等待 {wait_time} 秒后重试 ( 尝试 {attempt + 1}/{self.max_retries}): {e}")
                    self.stats["retries"] += 1
                    time.sleep(wait_time)
                    if attempt < self.max_retries - 1:
                        continue
                else:
                    self.logger.warning(f" 批量获取引用数量失败 : {e}")
                    if attempt < self.max_retries - 1:
                        self.stats["retries"] += 1
                        time.sleep(self.retry_wait_time)
                        continue
                break
        
        return citation_dict
    
    def create_record_dict(self, record: Dict[str, Any], publication_date: str, 
                          cited_by: List[str], references: List[str]) -> Dict[str, Any]:
        """
        创建标准化的文献记录字典
        
        Args:
            record: 原始记录
            publication_date: 出版日期
            cited_by: 被引用列表或数量标记
            references: 参考文献列表或数量标记
            
        Returns:
            标准化记录字典
        """
        # 处理只有数量的情况
        if cited_by and len(cited_by) == 1 and str(cited_by[0]).startswith("COUNT_ONLY:"):
            cited_count = int(str(cited_by[0]).replace("COUNT_ONLY:", ""))
            cited_by = []  # 清空列表，只保留数量
        else:
            cited_count = len(cited_by) if cited_by else 0
            
        if references and len(references) == 1 and str(references[0]).startswith("COUNT_ONLY:"):
            references_count = int(str(references[0]).replace("COUNT_ONLY:", ""))
            references = []  # 清空列表，只保留数量
        else:
            references_count = len(references) if references else 0
        return {
            'Title': record.get('TI', 'NA'),
            'Status': record.get('STAT', 'NA'),
            'Last_Revision_Date': record.get('LR', 'NA'),
            'ISSN': record.get('IS', 'NA'),
            'Type': record.get('PT', 'NA'),
            'Year_of_Publication': record.get('DP', 'NA').split(' ')[0] if 'DP' in record else 'NA',
            'Date_of_Electronic_Publication': record.get('DEP', 'NA'),
            'Publication_Date': publication_date,
            'Place_of_Publication': record.get('PL', 'NA'),
            'First_Author': record.get('FAU', 'NA'),
            'Authors': record.get('AU', 'NA'),
            'Affiliation': record.get('AD', 'NA'),
            'Abstract': record.get('AB', 'NA'),
            'Language': record.get('LA', 'NA'),
            'Keywords': record.get('OT', 'NA'),
            'PMID': record.get('PMID', 'NA'),
            'Medline_Volume': record.get('VI', 'NA'),
            'Medline_Issue': record.get('IP', 'NA'),
            'Medline_Pagination': record.get('PG', 'NA'),
            'DOI': record.get('LID', 'NA').split(' ')[0] if 'LID' in record else 'NA',
            'PMC': record.get('PMC', 'NA'),
            'Processing_History': record.get('PHST', 'NA'),
            'Publication_Status': record.get('PST', 'NA'),
            'Journal_Title_Abbreviation': record.get('TA', 'NA'),
            'Journal_Title': record.get('JT', 'NA'),
            'Journal_ID': record.get('JID', 'NA'),
            'Source': record.get('SO', 'NA'),
            'Grant_List': record.get('GR', 'NA'),
            'Cited_Count': cited_count,
            'Cited_By': cited_by,
            'References_Count': references_count,
            'References_PMID': references,
        }
    
    def check_existing_data(self, output_file: Path) -> tuple:
        """
        检查现有数据（断点续传）
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            ( 已处理的 PMID 集合 , 已有数据列表 )
        """
        try:
            if output_file.exists() and output_file.stat().st_size > 0:
                self.logger.info(f" 📁 检测到现有数据文件 : {output_file}")
                existing_df = pd.read_csv(output_file, keep_default_na=False, na_values=[''])
                self.logger.info(f" 📊 已有 {len(existing_df)} 篇文献，将进行断点续传 ")
                
                valid_pmids = existing_df['PMID'].dropna().astype(str)
                valid_pmids = [pmid for pmid in valid_pmids if pmid.strip() and pmid != 'nan']
                return set(valid_pmids), existing_df.to_dict('records')
            else:
                return set(), []
        except Exception as e:
            self.logger.error(f" 读取现有数据时出错 : {e}")
            return set(), []
    
    def save_results(self, data: List[Dict[str, Any]], output_file: Path):
        """
        保存结果到 CSV 文件（使用 DataProcessor 处理引用详情配置）
        
        Args:
            data: 数据列表
            output_file: 输出文件路径
        """
        try:
            # 使用 DataProcessor 来处理 CSV 生成，支持引用详情配置
            from core.data_processor import DataProcessor
            
            # 使用当前 PubMedFetcher 的配置（包含正确的引用详情设置）
            output_config = {
                'csv_encoding': 'utf-8-sig',
                'date_format': '%Y-%m-%d',
                'citation_details': {
                    'fetch_detailed_pmid_lists': self.fetch_detailed_pmid_lists,
                    'citation_dir': 'citations'
                }
            }
            
            # 创建 DataProcessor 实例
            processor = DataProcessor(output_config)
            
            # 创建简单的模板（只包含基本字段，不包含提取字段）
            basic_template = {
                'name': 'Basic PubMed Data',
                'version': '1.0',
                'description': 'Basic PubMed paper information',
                'fields': {}  # 空字段，只使用基本信息
            }
            
            # 使用 DataProcessor 生成 CSV（会应用引用详情配置）
            success = processor.generate_csv(data, basic_template, output_file)
            
            if success:
                self.logger.debug(f" ✅ 结果已保存 : {output_file}")
            else:
                # 如果 DataProcessor 失败，回退到原始方法
                self.logger.warning(" ⚠️ DataProcessor 保存失败，使用基础方法 ")
                self._save_results_basic(data, output_file)
            
        except Exception as e:
            self.logger.error(f" ❌ 保存数据时出错 : {e}")
            # 出错时使用基础保存方法
            self._save_results_basic(data, output_file)
    
    def _save_results_basic(self, data: List[Dict[str, Any]], output_file: Path):
        """
        基础 CSV 保存方法（不支持引用详情配置）
        
        Args:
            data: 数据列表
            output_file: 输出文件路径
        """
        try:
            df = pd.DataFrame(data)
            df = df.fillna('NA')
            df.to_csv(output_file, index=False, na_rep='NA', encoding='utf-8-sig')
            
            # 创建备份到 results/backup 目录
            backup_dir = Path('results') / 'backup'
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            backup_filename = f"{output_file.stem}_backup.csv"
            backup_file = backup_dir / backup_filename
            
            df.to_csv(backup_file, index=False, na_rep='NA', encoding='utf-8-sig')
            self.logger.debug(f" ✅ 创建备份文件 : {backup_file}")
            
            self.logger.debug(f" ✅ 结果已保存 : {output_file}")
            
        except Exception as e:
            self.logger.error(f" ❌ 基础保存方法失败 : {e}")
            raise
    
    def fetch_by_query(self, query: str, resume: bool = True, max_results: int = None) -> List[Dict[str, Any]]:
        """
        根据查询词获取文献信息
        
        Args:
            query: PubMed 查询词
            resume: 是否启用断点续传
            max_results: 最大结果数量限制
            
        Returns:
            文献信息列表
        """
        self.logger.info(f" 🔍 开始检索 : {query}")
        
        # 生成输出文件名
        safe_query = re.sub(r'[ ^ \w\s-]', '', query.replace(' ', '_'))[:50]
        output_file = self.output_dir / f"pubminer_{safe_query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # 检查现有数据
        existing_pmids, existing_data = self.check_existing_data(output_file) if resume else (set(), [])
        
        # 搜索文献
        self.logger.info(" 📊 正在搜索文献 ...")
        handle = self._fetch_with_retry(
            Entrez.esearch,
            db="pubmed",
            term=query,
            usehistory="y",
            retmax=0
        )
        search_results = Entrez.read(handle)
        handle.close()
        
        count = int(search_results.get("Count", 0) or 0)
        webenv = search_results.get("WebEnv")
        query_key = search_results.get("QueryKey")
        
        # 应用最大结果数限制
        if max_results is not None and max_results > 0:
            count = min(count, max_results)
            self.logger.info(f" 📚 找到文献总数 : {search_results.get('Count', 0)}, 限制获取 : {count} 篇 ")
        else:
            self.logger.info(f" 📚 找到 {count} 篇文献 ")
        
        self.stats["total_articles"] = count
        
        if count == 0:
            self.logger.warning(" ⚠️ 没有找到符合条件的文献 ")
            return []
        
        # 获取所有 PMID（用于断点续传判断）
        if resume and existing_pmids:
            self.logger.info(" 🔍 获取 PMID 列表用于断点续传 ...")
            all_pmids = []
            pmid_batch_size = 9999
            
            for start in range(0, count, pmid_batch_size):
                retmax = min(pmid_batch_size, count - start)
                handle = self._fetch_with_retry(
                    Entrez.esearch,
                    db="pubmed",
                    term=query,
                    retstart=start,
                    retmax=retmax,
                    usehistory="n"
                )
                results = Entrez.read(handle)
                handle.close()
                all_pmids.extend(results["IdList"])
                time.sleep(self.api_wait_time)
            
            # 过滤已处理的 PMID
            new_pmids = [pmid for pmid in all_pmids if pmid not in existing_pmids]
            self.logger.info(f" 📊 需要处理 {len(new_pmids)} 篇新文献 ")
            
            if len(new_pmids) == 0:
                self.logger.info(" ✅ 所有文献都已处理完成 ")
                return existing_data
        
        # 批量获取文献详情
        self.logger.info(" 📚 开始批量获取文献详情 ...")
        data = list(existing_data)  # 复制现有数据
        
        # 进度条
        total_batches = (count + self.batch_size - 1) // self.batch_size
        batch_progress = tqdm(
            total=total_batches,
            desc=" 📦 批次进度 ",
            unit="batch",
            position=0
        )
        
        processed_count = 0
        
        for start in range(0, count, self.batch_size):
            # 计算当前批次应该获取的数量
            current_batch_size = min(self.batch_size, count - start)
            
            # 使用 WebEnv 和 QueryKey 获取数据
            handle = self._fetch_with_retry(
                Entrez.efetch,
                db="pubmed",
                rettype='medline',
                retmode="text",
                retstart=start,
                retmax=current_batch_size,
                webenv=webenv,
                query_key=query_key
            )
            records = list(Medline.parse(handle))
            handle.close()
            
            # 过滤出需要处理的记录
            if resume:
                records_to_process = [
                    r for r in records
                    if r.get('PMID') and r.get('PMID') not in existing_pmids
                ]
            else:
                records_to_process = records
            
            if not records_to_process:
                batch_progress.update(1)
                time.sleep(self.api_wait_time)
                continue
            
            # 批量获取引用信息
            batch_pmids = [record.get('PMID') for record in records_to_process]
            citation_data = self.fetch_citation_data_batch(batch_pmids)
            
            # 处理每篇文献
            for record in records_to_process:
                pmid = record.get('PMID', 'NA')
                
                # 获取引用信息
                cited_by, references = citation_data.get(pmid, ([], []))
                
                # 提取发布日期
                publication_date = self.extract_publication_date(record)
                
                # 创建记录
                record_dict = self.create_record_dict(record, publication_date, cited_by, references)
                data.append(record_dict)
                
                processed_count += 1
                self.stats["fetched_articles"] += 1
            
            # 定期保存
            if processed_count > 0:
                self.save_results(data, output_file)
            
            batch_progress.update(1)
            time.sleep(self.api_wait_time)
        
        batch_progress.close()
        
        # 最终保存
        self.save_results(data, output_file)
        
        # 显示统计信息
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds() / 60
        self.logger.info(f" ✅ 完成 ! 总共处理 {len(data)} 篇文献 ")
        self.logger.info(f" ⏱️ 用时 : {elapsed:.2f} 分钟 ")
        self.logger.info(f" 💾 结果保存至 : {output_file}")
        
        return data
    
    def fetch_by_pmid_list(self, pmid_list: List[str], resume: bool = True) -> List[Dict[str, Any]]:
        """
        根据 PMID 列表获取文献信息
        
        Args:
            pmid_list: PMID 列表
            resume: 是否启用断点续传
            
        Returns:
            文献信息列表
        """
        pmid_list = [str(pmid).strip() for pmid in pmid_list if str(pmid).strip()]
        self.logger.info(f" 📋 根据 PMID 列表获取文献信息，共 {len(pmid_list)} 个 PMID")
        
        if not pmid_list:
            self.logger.warning(" ⚠️ PMID 列表为空 ")
            return []
        
        # 生成输出文件名
        output_file = self.output_dir / f"pubminer_pmids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # 检查现有数据
        existing_pmids, existing_data = self.check_existing_data(output_file) if resume else (set(), [])
        
        # 过滤已处理的 PMID
        if resume and existing_pmids:
            pmid_list = [pmid for pmid in pmid_list if pmid not in existing_pmids]
            self.logger.info(f" 📊 需要处理 {len(pmid_list)} 个新 PMID")
        
        if not pmid_list:
            self.logger.info(" ✅ 所有 PMID 都已处理完成 ")
            return existing_data
        
        self.stats["total_articles"] = len(pmid_list)
        data = list(existing_data)
        
        # 批量处理
        self.logger.info(" 📚 开始批量获取文献详情 ...")
        
        total_batches = (len(pmid_list) + self.batch_size - 1) // self.batch_size
        batch_progress = tqdm(
            total=total_batches,
            desc=" 📦 批次进度 ",
            unit="batch"
        )
        
        for i in range(0, len(pmid_list), self.batch_size):
            batch_pmids = pmid_list[i:i + self.batch_size]
            
            try:
                # 获取文献详情
                handle = self._fetch_with_retry(
                    Entrez.efetch,
                    db="pubmed",
                    id=batch_pmids,
                    rettype='medline',
                    retmode="text"
                )
                records = list(Medline.parse(handle))
                handle.close()
                
                # 批量获取引用信息
                citation_data = self.fetch_citation_data_batch(batch_pmids)
                
                # 处理每篇文献
                for record in records:
                    pmid = record.get('PMID', 'NA')
                    
                    # 获取引用信息
                    cited_by, references = citation_data.get(pmid, ([], []))
                    
                    # 提取发布日期
                    publication_date = self.extract_publication_date(record)
                    
                    # 创建记录
                    record_dict = self.create_record_dict(record, publication_date, cited_by, references)
                    data.append(record_dict)
                    
                    self.stats["fetched_articles"] += 1
                
                # 定期保存
                self.save_results(data, output_file)
                
            except Exception as e:
                self.logger.error(f" ❌ 处理批次失败 : {e}")
                continue
            
            batch_progress.update(1)
            time.sleep(self.api_wait_time)
        
        batch_progress.close()
        
        # 最终保存
        self.save_results(data, output_file)
        
        # 显示统计信息
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds() / 60
        self.logger.info(f" ✅ 完成 ! 总共处理 {len(data)} 篇文献 ")
        self.logger.info(f" ⏱️ 用时 : {elapsed:.2f} 分钟 ")
        self.logger.info(f" 💾 结果保存至 : {output_file}")
        
        return data
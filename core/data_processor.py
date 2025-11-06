# -*- coding: utf-8 -*-
"""
数据处理模块

负责处理分析结果、生成 CSV 输出、数据验证和统计报告
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime
import json
import re

from utils.logger import LoggerMixin
from utils.file_handler import FileHandler

logger = logging.getLogger(__name__)


class DataProcessor(LoggerMixin):
    """数据处理器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据处理器

        Args:
            config: 输出配置
        """
        self.config = config
        self.csv_encoding = config.get('csv_encoding', 'utf-8-sig')
        self.date_format = config.get('date_format', '%Y-%m-%d')
        self.na_values = config.get('na_values', ['NA', 'N/A', '未提及', '未明确', ''])
        self.max_cell_length = config.get('max_cell_length', 32767)
        self.enable_backup = config.get('enable_backup', True)

        # 引用详情配置 - 控制是否获取详细 PMID 列表
        citation_config = config.get('citation_details', {})
        self.fetch_detailed_pmid_lists = citation_config.get('fetch_detailed_pmid_lists', True)
        self.citation_dir = citation_config.get('citation_dir', 'citations')
        self.citation_fields = ['Cited_By', 'References_PMID']  # 引用字段列表

    def _generate_csv_filename(self, prefix: str = "", identifier: str = "") -> str:
        """
        生成 CSV 文件名

        Args:
            prefix: 文件名前缀
            identifier: 标识符（可选）

        Returns:
            生成的文件名
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 清理标识符
        if identifier:
            safe_identifier = re.sub(r'[^\w\s-]', ' ', identifier.replace(' ', '_'))[:50]
        else:
            safe_identifier = ""

        # 构建文件名
        parts = []
        if prefix:
            parts.append(prefix)
        if safe_identifier:
            parts.append(safe_identifier)
        parts.append(timestamp)

        return "_".join(parts) + ".csv"

    def _clean_cell_content(self, content: Any) -> str:
        """
        清理单元格内容

        Args:
            content: 原始内容

        Returns:
            清理后的内容
        """
        if content is None:
            return 'NA'

        # 转换为字符串
        content_str = str(content).strip()

        # 处理空值
        if content_str in self.na_values:
            return 'NA'

        # 清理特殊字符
        content_str = re.sub(r'\s+', ' ', content_str)  # 合并多个空白字符
        content_str = content_str.replace('\r\n', '').replace('\n', ' ').replace('\r', ' ')

        # 长度限制
        if len(content_str) > self.max_cell_length:
            content_str = content_str[:self.max_cell_length - 3] + '...'
            self.logger.debug(f"单元格内容过长，已截断到 {self.max_cell_length} 字符")

        return content_str

    def _needs_detailed_pmid_lists(self, paper: Dict[str, Any]) -> bool:
        """
        检查是否需要获取详细的 PMID 列表

        Args:
            paper: 文献数据

        Returns:
            是否需要详细 PMID 列表
        """
        return self.fetch_detailed_pmid_lists

    def _save_citation_file(self, paper: Dict[str, Any], output_dir: Path) -> Optional[str]:
        """
        保存引用信息到单独的 JSON 文件

        Args:
            paper: 文献数据
            output_dir: 输出目录

        Returns:
            引用文件名，如果失败返回 None
        """
        try:
            pmid = paper.get('PMID', 'unknown')
            citation_filename = f"citations_{pmid}.json"

            # 创建引用目录
            citation_dir = output_dir / self.citation_dir
            citation_dir.mkdir(exist_ok=True)

            citation_file_path = citation_dir / citation_filename

            # 构建引用信息数据
            citation_info = {
                'PMID': pmid,
                'Cited_By': paper.get('Cited_By', []),
                'Cited_Count': len(paper.get('Cited_By', [])),
                'References_PMID': paper.get('References_PMID', []),
                'References_Count': len(paper.get('References_PMID', [])),
                'Last_Updated': datetime.now().isoformat(),
                'Data_Source': 'PubMed API',
                'Fetcher_Version': 'PubMiner v1.0'
            }

            # 保存 JSON 文件
            with open(citation_file_path, 'w', encoding='utf-8') as f:
                json.dump(citation_info, f, ensure_ascii=False, indent=2)

            self.logger.debug(f"✅ 保存引用文件: {citation_filename}")
            return citation_filename

        except Exception as e:
            self.logger.error(f"❌ 保存引用文件失败 PMID {pmid}: {e}")
            return None

    def _create_csv_headers(self, template: Dict[str, Any]) -> List[str]:
        """
        创建 CSV 表头

        Args:
            template: 提取模板

        Returns:
            表头列表
        """
        # 基本信息表头 - 检查数据中实际存在的字段
        basic_headers = [
            'PMID', 'Title', 'Authors', 'Year_of_Publication', 'Journal_Title', 'DOI', 'Abstract', 'Keywords'
        ]

        # 可选的基础字段（可能不存在于所有记录中）
        optional_headers = ['Text_Source', 'Extraction_Status', 'Publication_Date', 'First_Author', 'Language']

        # 引用信息表头（统一只包含统计字段，不包含详细列表字段）
        citation_headers = ['Cited_Count', 'References_Count']

        # 如果启用了详细 PMID 列表功能，添加相关管理字段
        if self.fetch_detailed_pmid_lists:
            citation_headers.extend(['Storage_Type', 'Citation_File', 'Last_Updated'])

        # 提取字段表头
        extraction_headers = []
        fields = template.get('fields', {})

        for field_key, field_info in fields.items():
            csv_header = field_info.get('csv_header', field_key)
            extraction_headers.append(csv_header)

        return basic_headers + optional_headers + citation_headers + extraction_headers

    def _prepare_row_data(self, paper: Dict[str, Any], template: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
        """
        准备单行数据

        Args:
            paper: 文献记录
            template: 提取模板
            output_dir: 输出目录（用于保存引用文件）

        Returns:
            行数据字典
        """
        pmid = paper.get('PMID', '')

        # 检查是否需要详细 PMID 列表
        needs_detailed_lists = self._needs_detailed_pmid_lists(paper)

        # 基本信息
        row_data = {
            'PMID': self._clean_cell_content(pmid),
            'Title': self._clean_cell_content(paper.get('Title', '')),
            'Authors': self._clean_cell_content(paper.get('Authors', '')),
            'Year_of_Publication': self._clean_cell_content(paper.get('Year_of_Publication', '')),
            'Journal_Title': self._clean_cell_content(paper.get('Journal_Title', '')),
            'DOI': self._clean_cell_content(paper.get('DOI', '')),
            'Abstract': self._clean_cell_content(paper.get('Abstract', '')),
            'Keywords': self._clean_cell_content(paper.get('Keywords', '')),
            'Text_Source': self._clean_cell_content(paper.get('text_source', '')),
            'Extraction_Status': self._clean_cell_content(paper.get('extraction_status', '')),
            'Publication_Date': self._clean_cell_content(paper.get('Publication_Date', '')),
            'First_Author': self._clean_cell_content(paper.get('First_Author', '')),
            'Language': self._clean_cell_content(paper.get('Language', ''))
        }

        # 处理引用信息
        if self.fetch_detailed_pmid_lists:
            # 详细模式：保存完整 PMID 列表到 JSON 文件
            citation_filename = self._save_citation_file(paper, output_dir)

            if citation_filename:
                self.logger.info(
                    f"PMID {pmid}: 保存详细引用列表 (被引用数: {len(paper.get('Cited_By', []))}, 参考文献数: {len(paper.get('References_PMID', []))})"
                )

                # 详细模式的 CSV 字段
                row_data.update({
                    'Cited_Count': len(paper.get('Cited_By', [])),
                    'References_Count': len(paper.get('References_PMID', [])),
                    'Storage_Type': 'detailed_lists',
                    'Citation_File': citation_filename,
                    'Last_Updated': datetime.now().isoformat()
                })
            else:
                # JSON 文件保存失败，回退到统计模式
                self.logger.warning(f"PMID {pmid}: 详细列表保存失败，回退到统计模式")
                row_data.update({
                    'Cited_Count': len(paper.get('Cited_By', [])),
                    'References_Count': len(paper.get('References_PMID', [])),
                    'Storage_Type': 'counts_only',
                    'Citation_File': 'NA',
                    'Last_Updated': datetime.now().isoformat()
                })
        else:
            # 仅数量模式：只保存引用统计，不包含额外字段
            cited_count = paper.get('Cited_Count', len(paper.get('Cited_By', [])))
            references_count = paper.get('References_Count', len(paper.get('References_PMID', [])))

            self.logger.info(f"PMID {pmid}: 仅数量模式 (被引用数: {cited_count}, 参考文献数: {references_count})")
            row_data.update({'Cited_Count': cited_count, 'References_Count': references_count})

        # 提取的字段信息
        fields = template.get('fields', {})
        for field_key, field_info in fields.items():
            csv_header = field_info.get('csv_header', field_key)
            field_value = paper.get(field_key, '')
            row_data[csv_header] = self._clean_cell_content(field_value)

        return row_data

    def generate_csv(self, papers: List[Dict[str, Any]], template: Dict[str, Any], output_path: Path,
                    filename_prefix: str = "", identifier: str = "") -> bool:
        """
        生成 CSV 输出文件

        Args:
            papers: 文献列表
            template: 提取模板
            output_path: 输出文件路径（可以是目录或完整文件路径）
            filename_prefix: 文件名前缀（可选）
            identifier: 标识符（可选）

        Returns:
            是否生成成功
        """
        try:
            # 如果 output_path 是目录，生成文件名
            if output_path.is_dir():
                filename = self._generate_csv_filename(filename_prefix, identifier)
                output_path = output_path / filename

            self.logger.info(f"📊 开始生成 CSV 文件: {output_path}")

            if not papers:
                self.logger.warning("⚠️ 没有数据可导出")
                return False

            # 确保输出目录存在
            output_dir = output_path.parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # 统计存储方式使用情况
            detailed_lists_count = 0
            counts_only_count = 0

            # 创建表头
            headers = self._create_csv_headers(template)

            # 准备数据
            rows_data = []
            for paper in papers:
                row_data = self._prepare_row_data(paper, template, output_dir)
                rows_data.append(row_data)

                # 统计存储方式
                storage_type = row_data.get('Storage_Type', 'counts_only')
                if storage_type == 'detailed_lists':
                    detailed_lists_count += 1
                else:
                    counts_only_count += 1

            # 创建 DataFrame
            df = pd.DataFrame(rows_data, columns=headers)

            # 填充缺失值
            df = df.fillna('NA')

            # 保存 CSV 文件
            df.to_csv(output_path, index=False, encoding=self.csv_encoding, na_rep='NA')

            # 创建备份到 results/backup 目录
            if self.enable_backup:
                backup_dir = Path('results') / 'backup'
                backup_dir.mkdir(parents=True, exist_ok=True)

                backup_filename = f"{output_path.stem}_backup.csv"
                backup_path = backup_dir / backup_filename

                df.to_csv(backup_path, index=False, encoding=self.csv_encoding, na_rep='NA')
                self.logger.debug(f"✅ 创建备份文件: {backup_path}")

            # 记录存储统计信息
            self.logger.info(f"✅ CSV 文件生成成功: {output_path}")
            self.logger.info(f"📋 包含 {len(df)} 行数据，{len(df.columns)} 列")
            self.logger.info(f"📊 存储方式统计: 详细列表 {detailed_lists_count} 篇，仅统计 {counts_only_count} 篇")

            if detailed_lists_count > 0:
                citation_dir = output_path.parent / self.citation_dir
                self.logger.info(f"📁 详细引用列表保存在: {citation_dir}")
                self.logger.info(f"💡 详细列表模式提供完整的 PMID 引用信息")

            return True

        except Exception as e:
            self.logger.error(f"❌ 生成 CSV 文件失败: {e}")
            return False

    def load_citation_data(self, csv_file_path: Path, pmid: str) -> Optional[Dict[str, Any]]:
        """
        从分离存储中加载引用数据

        Args:
            csv_file_path: CSV 文件路径
            pmid: 文献 PMID

        Returns:
            引用数据字典，如果失败返回 None
        """
        try:
            # 读取 CSV 文件获取引用文件名
            df = pd.read_csv(csv_file_path)
            paper_row = df[df['PMID'].astype(str) == str(pmid)]

            if paper_row.empty:
                self.logger.warning(f"未找到 PMID {pmid} 的数据")
                return None

            storage_type = paper_row['Storage_Type'].iloc[0] if 'Storage_Type' in paper_row.columns else 'counts_only'

            if storage_type == 'detailed_lists':
                citation_file = paper_row['Citation_File'].iloc[0]
                citation_path = csv_file_path.parent / citation_file

                if citation_path.exists():
                    with open(citation_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    self.logger.error(f"引用文件不存在: {citation_path}")
                    return None
            else:
                # 内联存储，从 CSV 中直接读取
                citation_data = {
                    'PMID':
                    pmid,
                    'Cited_By':
                    paper_row.get('Cited_By', []).iloc[0] if 'Cited_By' in paper_row.columns else [],
                    'References_PMID':
                    paper_row.get('References_PMID', []).iloc[0] if 'References_PMID' in paper_row.columns else [],
                    'Cited_Count':
                    paper_row.get('Cited_Count', 0).iloc[0] if 'Cited_Count' in paper_row.columns else 0,
                    'References_Count':
                    paper_row.get('References_Count', 0).iloc[0] if 'References_Count' in paper_row.columns else 0,
                    'Storage_Type':
                    storage_type
                }
                return citation_data

        except Exception as e:
            self.logger.error(f"加载引用数据失败 PMID {pmid}: {e}")
            return None

    def get_storage_statistics(self, csv_file_path: Path) -> Dict[str, Any]:
        """
        获取存储方式统计信息

        Args:
            csv_file_path: CSV 文件路径

        Returns:
            存储统计信息
        """
        try:
            df = pd.read_csv(csv_file_path)

            if 'Storage_Type' not in df.columns:
                return {
                    'total_papers': len(df),
                    'detailed_lists': 0,
                    'counts_only': len(df),
                    'storage_types': {
                        'counts_only': len(df)
                    }
                }

            storage_counts = df['Storage_Type'].value_counts().to_dict()

            stats = {
                'total_papers': len(df),
                'detailed_lists': storage_counts.get('detailed_lists', 0),
                'counts_only': storage_counts.get('counts_only', 0),
                'storage_types': storage_counts,
                'detailed_lists_rate': storage_counts.get('detailed_lists', 0) / len(df) * 100 if len(df) > 0 else 0
            }

            return stats

        except Exception as e:
            self.logger.error(f"获取存储统计失败: {e}")
            return {}

    def generate_statistics(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成处理统计信息

        Args:
            papers: 文献列表

        Returns:
            统计信息字典
        """
        if not papers:
            return {'total_papers': 0, 'analyzed_papers': 0, 'extracted_fields': 0, 'processing_time': 0, 'success_rate': 0}

        # 基本统计
        total_papers = len(papers)
        analyzed_papers = len([p for p in papers if p.get('extraction_status') == 'success'])

        # 文本来源统计
        text_sources = {}
        for paper in papers:
            source = paper.get('text_source', 'unknown')
            text_sources[source] = text_sources.get(source, 0) + 1

        # 提取状态统计
        extraction_statuses = {}
        for paper in papers:
            status = paper.get('extraction_status', 'unknown')
            extraction_statuses[status] = extraction_statuses.get(status, 0) + 1

        # 字段提取统计
        extracted_fields = 0
        field_stats = {}

        for paper in papers:
            if paper.get('extraction_status') == 'success':
                for key, value in paper.items():
                    if (not key.startswith(('PMID', 'Title', 'Authors', 'Year', 'Journal', 'DOI', 'Abstract'))
                            and not key.endswith(('_status', '_error', '_time', '_source', '_length')) and value
                            and value != 'NA' and value != '未提及'):

                        field_stats[key] = field_stats.get(key, 0) + 1
                        extracted_fields += 1

        # 处理时间统计
        processing_times = [p.get('extraction_time', 0) for p in papers if p.get('extraction_time')]

        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0

        # 成功率
        success_rate = analyzed_papers / total_papers if total_papers > 0 else 0

        stats = {
            'total_papers': total_papers,
            'analyzed_papers': analyzed_papers,
            'extracted_fields': extracted_fields,
            'success_rate': round(success_rate * 100, 2),
            'avg_processing_time': round(avg_processing_time, 2),
            'text_sources': text_sources,
            'extraction_statuses': extraction_statuses,
            'field_statistics': field_stats,
            'processing_time': sum(processing_times)
        }

        return stats

    def generate_report(self, papers: List[Dict[str, Any]], template: Dict[str, Any], output_dir: Path) -> bool:
        """
        生成详细的分析报告

        Args:
            papers: 文献列表
            template: 提取模板
            output_dir: 输出目录

        Returns:
            是否生成成功
        """
        try:
            self.logger.info("📋 生成分析报告...")

            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)

            # 生成统计信息
            stats = self.generate_statistics(papers)

            # 创建报告内容
            report = {
                'generation_time': datetime.now().strftime(self.date_format + '%H:%M:%S'),
                'template_info': {
                    'name': template.get('name', 'Unknown'),
                    'description': template.get('description', ''),
                    'version': template.get('version', '1.0'),
                    'fields_count': len(template.get('fields', {}))
                },
                'processing_statistics': stats,
                'field_details': []
            }

            # 字段详细信息
            fields = template.get('fields', {})
            for field_key, field_info in fields.items():
                csv_header = field_info.get('csv_header', field_key)
                field_name = field_info.get('name', field_key)

                # 统计该字段的提取情况
                extracted_count = 0
                sample_values = []

                for paper in papers:
                    if paper.get('extraction_status') == 'success':
                        value = paper.get(field_key, '')
                        if value and value != 'NA' and value != '未提及':
                            extracted_count += 1
                            if len(sample_values) < 3:  # 收集样本值
                                sample_values.append(value[:100])  # 截取前 100 字符

                field_detail = {
                    'field_key':
                    field_key,
                    'field_name':
                    field_name,
                    'csv_header':
                    csv_header,
                    'description':
                    field_info.get('description', ''),
                    'required':
                    field_info.get('required', False),
                    'extracted_count':
                    extracted_count,
                    'extraction_rate':
                    round(extracted_count / stats['analyzed_papers'] * 100, 2) if stats['analyzed_papers'] > 0 else 0,
                    'sample_values':
                    sample_values
                }

                report['field_details'].append(field_detail)

            # 保存报告
            report_file = output_dir / 'analysis_report.json'
            FileHandler.save_json(report, report_file)

            # 生成简化的文本报告
            text_report = self._generate_text_report(report)
            text_report_file = output_dir / 'analysis_report.txt'
            FileHandler.save_text(text_report, text_report_file)

            self.logger.info(f"✅ 分析报告已生成: {report_file}")
            return True

        except Exception as e:
            self.logger.error(f"❌ 生成分析报告失败: {e}")
            return False

    def _generate_text_report(self, report: Dict[str, Any]) -> str:
        """
        生成文本格式的报告

        Args:
            report: 报告数据

        Returns:
            文本报告内容
        """
        lines = []

        # 标题
        lines.append("=" * 60)
        lines.append("PubMiner 文献分析报告")
        lines.append("=" * 60)
        lines.append(f"生成时间: {report['generation_time']}")
        lines.append("")

        # 模板信息
        template_info = report['template_info']
        lines.append("📋 提取模板信息:")
        lines.append(f"名称: {template_info['name']}")
        lines.append(f"描述: {template_info['description']}")
        lines.append(f"版本: {template_info['version']}")
        lines.append(f"字段数量: {template_info['fields_count']}")
        lines.append("")

        # 处理统计
        stats = report['processing_statistics']
        lines.append("📊 处理统计:")
        lines.append(f"总文献数: {stats['total_papers']}")
        lines.append(f"成功分析: {stats['analyzed_papers']}")
        lines.append(f"成功率: {stats['success_rate']}%")
        lines.append(f"提取字段总数: {stats['extracted_fields']}")
        lines.append(f"平均处理时间: {stats['avg_processing_time']} 秒")
        lines.append("")

        # 文本来源统计
        if 'text_sources' in stats:
            lines.append("📄 文本来源分布:")
            for source, count in stats['text_sources'].items():
                lines.append(f"{source}: {count}")
            lines.append("")

        # 提取状态统计
        if 'extraction_statuses' in stats:
            lines.append("🎯 提取状态分布:")
            for status, count in stats['extraction_statuses'].items():
                lines.append(f"{status}: {count}")
            lines.append("")

        # 字段提取详情
        lines.append("🔍 字段提取详情:")
        lines.append("-" * 40)

        for field_detail in report['field_details']:
            lines.append(f"字段: {field_detail['field_name']} ({field_detail['csv_header']})")
            lines.append(f"提取数量: {field_detail['extracted_count']}")
            lines.append(f"提取率: {field_detail['extraction_rate']}%")
            lines.append(f"是否必需: {'是'if field_detail['required'] else'否'}")

            if field_detail['sample_values']:
                lines.append("样本值:")
                for i, sample in enumerate(field_detail['sample_values'], 1):
                    lines.append(f"{i}. {sample}")

            lines.append("")

        lines.append("=" * 60)
        lines.append("报告结束")

        return "\n".join(lines)

    def validate_data_quality(self, papers: List[Dict[str, Any]], template: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证数据质量

        Args:
            papers: 文献列表
            template: 提取模板

        Returns:
            质量验证结果
        """
        validation_result = {
            'total_papers': len(papers),
            'quality_issues': [],
            'field_completeness': {},
            'data_consistency': {},
            'overall_quality_score': 0
        }

        if not papers:
            return validation_result

        fields = template.get('fields', {})

        # 检查必需字段的完整性
        for field_key, field_info in fields.items():
            if field_info.get('required', False):
                field_name = field_info.get('name', field_key)
                missing_count = 0

                for paper in papers:
                    if paper.get('extraction_status') == 'success':
                        value = paper.get(field_key, '')
                        if not value or value in self.na_values:
                            missing_count += 1

                completeness_rate = 1 - (missing_count / len(papers))
                validation_result['field_completeness'][field_name] = {
                    'completeness_rate': round(completeness_rate * 100, 2),
                    'missing_count': missing_count
                }

                if completeness_rate < 0.8:  # 完整率低于 80% 发出警告
                    validation_result['quality_issues'].append(f"必需字段'{field_name}'完整率较低: {completeness_rate*100:.1f}%")

        # 计算整体质量分数
        success_rate = len([p for p in papers if p.get('extraction_status') == 'success']) / len(papers)
        avg_completeness = sum(info['completeness_rate'] for info in validation_result['field_completeness'].values()) / len(
            validation_result['field_completeness']) if validation_result['field_completeness'] else 0

        validation_result['overall_quality_score'] = round((success_rate * 0.5 + avg_completeness / 100 * 0.5) * 100, 2)

        return validation_result

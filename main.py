#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PubMiner - 模块化文献分析工具
主程序入口

功能：
1. 获取PubMed文献基本信息
2. 提取全文内容（PMC/PDF）
3. 基于大模型的结构化信息提取
4. 生成标准化CSV报告
"""

import sys
import argparse
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent))

from core.config_manager import ConfigManager
from core.pubmed_fetcher import PubMedFetcher
from core.text_extractor import TextExtractor
from core.llm_analyzer import LLMAnalyzer
from core.data_processor import DataProcessor
from core.query_manager import QueryManager
from utils.logger import setup_logger


class PubMiner:
    """PubMiner 主类 - 提供编程接口"""

    def __init__(self, config_path=None, llm_provider='deepseek'):
        """
        初始化PubMiner
        
        Args:
            config_path: 配置文件路径
            llm_provider: LLM提供商
        """
        # 如果没有指定配置路径，使用项目根目录的配置
        if config_path is None:
            project_root = Path(__file__).parent
            config_path = project_root / 'config' / 'default_config.json'

        self.config_manager = ConfigManager(str(config_path))
        self.llm_provider = llm_provider
        self.logger = setup_logger(logging.INFO, Path('logs'))

        # 初始化组件
        # 合并pubmed配置和citation_details配置传递给PubMedFetcher
        pubmed_config = self.config_manager.get_pubmed_config()
        output_config = self.config_manager.get_output_config()
        pubmed_config.update(
            {'citation_details': output_config.get('citation_details', {})})

        self.fetcher = PubMedFetcher(pubmed_config)
        self.extractor = TextExtractor(
            self.config_manager.get_extraction_config())
        self.analyzer = LLMAnalyzer(
            self.config_manager.get_llm_config(llm_provider))
        self.processor = DataProcessor(output_config)
        self.query_manager = QueryManager(self.config_manager)

        self.logger.info("✅ PubMiner 初始化完成")

    def analyze_by_query(self,
                         query,
                         template_name='standard',
                         max_results=50,
                         include_fulltext=True,
                         max_workers=4,
                         language=None,
                         custom_template_file=None):
        """
        根据查询词分析文献
        
        Args:
            query: PubMed查询词
            template_name: 提取模板名称
            max_results: 最大结果数
            include_fulltext: 是否包含全文
            max_workers: 并发数
            language: 输出语言 (Chinese, English, etc.)，如果为 None 则使用配置文件默认值
            custom_template_file: 自定义模板文件路径
            
        Returns:
            分析结果列表
        """
        # 如果未指定语言，使用配置文件中的默认语言
        if language is None:
            language = self.config_manager.get_default_language()
        else:
            language = self.config_manager.normalize_language(language)

        self.logger.info(f"🔍 开始查询分析: {query}")
        self.logger.info(f"🌐 输出语言: {language}")

        # 1. 获取文献基本信息
        papers = self.fetcher.fetch_by_query(query, max_results=max_results)
        self.logger.info(f"📚 获取到 {len(papers)} 篇文献")

        if not papers:
            return []

        # 2. 提取全文（如果需要）
        if include_fulltext:
            papers = self.extractor.extract_batch(papers,
                                                  max_workers=max_workers)
            papers = [p for p in papers if p.get('full_text')]
            self.logger.info(f"📄 成功提取 {len(papers)} 篇文献全文")

        # 3. LLM分析
        if custom_template_file:
            # 加载自定义模板文件
            import json
            with open(custom_template_file, 'r', encoding='utf-8') as f:
                template = json.load(f)
        else:
            template = self.config_manager.get_extraction_template(
                template_name)
        analyzed_papers = self.analyzer.analyze_batch(papers,
                                                      template,
                                                      max_workers=max_workers,
                                                      language=language)

        self.logger.info(f"✅ 分析完成，共处理 {len(analyzed_papers)} 篇文献")
        return analyzed_papers

    def analyze_by_pmids(self,
                         pmids,
                         template_name='standard',
                         include_fulltext=True,
                         max_workers=4,
                         language=None):
        """
        根据PMID列表分析文献
        
        Args:
            pmids: PMID列表
            template_name: 提取模板名称
            include_fulltext: 是否包含全文
            max_workers: 并发数
            language: 输出语言（None 时使用配置文件默认值）
            
        Returns:
            分析结果列表
        """
        # 如果未指定语言，使用配置文件中的默认语言
        if language is None:
            language = self.config_manager.get_default_language()

        self.logger.info(f"🔍 开始 PMID 分析: {len(pmids)} 篇文献")
        self.logger.info(f"🌐 输出语言: {language}")

        # 1. 获取文献基本信息
        papers = self.fetcher.fetch_by_pmid_list(pmids)
        self.logger.info(f"📚 获取到 {len(papers)} 篇文献")

        if not papers:
            return []

        # 2. 提取全文（如果需要）
        if include_fulltext:
            papers = self.extractor.extract_batch(papers,
                                                  max_workers=max_workers)
            papers = [p for p in papers if p.get('full_text')]
            self.logger.info(f"📄 成功提取 {len(papers)} 篇文献全文")

        # 3. LLM 分析
        template = self.config_manager.get_extraction_template(template_name)
        analyzed_papers = self.analyzer.analyze_batch(papers,
                                                      template,
                                                      max_workers=max_workers,
                                                      language=language)

        self.logger.info(f"✅ 分析完成，共处理 {len(analyzed_papers)} 篇文献")
        return analyzed_papers

    def save_results(self, results, output_name='analysis_results'):
        """
        保存分析结果
        
        Args:
            results: 分析结果列表
            output_name: 输出文件名前缀
        """
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = Path('results') / f'{output_name}_{timestamp}.csv'

        # 使用标准模板（这里需要改进以支持动态模板）
        template = self.config_manager.get_extraction_template('standard')
        self.processor.generate_csv(results, template, output_path)

        self.logger.info(f"💾 结果已保存到: {output_path}")
        return output_path

    def get_available_templates(self):
        """获取可用的提取模板列表"""
        templates = self.config_manager.get_extraction_templates()
        return list(templates.keys())

    def create_custom_template(self,
                               fields,
                               template_name,
                               template_description="Custom template"):
        """
        创建自定义模板
        
        Args:
            fields: 字段定义列表
            template_name: 模板名称
            template_description: 模板描述
        """
        from extractors.custom_extractor import CustomExtractor
        extractor = CustomExtractor(self.config_manager.get_config())
        template = extractor.create_template_from_fields(
            fields, template_description)

        # 这里可以添加保存模板的逻辑
        return template

    def execute_batch_queries(self, config_file):
        """
        执行批量查询任务
        
        Args:
            config_file: 查询配置文件路径
            
        Returns:
            执行结果列表
        """
        return self.query_manager.execute_batch_queries(config_file, self)

    def create_query_config_example(self,
                                    output_file="query_config_example.json"):
        """
        创建查询配置示例文件
        
        Args:
            output_file: 输出文件路径
        """
        self.query_manager.create_example_config(output_file)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='PubMiner - 模块化文献分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 按查询词分析文献
  python main.py --query "covid-19 AND vaccine" --output results.csv
  
  # 按PMID列表分析
  python main.py --pmids 12345678,87654321 --output results.csv
  
  # 使用自定义提取模板
  python main.py --query "aging biomarker" --template aging_biomarker --output aging_results.csv
  
  # 指定大模型配置
  python main.py --query "cancer treatment" --llm-provider deepseek --output cancer_results.csv
        """)

    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--query', type=str, help='PubMed 查询词')
    input_group.add_argument('--pmids', type=str, help='PMID 列表，逗号分隔')
    input_group.add_argument('--pmid-file', type=str, help='包含 PMID 列表的文件路径')
    input_group.add_argument('--batch-config', type=str, help='批量查询配置文件路径')
    input_group.add_argument('--create-query-example',
                             action='store_true',
                             help='创建查询配置示例文件')

    # 输出参数
    parser.add_argument('--output', type=str, help='输出 CSV 文件路径（单个查询时必需）')
    parser.add_argument('--output-dir',
                        type=str,
                        default='output',
                        help='输出目录（默认：output）')

    # 处理参数
    parser.add_argument('--template',
                        type=str,
                        default='standard',
                        help='提取模板（standard/custom 等，默认：standard）')
    parser.add_argument('--custom-fields', type=str, help='自定义字段 JSON 文件路径')

    # LLM参数
    parser.add_argument('--llm-provider',
                        type=str,
                        default='deepseek',
                        choices=['openai', 'deepseek', 'qwen', 'volcengine'],
                        help='大模型提供商（默认：deepseek）')
    parser.add_argument('--llm-model', type=str, help='具体模型名称（覆盖默认配置）')
    parser.add_argument('--api-key', type=str, help='API 密钥（覆盖配置文件）')

    # 优化参数
    parser.add_argument('--max-workers',
                        type=int,
                        default=4,
                        help='最大并发数（默认：4）')
    parser.add_argument('--batch-size',
                        type=int,
                        default=10,
                        help='批处理大小（默认：10）')
    parser.add_argument('--text-limit',
                        type=int,
                        default=15000,
                        help='单篇文献文本长度限制（默认：15000 字符）')

    # 其他参数
    parser.add_argument('--config',
                        type=str,
                        default='config/default_config.json',
                        help='配置文件路径（默认：config/default_config.json）')
    parser.add_argument('--resume', action='store_true', help='断点续传模式')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='试运行模式（不实际调用 API）')

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_arguments()

    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger(log_level, Path('logs'))

    try:
        # 处理创建查询配置示例的情况
        if args.create_query_example:
            from core.query_manager import QueryManager
            config_manager = ConfigManager(args.config)
            query_manager = QueryManager(config_manager)
            output_file = args.output if args.output else "query_config_example.json"
            query_manager.create_example_config(output_file)
            return

        # 验证输出文件参数
        if not args.batch_config and not args.output:
            logger.error("❌ 错误: 单个查询模式需要指定 --output 参数")
            sys.exit(1)

        # 处理批量查询配置的情况
        if args.batch_config:
            logger.info("🚀 启动 PubMiner 批量查询模式")
            logger.info(f"配置文件: {args.batch_config}")

            # 初始化PubMiner
            pubminer = PubMiner(args.config, args.llm_provider)

            # 执行批量查询
            results = pubminer.execute_batch_queries(args.batch_config)

            logger.info("🎉 批量查询执行完成！")
            return

        logger.info("🚀 启动 PubMiner 文献分析工具")
        logger.info(f"输出目录: {args.output_dir}")
        logger.info(f"输出文件: {args.output}")

        # 1. 加载配置
        logger.info("📋 加载配置文件...")
        config_manager = ConfigManager(args.config)

        # 覆盖配置参数
        if args.api_key:
            config_manager.set_api_key(args.llm_provider, args.api_key)
        if args.llm_model:
            config_manager.set_model(args.llm_provider, args.llm_model)

        # 2. 获取文献基本信息
        logger.info("📚 获取文献基本信息...")
        fetcher = PubMedFetcher(config_manager.get_pubmed_config())

        if args.query:
            papers = fetcher.fetch_by_query(args.query, resume=args.resume)
        elif args.pmids:
            pmid_list = [pmid.strip() for pmid in args.pmids.split(',')]
            papers = fetcher.fetch_by_pmid_list(pmid_list, resume=args.resume)
        elif args.pmid_file:
            with open(args.pmid_file, 'r', encoding='utf-8') as f:
                pmid_list = [line.strip() for line in f if line.strip()]
            papers = fetcher.fetch_by_pmid_list(pmid_list, resume=args.resume)

        logger.info(f"✅ 获取到 {len(papers)} 篇文献的基本信息")

        if not papers:
            logger.warning("⚠️ 未获取到任何文献，程序退出")
            return

        # 3. 提取全文内容
        logger.info("📄 提取文献全文内容...")
        extractor = TextExtractor(config_manager.get_extraction_config())
        papers_with_text = extractor.extract_batch(
            papers, max_workers=args.max_workers, text_limit=args.text_limit)

        valid_papers = [p for p in papers_with_text if p.get('full_text')]
        logger.info(f"✅ 成功提取 {len(valid_papers)} 篇文献的全文内容")

        if not valid_papers:
            logger.warning("⚠️ 未能提取到任何文献的全文内容，程序退出")
            return

        # 4. 加载提取模板
        logger.info(f"🎯 加载提取模板: {args.template}")
        if args.custom_fields:
            template = config_manager.load_custom_template(args.custom_fields)
        else:
            template = config_manager.get_extraction_template(args.template)

        # 5. LLM分析
        if not args.dry_run:
            logger.info("🧠 开始大模型分析...")
            analyzer = LLMAnalyzer(
                config_manager.get_llm_config(args.llm_provider))

            analyzed_papers = analyzer.analyze_batch(
                valid_papers,
                template,
                batch_size=args.batch_size,
                max_workers=args.max_workers)
        else:
            logger.info("🔍 试运行模式，跳过 LLM 分析")
            analyzed_papers = valid_papers

        # 6. 数据处理和输出
        logger.info("📊 处理数据并生成输出...")
        processor = DataProcessor(config_manager.get_output_config())

        output_path = Path(args.output_dir) / args.output
        processor.generate_csv(analyzed_papers, template, output_path)

        logger.info(f"🎉 分析完成！结果已保存到: {output_path}")

        # 7. 生成统计报告
        stats = processor.generate_statistics(analyzed_papers)
        logger.info("📈 处理统计:")
        logger.info(f"  - 总文献数: {stats['total_papers']}")
        logger.info(f"  - 成功分析: {stats['analyzed_papers']}")
        logger.info(f"  - 提取字段: {stats['extracted_fields']}")
        logger.info(f"  - 处理时间: {stats['processing_time']:.2f}秒")

    except KeyboardInterrupt:
        logger.info("⛔ 用户中断操作")
    except Exception as e:
        logger.error(f"💥 程序执行出错: {str(e)}")
        if args.verbose:
            import traceback
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PubMiner 基础使用示例

展示如何使用 PubMiner 进行基本的文献分析任务
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from main import PubMiner
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def example_query_analysis():
    """示例1: 按查询搜索分析"""
    print("=" * 60)
    print("示例1: 按查询搜索分析")
    print("=" * 60)
    
    # 初始化 PubMiner
    miner = PubMiner()
    
    # 设置查询参数
    query = "aging biomarkers AND humans"
    max_results = 20
    
    print(f"查询: {query}")
    print(f"最大结果数: {max_results}")
    print()
    
    try:
        # 执行分析
        results = miner.analyze_by_query(
            query=query,
            max_results=max_results,
            template_name="aging_biomarker",
            llm_provider="deepseek"
        )
        
        print(f"✅ 分析完成，共处理 {len(results)} 篇文献")
        
        # 保存结果
        output_file = project_root / "output" / "query_analysis_results.csv"
        success = miner.save_results(results, output_file)
        
        if success:
            print(f"✅ 结果已保存到: {output_file}")
        
        # 显示统计信息
        stats = miner.get_statistics()
        print("\n📊 处理统计:")
        print(f"  成功分析: {stats['successful_extractions']}")
        print(f"  失败数量: {stats['failed_extractions']}")
        print(f"  成功率: {stats['success_rate']:.1f}%")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")

def example_pmid_analysis():
    """示例2: 按PMID列表分析"""
    print("=" * 60)
    print("示例2: 按PMID列表分析")
    print("=" * 60)
    
    # 初始化 PubMiner
    miner = PubMiner()
    
    # PMID列表（示例）
    pmid_list = [
        "35123456",  # 请替换为真实的PMID
        "35234567",
        "35345678"
    ]
    
    print(f"PMID列表: {pmid_list}")
    print()
    
    try:
        # 执行分析
        results = miner.analyze_by_pmids(
            pmids=pmid_list,
            template_name="standard",
            llm_provider="deepseek"
        )
        
        print(f"✅ 分析完成，共处理 {len(results)} 篇文献")
        
        # 保存结果
        output_file = project_root / "output" / "pmid_analysis_results.csv"
        success = miner.save_results(results, output_file)
        
        if success:
            print(f"✅ 结果已保存到: {output_file}")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")

def example_custom_template():
    """示例3: 使用自定义模板"""
    print("=" * 60)
    print("示例3: 使用自定义模板")
    print("=" * 60)
    
    from extractors import CustomExtractor
    from core.config_manager import ConfigManager
    
    # 初始化配置管理器
    config_manager = ConfigManager()
    config = config_manager.get_config()
    
    # 创建自定义提取器
    extractor = CustomExtractor(config)
    
    # 定义自定义字段
    field_definitions = [
        {
            "key": "drug_name",
            "name": "药物名称",
            "description": "研究中使用的药物名称",
            "csv_header": "Drug_Name",
            "prompt_hint": "文章中提到的具体药物、化合物或治疗药物名称",
            "required": True
        },
        {
            "key": "dosage",
            "name": "药物剂量",
            "description": "药物的使用剂量",
            "csv_header": "Dosage",
            "prompt_hint": "药物的具体剂量、用量或浓度",
            "required": False
        },
        {
            "key": "side_effects",
            "name": "副作用",
            "description": "观察到的副作用或不良反应",
            "csv_header": "Side_Effects",
            "prompt_hint": "研究中报告的副作用、不良反应或安全性问题",
            "required": False
        },
        {
            "key": "efficacy",
            "name": "疗效评估",
            "description": "药物疗效的评估结果",
            "csv_header": "Efficacy",
            "prompt_hint": "治疗效果、疗效评估结果或临床终点",
            "required": True
        }
    ]
    
    # 创建自定义模板
    template = extractor.create_template_from_fields(
        field_definitions,
        template_name="药物研究专用模板",
        template_description="专门用于提取药物研究相关信息的自定义模板"
    )
    
    print("✅ 自定义模板创建成功")
    print(f"模板名称: {template['name']}")
    print(f"字段数量: {len(template['fields'])}")
    
    # 保存模板
    template_file = project_root / "config" / "drug_research_template.json"
    success = extractor.save_template(template_file)
    
    if success:
        print(f"✅ 模板已保存到: {template_file}")
    
    # 使用自定义模板进行分析（示例）
    # results = miner.analyze_by_query(
    #     query="drug treatment clinical trial",
    #     max_results=10,
    #     custom_template_path=str(template_file)
    # )

def example_text_optimization():
    """示例4: 文本优化功能"""
    print("=" * 60)
    print("示例4: 文本优化功能")
    print("=" * 60)
    
    from optimizers import TextPreprocessor
    from core.config_manager import ConfigManager
    
    # 初始化
    config_manager = ConfigManager()
    config = config_manager.get_config()
    
    preprocessor = TextPreprocessor(config['optimization'])
    
    # 示例文本（通常会更长）
    sample_text = """
    Abstract: This study investigates the role of aging biomarkers in human health.
    
    Introduction: Aging is a complex biological process characterized by the gradual 
    decline of physiological functions. Recent advances in biotechnology have enabled 
    the identification of various biomarkers that can indicate the aging process.
    
    Methods: We conducted a systematic review of literature published between 2020 and 2024.
    A total of 150 studies were included in the analysis. We used statistical methods 
    to analyze the correlation between different biomarkers and aging.
    
    Results: Our analysis revealed that protein-based biomarkers showed the highest 
    correlation with chronological age (r=0.85, p<0.001). DNA methylation patterns 
    also demonstrated significant associations with aging (r=0.78, p<0.001).
    
    Discussion: These findings suggest that combining multiple biomarker types may 
    provide more accurate assessments of biological age compared to chronological age alone.
    
    Conclusion: Multi-biomarker approaches represent a promising direction for aging research.
    """
    
    print(f"原始文本长度: {len(sample_text)} 字符")
    
    # 文本清理
    cleaned_text = preprocessor.clean_text(sample_text)
    print(f"清理后长度: {len(cleaned_text)} 字符")
    
    # 章节识别
    sections = preprocessor.extract_sections(sample_text)
    print(f"识别到 {len(sections)} 个章节: {list(sections.keys())}")
    
    # LLM优化
    optimized_text = preprocessor.optimize_for_llm(sample_text, max_tokens=1000)
    print(f"LLM优化后长度: {len(optimized_text)} 字符")
    
    print("\n优化后的文本预览:")
    print("-" * 40)
    print(optimized_text[:300] + "..." if len(optimized_text) > 300 else optimized_text)

def example_batch_processing():
    """示例5: 批量处理"""
    print("=" * 60)
    print("示例5: 批量处理")
    print("=" * 60)
    
    # 初始化 PubMiner
    miner = PubMiner()
    
    # 多个查询的批量处理
    queries = [
        "aging biomarkers",
        "senescence markers", 
        "longevity genes"
    ]
    
    all_results = []
    
    for i, query in enumerate(queries, 1):
        print(f"处理查询 {i}/{len(queries)}: {query}")
        
        try:
            results = miner.analyze_by_query(
                query=query,
                max_results=10,
                template_name="aging_biomarker",
                llm_provider="deepseek"
            )
            
            # 添加查询来源标记
            for result in results:
                result['query_source'] = query
            
            all_results.extend(results)
            print(f"  ✅ 完成，获得 {len(results)} 篇文献")
            
        except Exception as e:
            print(f"  ❌ 失败: {e}")
    
    print(f"\n📊 批量处理完成，总计 {len(all_results)} 篇文献")
    
    # 保存合并结果
    if all_results:
        output_file = project_root / "output" / "batch_analysis_results.csv"
        success = miner.save_results(all_results, output_file)
        
        if success:
            print(f"✅ 合并结果已保存到: {output_file}")

def main():
    """主函数"""
    print("🔬 PubMiner 使用示例")
    print("=" * 60)
    
    # 确保输出目录存在
    output_dir = project_root / "results"
    output_dir.mkdir(exist_ok=True)
    
    # 运行示例
    examples = [
        ("基础查询分析", example_query_analysis),
        ("PMID列表分析", example_pmid_analysis), 
        ("自定义模板", example_custom_template),
        ("文本优化", example_text_optimization),
        ("批量处理", example_batch_processing)
    ]
    
    print("可用示例:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    print("\n选择要运行的示例 (1-5, 或 'all' 运行所有示例):")
    choice = input("请输入选择: ").strip().lower()
    
    if choice == 'all':
        for name, func in examples:
            print(f"\n运行示例: {name}")
            try:
                func()
            except KeyboardInterrupt:
                print("用户中断")
                break
            except Exception as e:
                print(f"示例执行失败: {e}")
    else:
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(examples):
                name, func = examples[choice_num - 1]
                print(f"\n运行示例: {name}")
                func()
            else:
                print("无效选择")
        except ValueError:
            print("无效输入")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Query Manager - 查询配置管理器
支持从配置文件加载复杂查询任务，类似PubEx的功能
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from tqdm import tqdm

from .config_manager import ConfigManager
from utils.logger import setup_logger


class QueryManager:
    """查询配置管理器"""
    
    def __init__(self, config_manager: ConfigManager):
        """初始化查询管理器"""
        self.config_manager = config_manager
        self.logger = setup_logger()
        
    def load_query_config(self, config_file: str) -> Dict[str, Any]:
        """
        加载查询配置文件
        
        Args:
            config_file: 配置文件路径
            
        Returns:
            Dict: 查询配置字典
            
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Query config file not found: {config_file}")
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in config file: {e}")
            
        # 验证配置文件结构
        self._validate_config(config)
        
        return config
        
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        验证配置文件格式
        
        Args:
            config: 配置字典
            
        Raises:
            ValueError: 配置格式错误
        """
        if 'query_tasks' not in config:
            raise ValueError("Missing 'query_tasks' in config file")
            
        if not isinstance(config['query_tasks'], list):
            raise ValueError("'query_tasks' must be a list")
            
        if not config['query_tasks']:
            raise ValueError("'query_tasks' cannot be empty")
            
        # 验证每个任务的必需字段
        required_fields = ['name', 'query']
        for i, task in enumerate(config['query_tasks']):
            for field in required_fields:
                if field not in task:
                    raise ValueError(f"Task {i+1} missing required field: {field}")
                    
    def create_example_config(self, output_file: str = "query_config_example.json") -> None:
        """
        创建示例查询配置文件
        
        Args:
            output_file: 输出文件路径
        """
        example_config = {
            "_comment": "PubMiner 批量查询配置文件示例",
            "_max_results_options": {
                "说明": "max_results 设置选项",
                "获取所有结果": "设为 null 或 -1",
                "限制数量": "设为具体数字，如 100, 500 等"
            },
            "query_tasks": [
                {
                    "name": "COVID-19 and Diabetes Research (Limited)",
                    "query": "(COVID-19[ti] OR SARS-CoV-2[ti]) AND (diabetes[ti] OR diabetic[ti]) AND (\"2020/01/01\"[Date - Publication] : \"2024/12/31\"[Date - Publication])",
                    "max_results": 50,
                    "include_fulltext": False,
                    "output_file": "covid_diabetes_limited.csv",
                    "description": "Research on COVID-19 and diabetes relationship (limited to 50 papers)"
                },
                {
                    "name": "Aging Biomarkers Study (All Results)",
                    "query": "(aging[ti] OR senescence[ti]) AND (biomarker[ti] OR marker[ti]) AND (\"2023/01/01\"[Date - Publication] : \"2024/12/31\"[Date - Publication])",
                    "max_results": None,
                    "include_fulltext": True,
                    "output_file": "aging_biomarkers_all.csv",
                    "description": "Aging-related biomarker research (获取所有结果)",
                    "custom_fields": [
                        "What biomarkers are studied in this article",
                        "Single biomarker or combination of biomarkers",
                        "Biomarker category (Protein/DNA/RNA/Other)",
                        "Study population ethnicity",
                        "Gender ratio of study samples"
                    ]
                },
                {
                    "name": "Cancer Immunotherapy (Unlimited)",
                    "query": "cancer[ti] AND immunotherapy[ti] AND (\"2024/01/01\"[Date - Publication] : \"2024/12/31\"[Date - Publication])",
                    "max_results": -1,
                    "include_fulltext": False,
                    "output_file": "cancer_immunotherapy_unlimited.csv",
                    "description": "Cancer immunotherapy research (使用 -1 获取所有结果)"
                }
            ],
            "default_settings": {
                "max_results": None,
                "include_fulltext": False,
                "output_dir": "results/batch_queries",
                "task_wait_time": 5,
                "retry_failed_tasks": True
            }
        }
        
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(example_config, f, indent=4, ensure_ascii=False)
            
        self.logger.info(f"✅ Example query config created: {output_file}")
        print(f"✅ Example query config created: {output_file}")
        print("📝 Please modify the config file according to your needs")
        
    def execute_batch_queries(self, config_file: str, pubminer) -> List[Dict[str, Any]]:
        """
        执行批量查询任务
        
        Args:
            config_file: 查询配置文件路径
            pubminer: PubMiner实例
            
        Returns:
            List[Dict]: 执行结果列表
        """
        # 加载配置
        config = self.load_query_config(config_file)
        query_tasks = config['query_tasks']
        default_settings = config.get('default_settings', {})
        
        # 创建输出目录
        output_dir = default_settings.get('output_dir', 'results/batch_queries')
        os.makedirs(output_dir, exist_ok=True)
        
        # 执行结果
        execution_results = []
        
        # 创建总体进度条
        task_progress = tqdm(total=len(query_tasks), desc="🎯 Batch Query Progress", unit="task")
        
        self.logger.info(f"🚀 Starting batch query execution with {len(query_tasks)} tasks")
        print(f"🚀 Starting batch query execution with {len(query_tasks)} tasks")
        print(f"📁 Output directory: {output_dir}")
        print("=" * 80)
        
        for i, task in enumerate(query_tasks, 1):
            task_name = task.get('name', f'Task {i}')
            query = task['query']
            
            # 任务参数，使用默认值填充
            max_results = task.get('max_results', default_settings.get('max_results', 100))
            
            # 处理无限制获取的情况
            if max_results is None or max_results == -1:
                max_results = None  # None 表示获取所有结果
                max_results_display = "所有结果"
            else:
                max_results_display = str(max_results)
            include_fulltext = task.get('include_fulltext', default_settings.get('include_fulltext', False))
            output_file = task.get('output_file', f'query_task_{i}.csv')
            custom_fields = task.get('custom_fields', [])
            description = task.get('description', '')
            
            # 确保输出文件在正确的目录下
            if not os.path.isabs(output_file):
                output_file = os.path.join(output_dir, output_file)
                
            print(f"\n🎯 Task {i}/{len(query_tasks)}: {task_name}")
            print(f"📝 Description: {description}")
            print(f"🔍 Query: {query}")
            print(f"📊 Max results: {max_results_display}")
            print(f"📄 Include fulltext: {include_fulltext}")
            print(f"📁 Output file: {output_file}")
            if custom_fields:
                print(f"🔧 Custom fields: {len(custom_fields)} fields")
            print("-" * 60)
            
            # 记录任务开始时间
            start_time = time.time()
            
            try:
                # 设置提取模板
                if custom_fields:
                    # 创建临时自定义模板
                    custom_template = {
                        "template_name": f"custom_task_{i}",
                        "description": f"Custom template for task: {task_name}",
                        "fields": {}
                    }
                    
                    for j, field in enumerate(custom_fields, 1):
                        field_key = f"custom_field_{j}"
                        custom_template["fields"][field_key] = {
                            "description": field,
                            "type": "string",
                            "required": False
                        }
                    
                    # 临时保存自定义模板
                    temp_template_file = f"temp_template_task_{i}.json"
                    with open(temp_template_file, 'w', encoding='utf-8') as f:
                        json.dump(custom_template, f, indent=2, ensure_ascii=False)
                    
                    # 执行带自定义字段的分析
                    language = task.get('language', default_settings.get('language'))
                    results = pubminer.analyze_by_query(
                        query=query,
                        max_results=max_results,
                        include_fulltext=include_fulltext,
                        custom_template_file=temp_template_file,
                        language=language
                    )
                    
                    # 清理临时文件
                    if os.path.exists(temp_template_file):
                        os.remove(temp_template_file)
                else:
                    # 执行标准分析
                    language = task.get('language', default_settings.get('language'))
                    results = pubminer.analyze_by_query(
                        query=query,
                        max_results=max_results,
                        include_fulltext=include_fulltext,
                        language=language
                    )
                
                # 保存结果
                if results:
                    pubminer.save_results(results, output_file)
                    
                # 记录执行结果
                execution_time = time.time() - start_time
                result_info = {
                    'task_id': i,
                    'task_name': task_name,
                    'query': query,
                    'status': 'success',
                    'results_count': len(results) if results else 0,
                    'execution_time': execution_time,
                    'output_file': output_file,
                    'error': None
                }
                
                print(f"✅ Task completed: {len(results) if results else 0} papers retrieved")
                print(f"⏱️ Execution time: {execution_time:.2f}s")
                
            except Exception as e:
                # 记录错误
                execution_time = time.time() - start_time
                result_info = {
                    'task_id': i,
                    'task_name': task_name,
                    'query': query,
                    'status': 'failed',
                    'results_count': 0,
                    'execution_time': execution_time,
                    'output_file': output_file,
                    'error': str(e)
                }
                
                self.logger.error(f"❌ Task {i} failed: {e}")
                print(f"❌ Task failed: {e}")
                
                # 根据配置决定是否重试
                if default_settings.get('retry_failed_tasks', False):
                    print("🔄 Retrying failed task...")
                    # 这里可以添加重试逻辑
                
            execution_results.append(result_info)
            task_progress.update(1)
            
            # 任务间等待
            if i < len(query_tasks):
                wait_time = default_settings.get('task_wait_time', 5)
                if wait_time > 0:
                    print(f"\n⏸️ Task completed, waiting {wait_time}s before next task...")
                    time.sleep(wait_time)
        
        task_progress.close()
        
        # 生成执行报告
        self._generate_execution_report(execution_results, output_dir)
        
        print(f"\n🎉 All {len(query_tasks)} query tasks completed!")
        print(f"📊 Results saved in: {output_dir}")
        
        return execution_results
        
    def _generate_execution_report(self, results: List[Dict[str, Any]], output_dir: str) -> None:
        """
        生成执行报告
        
        Args:
            results: 执行结果列表
            output_dir: 输出目录
        """
        report_file = os.path.join(output_dir, 'execution_report.json')
        
        # 统计信息
        total_tasks = len(results)
        successful_tasks = len([r for r in results if r['status'] == 'success'])
        failed_tasks = total_tasks - successful_tasks
        total_papers = sum(r['results_count'] for r in results)
        total_time = sum(r['execution_time'] for r in results)
        
        report = {
            'execution_summary': {
                'total_tasks': total_tasks,
                'successful_tasks': successful_tasks,
                'failed_tasks': failed_tasks,
                'success_rate': f"{successful_tasks/total_tasks*100:.1f}%" if total_tasks > 0 else "0%",
                'total_papers_retrieved': total_papers,
                'total_execution_time': f"{total_time:.2f}s",
                'average_time_per_task': f"{total_time/total_tasks:.2f}s" if total_tasks > 0 else "0s"
            },
            'task_details': results,
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"📋 Execution report saved: {report_file}")
        print(f"📋 Execution report saved: {report_file}")
        print(f"📊 Summary: {successful_tasks}/{total_tasks} tasks successful, {total_papers} papers total")
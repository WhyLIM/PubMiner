# -*- coding: utf-8 -*-
"""
大语言模型分析模块

负责调用各种 LLM API 进行文献内容分析和结构化信息提取
支持多厂商 API，包含智能提示工程和结果验证
"""

import json
import time
import asyncio
from typing import Dict, List, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
from datetime import datetime

from utils.logger import LoggerMixin
from utils.api_manager import api_manager

logger = logging.getLogger(__name__)

class LLMAnalyzer(LoggerMixin):
    """大语言模型分析器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化LLM分析器
        
        Args:
            config: LLM 配置
        """
        self.config = config
        self.api_base = config.get('api_base', '')
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', '')
        self.temperature = config.get('temperature', 0.1)
        self.max_tokens = config.get('max_tokens', 4000)
        self.timeout = config.get('timeout', 60)
        
        # 根据 API base 判断提供商
        self.provider = self._detect_provider()
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_tokens_used': 0,
            'start_time': datetime.now()
        }
        
        self.logger.info(f"初始化 LLM 分析器: {self.provider} - {self.model}")
    
    def _detect_provider(self) -> str:
        """根据 API base 检测提供商"""
        api_base_lower = self.api_base.lower()
        
        if 'openai.com' in api_base_lower:
            return 'openai'
        elif 'deepseek.com' in api_base_lower:
            return 'deepseek'
        elif 'dashscope.aliyuncs.com' in api_base_lower:
            return 'qwen'
        elif 'volces.com' in api_base_lower:
            return 'volcengine'
        else:
            return 'unknown'
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'PubMiner/1.0'
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        return headers
    
    def _build_system_prompt(self, template: Dict[str, Any], language: str = "English") -> str:
        """
        构建系统提示词
        
        Args:
            template: 提取模板
            language: 输出语言 (Chinese, English, etc.)
            
        Returns:
            系统提示词
        """
        template_name = template.get('name', '信息提取')
        template_desc = template.get('description', '')
        
        system_prompt = f"""You are a professional medical literature analysis assistant, specializing in extracting structured information from academic papers.

Task: {template_name}
Description: {template_desc}

Important requirements:
1. Output results strictly in JSON format
2. Only extract information explicitly mentioned in the paper; do not fabricate any content
3. If a certain field is not mentioned in the paper, fill in "Not Mentioned"
4. Maintain the accuracy and objectivity of the extracted information
5. For numerical information, maintain the precise expression of the original text

Output format requirements:
- Use standard JSON format
- Field names use English
- Content use {language}
- Ensure the JSON format is correct and can be parsed by programs"""

        return system_prompt
    
    def _build_user_prompt(self, text: str, template: Dict[str, Any]) -> str:
        """
        构建用户提示词
        
        Args:
            text: 文献文本
            template: 提取模板
            
        Returns:
            用户提示词
        """
        fields = template.get('fields', {})
        
        # 构建字段说明
        field_descriptions = []
        json_example = {}
        
        for field_key, field_info in fields.items():
            field_name = field_info.get('name', field_key)
            field_desc = field_info.get('description', '')
            prompt_hint = field_info.get('prompt_hint', '')
            
            description = f"- {field_key}: {field_name}"
            if field_desc:
                description += f" - {field_desc}"
            if prompt_hint:
                description += f" (提取提示: {prompt_hint})"
            
            field_descriptions.append(description)
            json_example[field_key] = "请从论文中提取相关信息"
        
        user_prompt = f"""请从以下学术论文中提取指定的结构化信息：

需要提取的字段：
{chr(10).join(field_descriptions)}

输出JSON格式示例：
```json
{json.dumps(json_example, ensure_ascii=False, indent=2)}
```

论文全文：
{text}

请严格按照上述JSON格式输出提取结果："""

        return user_prompt
    
    def _clean_json_response(self, response_text: str) -> str:
        """
        清理LLM响应，提取JSON部分
        
        Args:
            response_text: 原始响应文本
            
        Returns:
            清理后的JSON字符串
        """
        # 移除markdown代码块标记
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        
        # 查找JSON对象
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json_match.group(0).strip()
        
        return response_text.strip()
    
    def _validate_extraction_result(self, result: Dict[str, Any], 
                                  template: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证提取结果的有效性
        
        Args:
            result: 提取结果
            template: 提取模板
            
        Returns:
            验证后的结果
        """
        fields = template.get('fields', {})
        validated_result = {}
        
        for field_key, field_info in fields.items():
            field_name = field_info.get('name', field_key)
            is_required = field_info.get('required', False)
            
            value = result.get(field_key, '')
            
            # 处理空值
            if not value or value in ['', 'N/A', 'NA', 'null', 'None']:
                if is_required:
                    self.logger.warning(f"必需字段 '{field_name}' 未提取到有效值")
                value = '未提及'
            
            # 长度限制
            if isinstance(value, str) and len(value) > 1000:
                value = value[:997] + '...'
                self.logger.debug(f"字段 '{field_name}' 内容过长，已截断")
            
            validated_result[field_key] = value
        
        return validated_result
    
    @api_manager.with_retry(max_retries=3, retry_delay=2.0)
    def _call_llm_api(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        调用LLM API
        
        Args:
            messages: 消息列表
            
        Returns:
            API响应结果
        """
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }
        
        headers = self._build_headers()
        
        # 应用API限流
        api_name = self.provider
        if api_name in api_manager.rate_limiters:
            api_manager.rate_limiters[api_name].wait_if_needed()
        
        response = api_manager.post(
            url=f"{self.api_base}/chat/completions",
            headers=headers,
            json_data=payload,
            timeout=self.timeout,
            api_name=api_name
        )
        
        return response.json()
    
    def analyze_single_paper(self, paper: Dict[str, Any], 
                           template: Dict[str, Any],
                           language: str = "English") -> Dict[str, Any]:
        """
        分析单篇文献
        
        Args:
            paper: 文献记录
            template: 提取模板
            language: 输出语言 (Chinese, English, etc.)
            
        Returns:
            包含提取信息的文献记录
        """
        pmid = paper.get('PMID', 'Unknown')
        title = paper.get('Title', 'Unknown')[:50]
        full_text = paper.get('full_text', '')
        
        self.logger.debug(f"🧠 分析文献: {pmid} - {title}...")
        
        # 如果没有全文，尝试使用摘要进行分析
        if not full_text:
            abstract = paper.get('Abstract', paper.get('abstract', '')).strip()
            if not abstract:
                self.logger.warning(f"⚠️ 文献 {pmid} 既没有全文也没有摘要，跳过分析")
                result = paper.copy()
                result['extraction_status'] = 'no_content'
                return result
            else:
                self.logger.info(f"📝 文献 {pmid} 使用摘要进行分析")
                full_text = "Title: " + title + "Abstract: " + abstract
        
        try:
            # 构建提示词
            system_prompt = self._build_system_prompt(template, language)
            user_prompt = self._build_user_prompt(full_text, template)
            
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ]
            
            # 调用API
            self.stats['total_requests'] += 1
            start_time = time.time()
            
            api_response = self._call_llm_api(messages)
            
            # 处理响应
            if 'choices' in api_response and len(api_response['choices']) > 0:
                response_content = api_response['choices'][0]['message']['content']
                
                # 清理并解析JSON
                json_content = self._clean_json_response(response_content)
                extraction_result = json.loads(json_content)
                
                # 验证结果
                validated_result = self._validate_extraction_result(extraction_result, template)
                
                # 更新统计
                self.stats['successful_requests'] += 1
                if 'usage' in api_response:
                    self.stats['total_tokens_used'] += api_response['usage'].get('total_tokens', 0)
                
                # 合并结果
                result = paper.copy()
                result.update(validated_result)
                result['extraction_status'] = 'success'
                result['extraction_time'] = time.time() - start_time
                
                self.logger.debug(f"✅ 分析完成: {pmid}")
                return result
                
            else:
                raise ValueError(f"API响应格式异常: {api_response}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON解析失败 {pmid}: {e}")
            self.stats['failed_requests'] += 1
            result = paper.copy()
            result['extraction_status'] = 'json_error'
            result['extraction_error'] = str(e)
            return result
            
        except Exception as e:
            self.logger.error(f"❌ 分析文献 {pmid} 失败: {e}")
            self.stats['failed_requests'] += 1
            result = paper.copy()
            result['extraction_status'] = 'api_error'
            result['extraction_error'] = str(e)
            return result
    
    def analyze_batch(self, papers: List[Dict[str, Any]], 
                     template: Dict[str, Any],
                     batch_size: int = 10,
                     max_workers: int = 4,
                     language: str = "English") -> List[Dict[str, Any]]:
        """
        批量分析文献
        
        Args:
            papers: 文献列表
            template: 提取模板
            batch_size: 批处理大小
            max_workers: 最大并发数
            language: 输出语言 (Chinese, English, etc.)
            
        Returns:
            包含提取信息的文献列表
        """
        self.logger.info(f"🧠 开始批量分析，共 {len(papers)} 篇文献")
        self.logger.info(f"使用模板: {template.get('name', 'Unknown')}")
        self.logger.info(f"批处理大小: {batch_size}, 并发数: {max_workers}")
        
        results = []
        
        # 分批处理
        for i in range(0, len(papers), batch_size):
            batch_papers = papers[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(papers) + batch_size - 1) // batch_size
            
            self.logger.info(f"📦 处理批次 {batch_num}/{total_batches} ({len(batch_papers)} 篇)")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交任务
                future_to_paper = {
                    executor.submit(self.analyze_single_paper, paper, template, language): paper
                    for paper in batch_papers
                }
                
                # 收集结果
                batch_results = []
                for future in as_completed(future_to_paper):
                    try:
                        result = future.result()
                        batch_results.append(result)
                    except Exception as e:
                        paper = future_to_paper[future]
                        pmid = paper.get('PMID', 'Unknown')
                        self.logger.error(f"❌ 处理文献 {pmid} 时出现异常: {e}")
                        
                        # 创建错误记录
                        error_result = paper.copy()
                        error_result['extraction_status'] = 'processing_error'
                        error_result['extraction_error'] = str(e)
                        batch_results.append(error_result)
                
                results.extend(batch_results)
            
            # 批次间休息
            if i + batch_size < len(papers):
                self.logger.info("⏸️ 批次间休息 5 秒...")
                time.sleep(5)
        
        # 统计结果
        successful = len([r for r in results if r.get('extraction_status') == 'success'])
        failed = len(results) - successful
        
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds()
        
        self.logger.info(f"✅ 批量分析完成!")
        self.logger.info(f"📊 成功: {successful}/{len(papers)} 篇")
        self.logger.info(f"❌ 失败: {failed} 篇")
        self.logger.info(f"⏱️ 用时: {elapsed_time:.1f} 秒")
        self.logger.info(f"🪙 Token 使用: {self.stats['total_tokens_used']}")
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取分析统计信息
        
        Returns:
            统计信息字典
        """
        elapsed_time = (datetime.now() - self.stats['start_time']).total_seconds()
        
        return {
            'provider': self.provider,
            'model': self.model,
            'total_requests': self.stats['total_requests'],
            'successful_requests': self.stats['successful_requests'],
            'failed_requests': self.stats['failed_requests'],
            'success_rate': (self.stats['successful_requests'] / self.stats['total_requests'] 
                           if self.stats['total_requests'] > 0 else 0),
            'total_tokens_used': self.stats['total_tokens_used'],
            'elapsed_time': elapsed_time,
            'requests_per_minute': (self.stats['total_requests'] / (elapsed_time / 60) 
                                  if elapsed_time > 0 else 0)
        }
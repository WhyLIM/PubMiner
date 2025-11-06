# -*- coding: utf-8 -*-
"""
API 管理模块

提供统一的 API 调用、重试、限流等功能
"""

import time
import requests
import logging
from typing import Dict, Any, Optional, Callable
from functools import wraps
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimiter:
    """API 限流器"""

    def __init__(self, max_calls: int, time_window: int):
        """
        初始化限流器

        Args:
            max_calls: 时间窗口内最大调用次数
            time_window: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
        self.lock = threading.Lock()

    def can_call(self) -> bool:
        """检查是否可以调用"""
        with self.lock:
            now = datetime.now()
            # 移除过期的调用记录
            self.calls = [call_time for call_time in self.calls if now - call_time < timedelta(seconds=self.time_window)]

            return len(self.calls) < self.max_calls

    def record_call(self):
        """记录一次调用"""
        with self.lock:
            self.calls.append(datetime.now())

    def wait_if_needed(self):
        """如果需要则等待"""
        while not self.can_call():
            time.sleep(0.1)
        self.record_call()


class APIManager:
    """API 管理器"""

    def __init__(self):
        self.rate_limiters = {}
        self.session = requests.Session()

        # 设置默认请求头
        self.session.headers.update({'User-Agent': 'PubMiner/1.0 (Literature Analysis Tool)'})

    def add_rate_limiter(self, api_name: str, max_calls: int, time_window: int):
        """
        添加 API 限流器

        Args:
            api_name: API 名称
            max_calls: 时间窗口内最大调用次数
            time_window: 时间窗口（秒）
        """
        self.rate_limiters[api_name] = RateLimiter(max_calls, time_window)

    def with_retry(self,
                   max_retries: int = 3,
                   retry_delay: float = 1.0,
                   backoff_factor: float = 2.0,
                   retry_on_status: Optional[list] = None):
        """
        重试装饰器

        Args:
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟
            backoff_factor: 退避因子
            retry_on_status: 需要重试的状态码列表
        """
        if retry_on_status is None:
            retry_on_status = [429, 500, 502, 503, 504]

        def decorator(func: Callable):

            @wraps(func)
            def wrapper(*args, **kwargs):
                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code in retry_on_status:
                            if attempt < max_retries:
                                delay = retry_delay * (backoff_factor**attempt)
                                logger.warning(f"API 调用失败 (状态码: {e.response.status_code})，"
                                               f"{delay:.1f} 秒后重试 (第 {attempt + 1}/{max_retries} 次)")
                                time.sleep(delay)
                                last_exception = e
                                continue
                        raise
                    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                            requests.exceptions.RequestException) as e:
                        if attempt < max_retries:
                            delay = retry_delay * (backoff_factor**attempt)
                            logger.warning(f"网络错误，{delay:.1f} 秒后重试 (第 {attempt + 1}/{max_retries} 次): {e}")
                            time.sleep(delay)
                            last_exception = e
                            continue
                        raise
                    except Exception as e:
                        # 对于其他异常，不重试
                        raise

                # 如果所有重试都失败了
                if last_exception:
                    raise last_exception

            return wrapper

        return decorator

    def call_api(self,
                 url: str,
                 method: str = 'GET',
                 headers: Optional[Dict[str, str]] = None,
                 params: Optional[Dict[str, Any]] = None,
                 json_data: Optional[Dict[str, Any]] = None,
                 data: Optional[Any] = None,
                 timeout: int = 30,
                 api_name: Optional[str] = None,
                 **kwargs) -> requests.Response:
        """
        统一 API 调用方法

        Args:
            url: 请求 URL
            method: HTTP 方法
            headers: 请求头
            params: URL 参数
            json_data: JSON 数据
            data: 请求数据
            timeout: 超时时间
            api_name: API 名称（用于限流）
            **kwargs: 其他 requests 参数

        Returns:
            响应对象
        """
        # 应用限流
        if api_name and api_name in self.rate_limiters:
            self.rate_limiters[api_name].wait_if_needed()

        # 合并请求头
        if headers:
            request_headers = {**self.session.headers, **headers}
        else:
            request_headers = self.session.headers

        # 发起请求
        response = self.session.request(method=method,
                                        url=url,
                                        headers=request_headers,
                                        params=params,
                                        json=json_data,
                                        data=data,
                                        timeout=timeout,
                                        **kwargs)

        # 检查响应状态
        response.raise_for_status()

        return response

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET 请求"""
        return self.call_api(url, method='GET', **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST 请求"""
        return self.call_api(url, method='POST', **kwargs)

    def put(self, url: str, **kwargs) -> requests.Response:
        """PUT 请求"""
        return self.call_api(url, method='PUT', **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        """DELETE 请求"""
        return self.call_api(url, method='DELETE', **kwargs)

    def close(self):
        """关闭会话"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 全局 API 管理器实例
api_manager = APIManager()


def setup_api_rate_limits():
    """设置 API 限流规则"""
    # PubMed API 限制（无 API key 时每秒 3 次，有 API key 时每秒 10 次）
    api_manager.add_rate_limiter('pubmed_no_key', 3, 1)
    api_manager.add_rate_limiter('pubmed_with_key', 10, 1)

    # LLM API 限制（根据不同提供商设置）
    api_manager.add_rate_limiter('openai', 60, 60)  # 每分钟 60 次
    api_manager.add_rate_limiter('deepseek', 200, 60)  # 每分钟 200 次
    api_manager.add_rate_limiter('qwen', 100, 60)  # 每分钟 100 次
    api_manager.add_rate_limiter('volcengine', 60, 60)  # 每分钟 60 次


# 初始化限流规则
setup_api_rate_limits()

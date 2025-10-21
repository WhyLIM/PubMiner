# -*- coding: utf-8 -*-
"""
文件处理工具模块

提供文件读写、备份、临时文件管理等功能
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import tempfile
import logging

logger = logging.getLogger(__name__)

class FileHandler:
    """文件处理工具类"""
    
    @staticmethod
    def ensure_dir(path: Union[str, Path]) -> Path:
        """确保目录存在"""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def load_json(file_path: Union[str, Path], default: Any = None) -> Any:
        """
        加载JSON文件
        
        Args:
            file_path: 文件路径
            default: 文件不存在时的默认值
            
        Returns:
            JSON数据或默认值
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            if default is None:
                raise FileNotFoundError(f"文件不存在: {file_path}")
            return default
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解码错误 {file_path}: {e}")
            if default is None:
                raise
            return default
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            if default is None:
                raise
            return default
    
    @staticmethod
    def save_json(data: Any, file_path: Union[str, Path], backup: bool = True) -> bool:
        """
        保存JSON文件
        
        Args:
            data: 要保存的数据
            file_path: 文件路径
            backup: 是否创建备份
            
        Returns:
            是否保存成功
        """
        file_path = Path(file_path)
        
        try:
            # 确保目录存在
            FileHandler.ensure_dir(file_path.parent)
            
            # 创建备份
            if backup and file_path.exists():
                FileHandler.create_backup(file_path)
            
            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"✅ JSON文件保存成功: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ JSON文件保存失败 {file_path}: {e}")
            return False
    
    @staticmethod
    def load_text(file_path: Union[str, Path], encoding: str = 'utf-8') -> str:
        """
        加载文本文件
        
        Args:
            file_path: 文件路径
            encoding: 文件编码
            
        Returns:
            文件内容
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取文本文件失败 {file_path}: {e}")
            raise
    
    @staticmethod
    def save_text(content: str, file_path: Union[str, Path], 
                  encoding: str = 'utf-8', backup: bool = True) -> bool:
        """
        保存文本文件
        
        Args:
            content: 文本内容
            file_path: 文件路径
            encoding: 文件编码
            backup: 是否创建备份
            
        Returns:
            是否保存成功
        """
        file_path = Path(file_path)
        
        try:
            # 确保目录存在
            FileHandler.ensure_dir(file_path.parent)
            
            # 创建备份
            if backup and file_path.exists():
                FileHandler.create_backup(file_path)
            
            # 保存文件
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
            
            logger.debug(f"✅ 文本文件保存成功: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 文本文件保存失败 {file_path}: {e}")
            return False
    
    @staticmethod
    def create_backup(file_path: Union[str, Path], backup_dir: Optional[Path] = None) -> Optional[Path]:
        """
        创建文件备份
        
        Args:
            file_path: 原文件路径
            backup_dir: 备份目录，默认为results/backup子目录
            
        Returns:
            备份文件路径，失败返回None
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.warning(f"要备份的文件不存在: {file_path}")
            return None
        
        try:
            if backup_dir is None:
                # 使用results/backup作为默认备份目录
                backup_dir = Path('results') / 'backup'
            
            FileHandler.ensure_dir(backup_dir)
            
            # 生成带时间戳的备份文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = backup_dir / backup_name
            
            # 复制文件
            shutil.copy2(file_path, backup_path)
            logger.debug(f"✅ 创建备份成功: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ 创建备份失败 {file_path}: {e}")
            return None
    
    @staticmethod
    def load_pmid_list(file_path: Union[str, Path]) -> List[str]:
        """
        从文件加载PMID列表
        
        支持格式：
        - 纯文本文件（每行一个PMID）
        - CSV文件（第一列为PMID）
        - JSON文件（数组格式）
        
        Args:
            file_path: 文件路径
            
        Returns:
            PMID列表
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"PMID文件不存在: {file_path}")
        
        try:
            suffix = file_path.suffix.lower()
            
            if suffix == '.json':
                data = FileHandler.load_json(file_path)
                if isinstance(data, list):
                    return [str(pmid).strip() for pmid in data if str(pmid).strip()]
                else:
                    raise ValueError("JSON文件应包含PMID数组")
                    
            elif suffix == '.csv':
                import pandas as pd
                df = pd.read_csv(file_path)
                # 假设第一列是PMID
                first_col = df.iloc[:, 0]
                return [str(pmid).strip() for pmid in first_col if str(pmid).strip() and str(pmid) != 'nan']
                
            else:
                # 纯文本文件
                content = FileHandler.load_text(file_path)
                lines = content.strip().split('\n')
                return [line.strip() for line in lines if line.strip()]
                
        except Exception as e:
            logger.error(f"加载PMID列表失败 {file_path}: {e}")
            raise
    
    @staticmethod
    def get_temp_file(suffix: str = '', prefix: str = 'pubminer_') -> str:
        """
        创建临时文件
        
        Args:
            suffix: 文件后缀
            prefix: 文件前缀
            
        Returns:
            临时文件路径
        """
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)  # 关闭文件描述符，但保留文件
        return temp_path
    
    @staticmethod
    def get_temp_dir(prefix: str = 'pubminer_') -> str:
        """
        创建临时目录
        
        Args:
            prefix: 目录前缀
            
        Returns:
            临时目录路径
        """
        return tempfile.mkdtemp(prefix=prefix)
    
    @staticmethod
    def clean_temp_files(temp_paths: List[str]):
        """
        清理临时文件
        
        Args:
            temp_paths: 临时文件路径列表
        """
        for temp_path in temp_paths:
            try:
                temp_path = Path(temp_path)
                if temp_path.exists():
                    if temp_path.is_file():
                        temp_path.unlink()
                    elif temp_path.is_dir():
                        shutil.rmtree(temp_path)
                    logger.debug(f"✅ 清理临时文件: {temp_path}")
            except Exception as e:
                logger.warning(f"⚠️ 清理临时文件失败 {temp_path}: {e}")
    
    @staticmethod
    def get_file_info(file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        获取文件信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件信息字典
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return {"exists": False}
        
        stat = file_path.stat()
        
        return {
            "exists": True,
            "size": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "created": datetime.fromtimestamp(stat.st_ctime),
            "is_file": file_path.is_file(),
            "is_dir": file_path.is_dir(),
            "suffix": file_path.suffix,
            "name": file_path.name,
            "stem": file_path.stem
        }
# -*- coding: utf-8 -*-
"""
PDF下载模块使用示例
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.pdf_downloader import PDFDownloader
from core.config_manager import ConfigManager
from utils.logger import LoggerMixin


class PDFDownloadExample(LoggerMixin):
    """PDF下载示例类"""
    
    def __init__(self):
        """初始化"""
        super().__init__()
        
        # 加载配置
        config_manager = ConfigManager()
        self.pdf_config = config_manager.get_pdf_download_config()
        
        # 创建下载器
        self.downloader = PDFDownloader(self.pdf_config)
        
        self.logger.info("PDF下载示例初始化完成")
    
    def download_single_paper(self):
        """下载单篇论文示例"""
        self.logger.info("开始单篇论文下载示例")
        
        # 使用DOI下载
        doi = "10.1038/nature12373"  # 示例DOI
        self.logger.info(f"尝试下载DOI: {doi}")
        
        result = self.downloader.download_by_doi(doi)
        
        if result['success']:
            self.logger.info(f"下载成功: {result['file_path']}")
            self.logger.info(f"文件大小: {result.get('file_size', 'Unknown')} bytes")
        else:
            self.logger.error(f"下载失败: {result['error']}")
    
    def download_by_pmid(self):
        """通过PMID下载示例"""
        self.logger.info("开始PMID下载示例")
        
        pmid = "23846655"  # 示例PMID
        self.logger.info(f"尝试下载PMID: {pmid}")
        
        result = self.downloader.download_by_pmid(pmid)
        
        if result['success']:
            self.logger.info(f"下载成功: {result['file_path']}")
        else:
            self.logger.error(f"下载失败: {result['error']}")
    
    def batch_download_example(self):
        """批量下载示例"""
        self.logger.info("开始批量下载示例")
        
        # 准备DOI列表
        dois = [
            "10.1038/nature12373",
            "10.1126/science.1234567",
            "10.1016/j.cell.2023.01.001"
        ]
        
        # 批量下载
        results = self.downloader.batch_download(dois)
        
        # 统计结果
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        self.logger.info(f"批量下载完成: 成功 {successful}, 失败 {failed}")
        
        # 显示详细结果
        for i, result in enumerate(results):
            if result['success']:
                self.logger.info(f"  [{i+1}] 成功: {result['file_path']}")
            else:
                self.logger.error(f"  [{i+1}] 失败: {result['error']}")
    
    def download_with_metadata(self):
        """带元数据的下载示例"""
        self.logger.info("开始带元数据下载示例")
        
        doi = "10.1038/nature12373"
        
        # 下载并获取元数据
        result = self.downloader.download_by_doi(doi, include_metadata=True)
        
        if result['success']:
            self.logger.info(f"下载成功: {result['file_path']}")
            
            # 显示元数据
            metadata = result.get('metadata', {})
            if metadata:
                self.logger.info("论文元数据:")
                self.logger.info(f"  标题: {metadata.get('title', 'N/A')}")
                self.logger.info(f"  作者: {', '.join(metadata.get('authors', []))}")
                self.logger.info(f"  期刊: {metadata.get('journal', 'N/A')}")
                self.logger.info(f"  发表年份: {metadata.get('year', 'N/A')}")
        else:
            self.logger.error(f"下载失败: {result['error']}")


def main():
    """主函数"""
    print("PubMiner PDF下载模块使用示例")
    print("=" * 50)
    
    try:
        example = PDFDownloadExample()
        
        print("\n1. 单篇论文下载示例")
        print("-" * 30)
        example.download_single_paper()
        
        print("\n2. PMID下载示例")
        print("-" * 30)
        example.download_by_pmid()
        
        print("\n3. 批量下载示例")
        print("-" * 30)
        example.batch_download_example()
        
        print("\n4. 带元数据下载示例")
        print("-" * 30)
        example.download_with_metadata()
        
        print("\n示例运行完成!")
        
    except Exception as e:
        print(f"运行示例时出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
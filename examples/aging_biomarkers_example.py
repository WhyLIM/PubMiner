#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
衰老生物标志物研究示例

演示如何使用自定义模板分析衰老生物标志物相关文献
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from main import PubMiner


def main():
    """衰老生物标志物研究示例"""
    print("🧬 衰老生物标志物文献分析示例")
    print("=" * 60)

    # 初始化PubMiner
    miner = PubMiner()

    # 设置API密钥（请先在.env文件中配置）
    print("📋 请确保已在.env文件中配置API密钥")

    try:
        # 使用自定义模板分析衰老生物标志物相关文献
        print("\n🔍 开始分析衰老生物标志物文献...")

        results = miner.analyze_by_query(
            query="aging biomarkers human",
            template="custom_template",  # 使用自定义模板示例
            max_papers=10,
            output_file="aging_biomarkers_analysis.csv")

        print(f"\n✅ 分析完成！")
        print(f"📊 共分析了 {len(results)} 篇文献")
        print(f"📁 结果已保存到: aging_biomarkers_analysis.csv")

        # 显示部分结果
        if results:
            print("\n📋 部分提取结果预览:")
            print("-" * 60)
            for i, result in enumerate(results[:3], 1):
                print(f"\n{i}. {result.get('Title', 'Unknown Title')}")
                print(f"   PMID: {result.get('PMID', 'N/A')}")
                print(f"   生物标志物类型: {result.get('Biomarker_Type', 'N/A')}")
                print(f"   分子类型: {result.get('Molecular_Type', 'N/A')}")
                print(f"   人群种族: {result.get('Population_Ethnicity', 'N/A')}")

    except Exception as e:
        print(f"❌ 分析过程中出现错误: {e}")
        print("💡 请检查:")
        print("   1. 网络连接是否正常")
        print("   2. API密钥是否正确配置")
        print("   3. 配置文件是否完整")


if __name__ == "__main__":
    main()

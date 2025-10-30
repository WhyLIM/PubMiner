# PubMiner - 基于大语言模型的模块化文献分析工具

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)]()

PubMiner 是一个专门针对 PubMed 医学文献的智能分析工具，通过模块化架构实现文献检索、全文提取、结构化分析和批量处理，帮助研究人员高效挖掘文献信息。

## 🎯 核心特性

- **🔍 智能检索**：支持复杂 PubMed 查询语法，自动获取引用关系
- **📄 多源提取**：集成 PMC 全文、 PDF 解析和 OCR 识别
- **🧠 AI 分析**：支持 OpenAI、 DeepSeek、通义千问等多个 LLM 提供商
- **📊 结构化输出**： 22 个标准字段 + 自定义字段，输出标准 CSV 格式
- **⚡ 高效处理**：并发处理、断点续传、智能重试机制
- **💰 成本优化**：文本压缩、批量处理，显著降低 API 调用成本
- **📋 批量任务**： JSON 配置驱动的自动化批量分析

## 🏗️ 项目架构

```
PubMiner/
├── main.py                    # 主程序入口
├── config/                    # 配置文件
│   ├── default_config.json    # 全局配置
│   ├── extraction_templates.json  # 提取模板
│   ├── pdf_download_config.json   # PDF 下载配置
│   └── query_templates.json   # 批量查询模板
├── core/                      # 核心模块
│   ├── config_manager.py      # 配置管理
│   ├── pubmed_fetcher.py      # PubMed 数据获取
│   ├── text_extractor.py      # 全文提取
│   ├── pdf_downloader.py      # PDF 下载器
│   ├── llm_analyzer.py        # LLM 分析
│   ├── data_processor.py      # 数据处理
│   └── query_manager.py       # 批量查询管理
├── utils/                     # 工具模块
├── extractors/                # 信息提取器
├── optimizers/                # Token 优化器
├── examples/                  # 使用示例
└── tests/                     # 测试文件
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- 4GB+ 内存
- 稳定网络连接

### 安装配置

```bash
# 1. 克隆项目
git clone https://github.com/WhyLIM/PubMiner.git
cd PubMiner

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置 API 密钥
```

### 环境变量配置

编辑 `.env` 文件：

```env
# PubMed API（推荐配置，提高请求限额）
PUBMED_EMAIL=your.email@example.com
PUBMED_API_KEY=your_ncbi_api_key

# LLM 提供商（至少配置一个）
DEEPSEEK_API_KEY=your_deepseek_key      # 推荐：性价比最高
OPENAI_API_KEY=your_openai_key          # 功能最全面
QWEN_API_KEY=your_qwen_key              # 中文支持好
VOLCENGINE_API_KEY=your_volcengine_key  # 国内服务稳定
```

### 基础使用

#### 1. 命令行使用

```bash
# 基础查询
python main.py --query "diabetes AND treatment" --output results.csv

# 包含全文分析
python main.py --query "COVID-19 AND vaccine" \
    --include-fulltext \
    --template standard \
    --max-workers 4

# PMID 列表分析
python main.py --pmids "12345678,87654321" \
    --template custom_template_example \
    --output pmid_analysis.csv

# 批量配置执行
python main.py --batch-config config/query_templates.json
```

#### 2. Python 编程接口

```python
from main import PubMiner

# 初始化
miner = PubMiner(llm_provider='deepseek')

# 查询分析
results = miner.analyze_by_query(
    query='machine learning AND medical diagnosis',
    template_name='standard',
    max_results=100,
    include_fulltext=True
)

# PMID 分析
pmid_results = miner.analyze_by_pmids(
    pmids=['12345678', '87654321'],
    template_name='custom_template_example'
)

# 保存结果
output_path = miner.save_results(results, 'analysis_results')
print(f" 结果已保存至：{output_path}")
```

## 📊 提取字段体系

### 标准模板（ 22 个字段）

涵盖医学文献分析的核心要素：

| 类别 | 字段 | 说明 |
|------|------|------|
| **研究背景** | Research_Background | 研究背景和动机 |
| | Theoretical_Framework | 理论框架 |
| | Existing_Research | 现有研究现状 |
| **研究设计** | Research_Objectives | 研究目标 |
| | Research_Questions | 研究问题 |
| | Sample_Size | 样本数量 |
| | Study_Region | 研究区域 |
| **方法工具** | Methods_Tools | 研究方法和工具 |
| | Variables | 变量设定 |
| | Data_Sources | 数据来源 |
| **研究结果** | Key_Findings | 核心发现 |
| | Main_Conclusions | 主要结论 |
| | Hypothesis_Evidence | 假设验证 |
| **讨论分析** | Result_Interpretation | 结果解释 |
| | Theoretical_Significance | 理论意义 |
| | Practical_Value | 实践价值 |
| **研究局限** | Data_Limitations | 数据局限性 |
| | Method_Limitations | 方法局限性 |
| | Future_Directions | 未来方向 |

### 自定义模板示例

**生物标志物研究模板**：
- 生物标志物类型和分类
- 检测方法和技术平台
- 研究人群特征
- 临床应用价值
- 验证状态等

## 📋 批量查询配置

### 配置文件示例

```json
{
    "query_tasks": [
        {
            "name": "COVID-19 与糖尿病研究 ",
            "query": "(COVID-19[ti] OR SARS-CoV-2[ti]) AND (diabetes[ti] OR diabetic[ti])",
            "max_results": 100,
            "include_fulltext": true,
            "output_file": "covid_diabetes.csv",
            "language": "English",
            "custom_fields": [
                " 研究的糖尿病类型 ",
                "COVID-19 对糖尿病患者的影响 ",
                " 推荐的治疗方案 "
            ]
        }
    ],
    "default_settings": {
        "max_results": 100,
        "include_fulltext": false,
        "output_dir": "results/batch_queries",
        "language": "English"
    }
}
```

### 执行批量任务

```bash
# 使用预设配置
python main.py --batch-config config/query_templates.json

# 查看执行报告
cat results/batch_queries/execution_report.json
```

## 📥 PDF 下载功能

PubMiner 集成了强大的 PDF 下载模块，支持多源智能下载：

### 🚀 核心特性

- **🔍 开放获取检测**：自动识别开放获取文章，优先使用免费源
- **📚 多源下载策略**： PMC、 SciHub 等多个数据源智能切换
- **🔄 强化重试机制**：指数退避重试，网络容错能力强
- **📝 统一文件命名**：`{doi}_{source}.pdf` 格式，便于管理
- **✅ 文件完整性校验**：自动验证 PDF 文件有效性
- **⚡ 并发下载**：支持多线程批量下载

### 🎯 智能下载流程

1. **开放获取检测**：通过 Crossref API 检查文章开放状态
2. **PMC 优先下载**：开放获取文章优先从 PMC 下载
3. **SciHub 备用**： PMC 失败时自动切换到 SciHub
4. **重试机制**：网络问题时自动重试，最大化成功率

### 💡 使用示例

```python
from core.pdf_downloader import PDFDownloader

# 初始化下载器
config = {
    'download_dir': './pdfs',
    'max_retries': 3,
    'timeout': 30
}
downloader = PDFDownloader(config)

# 通过 DOI 下载（智能多源）
result = downloader.download_by_doi(
    doi="10.1002/imt2.155",
    title="CBD2: A functional biomarker database"
)

# 检查结果
if result['success']:
    print(f" 下载成功：{result['local_path']}")
    print(f" 来源：{result['source']}")  # PMC 或 SciHub
    print(f" 文件大小：{result['file_size']/1024:.1f}KB")

# 批量下载
papers = [
    {"doi": "10.1093/database/bay046", "title": "SIFTS database"},
    {"doi": "10.1002/imt2.155", "title": "CBD2 database"}
]
results = downloader.batch_download(papers)
```

### 📊 下载统计示例

```
✅ 10.1002/imt2.155 - PMC - 10.1002_imt2.155_PMC.pdf (2432.9KB)
✅ 10.1093/database/bay046 - PMC - 10.1093_database_bay046_PMC.pdf (2046.1KB)
```

## ⚙️ 高级配置

### 性能优化

```bash
# 并发优化
python main.py --query "large dataset" \
    --max-workers 8 \
    --batch-size 20 \
    --text-limit 15000

# 成本控制
python main.py --query "cost sensitive" \
    --llm-provider deepseek \
    --cost-limit 50.0 \
    --smart-compression
```

### 提供商选择建议

| 提供商 | 优势 | 适用场景 | 相对成本 |
|--------|------|----------|----------|
| **DeepSeek** | 性价比极高 | 大规模批量处理 | ⭐⭐⭐⭐⭐ |
| **OpenAI** | 功能最全面 | 高质量精细分析 | ⭐⭐ |
| **通义千问** | 中文理解优秀 | 中文文献分析 | ⭐⭐⭐⭐ |
| **火山引擎** | 国内服务稳定 | 企业级应用 | ⭐⭐⭐ |

## 🧪 测试验证

```bash
# 运行基础测试
python tests/test_01_basic_functionality.py

# 运行 PDF 下载测试（包含重试机制验证）
python tests/test_06_pdf_download.py

# 运行完整测试套件
python tests/run_all_tests.py

# 使用 pytest 运行所有测试
python -m pytest tests/ -v
```

### 测试覆盖范围

- ✅ **基础功能测试**： PubMed 搜索、数据提取、 CSV 导出
- ✅ **引用功能测试**：引用查询、参考文献分析
- ✅ **批量查询测试**：配置文件批量处理、模板系统
- ✅ **文本分析测试**：全文提取、 AI 驱动分析
- ✅ **集成性能测试**：端到端工作流、性能基准
- ✅ **PDF 下载测试**：多源下载、重试机制、文件命名验证

## 📊 输出格式

### CSV 文件结构

生成的 CSV 文件包含以下列：

- **基本信息**： PMID, Title, Authors, Journal, DOI, Year 等
- **引用信息**： Cited_Count, References_Count 等
- **提取结果**： 22 个标准字段 + 自定义字段
- **质量控制**： extraction_status, quality_score 等

### 执行报告

自动生成详细的执行报告：

- 处理统计（成功率、耗时等）
- 成本分析（ Token 使用、费用估算）
- 质量评估（提取质量分布）
- 错误分析（失败原因统计）

## 💡 最佳实践

### 新用户建议

1. **从小规模开始**：先用 10-50 篇文献测试
2. **选择合适模板**：根据研究领域选择模板
3. **成本控制**：设置合理的成本上限
4. **质量验证**：对结果进行人工抽检

### 大规模使用

1. **分批处理**：将大任务分解为小批次
2. **配置优化**：根据系统性能调整参数
3. **监控报告**：定期查看执行报告
4. **数据备份**：定期备份重要结果

## 🤝 贡献指南

欢迎各种形式的贡献：

- 🐛 问题报告
- 💡 功能建议
- 📝 文档改进
- 🔧 代码贡献

### 开发环境

```bash
# 克隆开发版本
git clone https://github.com/WhyLIM/PubMiner.git
cd PubMiner

# 安装开发依赖
pip install -r requirements.txt

# 运行测试
python -m pytest tests/
```

## 📄 许可证

本项目采用 [MIT 许可证 ](LICENSE)。

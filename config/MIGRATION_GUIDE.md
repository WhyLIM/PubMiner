# 配置文件迁移指南

## 概述

PubMiner 已从单一配置文件架构升级为模块化配置架构。本指南帮助您平滑迁移到新的配置系统。

## 迁移的好处

1. **更好的组织结构**：配置按功能模块分离
2. **更易维护**：每个配置文件职责单一
3. **更强扩展性**：支持模板继承和环境变量
4. **向后兼容**：现有代码无需修改即可工作

## 迁移步骤

### 1. 备份现有配置

```bash
# 备份现有配置文件
cp config/default_config.json config/default_config.json.backup
cp config/extraction_templates.json config/extraction_templates.json.backup
cp config/query_templates.json config/query_templates.json.backup
cp config/pdf_download_config.json config/pdf_download_config.json.backup
```

### 2. 新配置文件已创建

新的配置文件已经自动创建在以下目录结构中：

```
config/
├── core/                     # 核心配置
│   ├── app_config.json      # 应用基础配置
│   ├── pubmed_config.json   # PubMed API 配置
│   ├── llm_config.json      # LLM 提供商配置
│   └── processing_config.json # 处理流程配置
├── extraction/               # 提取配置
│   ├── extraction_templates.json # 提取模板
│   └── text_processing_config.json # 文本处理配置
├── query/                    # 查询配置
│   └── query_templates.json  # 查询模板
├── output/                   # 输出配置
│   ├── pdf_config.json       # PDF 下载配置
│   └── output_config.json    # 输出格式配置
└── config_loader.py          # 配置加载器
```

### 3. 验证新配置系统

系统会自动检测并使用新配置系统。您可以通过以下代码验证：

```python
from core.config_manager import ConfigManager

# 创建配置管理器
config_manager = ConfigManager()

# 检查配置状态
status = config_manager.get_config_status()
print(f"配置文件: {status['config_file']}")
print(f"模板数量: {status['templates_count']}")
```

## 配置映射说明

### PubMed 配置迁移

**旧配置** (`default_config.json`):
```json
{
    "pubmed": {
        "email": "${PUBMED_EMAIL}",
        "api_key": "${PUBMED_API_KEY}",
        "batch_size": 50,
        "max_retries": 5,
        "retry_wait_time": 5,
        "api_wait_time": 0.5,
        "output_dir": "./results"
    }
}
```

**新配置** (`core/pubmed_config.json`):
```json
{
    "pubmed_api": {
        "email": "${PUBMED_EMAIL}",
        "api_key": "${PUBMED_API_KEY}",
        "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "batch_size": 50,
        "max_retries": 5,
        "retry_wait_time": 5,
        "api_wait_time": 0.5
    },
    "search_settings": {
        "default_max_results": 100,
        "sort_order": "relevance"
    },
    "citation_settings": {
        "fetch_detailed_pmid_lists": true,
        "citation_dir": "citations"
    }
}
```

### LLM 配置迁移

**旧配置** (`default_config.json`):
```json
{
    "llm_providers": {
        "deepseek": {
            "api_base": "${DEEPSEEK_BASE_URL}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-chat",
            "temperature": 0.1,
            "max_tokens": 4000
        }
    }
}
```

**新配置** (`core/llm_config.json`):
```json
{
    "llm_providers": {
        "deepseek": {
            "api_base": "${DEEPSEEK_BASE_URL}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
            "timeout": 60,
            "enabled": true
        }
    },
    "default_provider": "deepseek",
    "cost_management": {
        "enable_cost_tracking": true,
        "daily_budget": 10.0
    }
}
```

### 提取模板增强

**主要改进**：
1. **模板继承**：支持 `extends` 字段
2. **字段优先级**：添加 `priority` 和 `required` 字段
3. **数据类型**：支持 `data_type` 定义
4. **验证规则**：添加 `validation_rules`

**新功能示例**：
```json
{
    "aging_biomarkers": {
        "name": "Aging Biomarkers Research Template",
        "extends": "standard",  // 继承标准模板
        "fields": {
            "biomarker_type": {
                "name": "Biomarker Type",
                "required": true,
                "priority": 1,
                "data_type": "string"
            }
        },
        "validation_rules": {
            "min_required_fields": 10
        }
    }
}
```

### 查询模板优化

**移除冗余**：
- 删除 `custom_fields`（移至提取模板）
- 删除 `default_settings`（改为具体配置）

**新结构**：
```json
{
    "query_tasks": [
        {
            "id": "unique_task_id",
            "name": "任务名称",
            "query": "PubMed查询语句",
            "extraction_template": "standard",
            "output_file": "results.csv",
            "settings": {
                "max_results": 100,
                "include_fulltext": false
            }
        }
    ]
}
```

## 向后兼容性

### 自动降级
如果新配置系统初始化失败，系统会自动回退到旧配置：

```python
# 系统会自动处理，无需手动干预
config_manager = ConfigManager()  # 自动选择最佳配置系统
```

### API 兼容性
所有现有的 API 调用都保持不变：

```python
# 这些调用在新旧系统中都有效
pubmed_config = config_manager.get_pubmed_config()
template = config_manager.get_extraction_template('standard')
output_config = config_manager.get_output_config()
```

## 环境变量

新配置系统支持更灵活的环境变量：

```bash
# 标准环境变量替换
export API_KEY="your_api_key"

# 在配置文件中使用
{
    "api_key": "${API_KEY}",
    "timeout": "${TIMEOUT:30}"  # 支持默认值（未来版本）
}
```

## 故障排除

### 常见问题

**问题 1**: 配置文件格式错误
```bash
# 验证 JSON 格式
python -m json.tool config/core/app_config.json
```

**问题 2**: 环境变量未设置
```python
# 检查环境变量
import os
print("PUBMED_EMAIL:", os.getenv("PUBMED_EMAIL"))
print("DEEPSEEK_API_KEY:", os.getenv("DEEPSEEK_API_KEY"))
```

### 调试模式

启用详细日志：
```python
import logging
logging.basicConfig(level=logging.DEBUG)

config_manager = ConfigManager()
# 查看详细的配置加载过程
```

## 自定义配置

### 添加新的配置类别

1. 在相应目录创建配置文件
2. 在 `config_loader.py` 中添加映射
3. 在 `ConfigManager` 中添加获取方法

### 创建自定义提取模板

```python
# 方法 1：通过配置文件
# 在 config/extraction/extraction_templates.json 中添加

# 方法 2：通过代码
template = config_manager.load_custom_template("my_template.json")
```

## 性能考虑

### 配置缓存
新配置系统自动缓存配置文件：
- 首次加载时读取文件
- 后续调用使用缓存
- 支持手动刷新缓存

```python
# 清除缓存（如果需要）
if hasattr(config_manager, 'config_loader'):
    config_manager.config_loader.clear_cache()
```

### 启动时间
新配置系统可能增加约 50-100ms 的启动时间（由于加载多个文件），但提供了更好的结构和功能。

## 渐进式迁移

如果您不想立即完全迁移，可以：

1. **保持现有配置**：系统会继续使用旧配置
2. **逐步测试**：在测试环境中使用新配置
3. **分模块迁移**：先迁移部分配置，再逐步完成

## 回滚方案

如果需要回滚到旧配置：

```bash
# 恢复备份的配置文件
cp config/default_config.json.backup config/default_config.json

# 重命名新配置目录（可选）
mv config/core config/core.disabled
mv config/extraction config/extraction.disabled
mv config/query config/query.disabled
mv config/output config/output.disabled
```

## 支持和反馈

如果在迁移过程中遇到问题：

1. 检查日志输出中的错误信息
2. 验证 JSON 文件格式
3. 确认环境变量设置
4. 参考本指南的故障排除部分

## 更新历史

- **2025-11-04**: 初始迁移指南
  - 支持模块化配置架构
  - 向后兼容性保证
  - 自动降级机制
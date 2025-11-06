# 配置文件重新设计说明

## 重新设计原因

原始配置文件架构存在以下问题：
1. **功能混杂**：`query_templates.json` 混合了查询模板、提取字段和默认设置
2. **配置重复**：`custom_fields` 在 `query_templates.json` 中冗余
3. **职责不清**：配置文件之间边界模糊
4. **扩展性差**：难以添加新的配置类别

## 新架构设计

### 目录结构
```
config/
├── core/                     # 核心应用配置
│   ├── app_config.json      # 应用基础配置
│   ├── pubmed_config.json   # PubMed API 配置
│   ├── llm_config.json      # LLM 提供商配置
│   └── processing_config.json # 处理流程配置
├── extraction/               # 提取相关配置
│   ├── extraction_templates.json # 提取模板（整合原有功能）
│   └── text_processing_config.json # 文本处理配置
├── query/                    # 查询相关配置
│   └── query_templates.json  # 纯查询模板
├── output/                   # 输出相关配置
│   ├── pdf_config.json       # PDF 下载配置
│   └── output_config.json    # 输出格式配置
├── config_loader.py          # 新的配置加载器
└── README.md                 # 本说明文件
```

### 主要改进

1. **功能分离**：每个配置文件职责单一明确
2. **模板继承**：提取模板支持继承机制
3. **环境变量**：支持环境变量自动替换
4. **配置缓存**：提高配置加载性能
5. **结构验证**：自动验证配置文件完整性

### 配置文件说明

#### core/ - 核心配置
- `app_config.json`: 应用基础信息、系统设置、路径配置
- `pubmed_config.json`: PubMed API 配置、搜索设置、引用配置
- `llm_config.json`: LLM 提供商配置、成本管理
- `processing_config.json`: 语言设置、优化选项、缓存配置

#### extraction/ - 提取配置
- `extraction_templates.json`: 提取模板（整合原有 custom_fields）
- `text_processing_config.json`: 文本提取、BioC 处理、PDF 处理

#### query/ - 查询配置
- `query_templates.json`: 纯查询模板（移除冗余字段）

#### output/ - 输出配置
- `pdf_config.json`: PDF 下载配置
- `output_config.json`: 输出格式配置

### 迁移指南

#### 向后兼容性
为了保持向后兼容，原有的配置文件仍然保留，但建议逐步迁移到新架构。

#### 使用新配置加载器
```python
from config.config_loader import get_config_loader, load_config, get_extraction_template

# 加载单个配置
app_config = load_config('app')

# 获取提取模板
template = get_extraction_template('aging_biomarkers')

# 获取查询模板
query = get_query_template('colorectal_cancer_biomarkers')
```

#### 环境变量支持
新配置支持环境变量替换：
```json
{
    "api_key": "${API_KEY}",
    "base_url": "${BASE_URL:http://default}"
}
```

### 主要优势

1. **清晰结构**：功能分离，职责明确
2. **易于维护**：模块化设计，便于扩展
3. **性能优化**：配置缓存，减少重复加载
4. **类型安全**：结构验证，减少配置错误
5. **继承支持**：模板继承，减少重复配置

### 注意事项

1. **环境变量**：确保环境变量正确设置
2. **路径配置**：相对路径基于项目根目录
3. **模板继承**：注意继承顺序和字段覆盖
4. **配置验证**：启动时会自动验证配置结构

## 更新历史

- **2025-11-04**: 完成配置文件重新设计
  - 创建新的模块化配置架构
  - 实现配置加载器
  - 支持模板继承和环境变量
  - 添加配置验证功能
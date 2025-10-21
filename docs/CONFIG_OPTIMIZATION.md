# 配置管理优化方案

## 问题分析

之前的配置系统存在以下问题：
1. **配置重复**：API密钥在config.json和.env中都存在
2. **安全隐患**：敏感信息直接写在配置文件中
3. **维护困难**：需要在两个地方同步更新
4. **版本控制问题**：敏感信息容易被提交到Git

## 优化方案

### 配置分离原则

**环境变量（.env文件）**：
- ✅ API密钥（敏感信息）
- ✅ 邮箱地址
- ✅ API端点URL
- ✅ 日志级别等环境相关配置

**配置文件（config.json）**：
- ✅ 业务逻辑配置（批次大小、超时时间等）
- ✅ 模板配置
- ✅ 处理参数
- ✅ 输出格式设置

### 配置优先级

1. **环境变量** > **配置文件默认值**
2. 使用 `${VAR_NAME}` 占位符在配置文件中引用环境变量
3. 如果环境变量未设置，使用空字符串并记录警告

## 配置文件示例

### .env文件
```bash
# API密钥（敏感信息）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxx
QWEN_API_KEY=sk-xxxxxxxxxxxx
VOLCENGINE_API_KEY=your_key_here

# API端点
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
OPENAI_BASE_URL=https://api.openai.com/v1
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VOLCENGINE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# PubMed配置
PUBMED_EMAIL=your_email@example.com
PUBMED_API_KEY=your_pubmed_key

# 其他环境变量
LOG_LEVEL=INFO
```

### config/default_config.json
```json
{
    "pubmed": {
        "email": "${PUBMED_EMAIL}",
        "api_key": "${PUBMED_API_KEY}",
        "batch_size": 50,
        "max_retries": 5
    },
    "llm_providers": {
        "deepseek": {
            "api_base": "${DEEPSEEK_BASE_URL}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-chat",
            "temperature": 0.1
        }
    }
}
```

## 实现细节

### 环境变量替换机制
- 使用正则表达式 `${VAR_NAME}` 识别占位符
- 自动从环境变量中获取值并替换
- 未设置的环境变量会记录警告并使用空字符串

### 安全考虑
- `.env` 文件已添加到 `.gitignore`
- 提供 `.env.example` 作为模板
- 都敏感信息从配置文件中移除

## 使用方法

1. **复制环境变量模板**：
   ```bash
   cp .env.example .env
   ```

2. **编辑.env文件**：
   ```bash
   # 填写真实的API密钥
   DEEPSEEK_API_KEY=your_actual_key_here
   ```

3. **运行程序**：
   程序会自动加载环境变量并替换配置文件中的占位符

## 优势

1. **安全性**：敏感信息不会被提交到版本控制
2. **灵活性**：不同环境可以使用不同的环境变量
3. **维护性**：配置集中管理，避免重复
4. **可读性**：配置文件结构清晰，职责分明

## 兼容性

- 保持向后兼容
- 如果环境变量未设置，会给出明确警告
- 支持渐进式迁移